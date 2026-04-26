from pathlib import Path
import os
import secrets
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .anti_repetition import build_anti_repetition_report
from .mock_server import MockGpuServer
from .models import (
    AntiRepetitionReport,
    ArtifactInventoryItem,
    BriefInput,
    ComplianceReportArtifact,
    DispatchNextInput,
    DispatchNextResult,
    EpisodeSpec,
    EpisodeSpecInput,
    FullEpisodeArtifact,
    GenerationArtifact,
    GenerationArtifactView,
    GenerationJobDetail,
    GenerationRunnerState,
    HUMAN_REVIEW_STAGES,
    Job,
    JobEvent,
    KeyframesArtifact,
    LockHeartbeatInput,
    LockHeartbeatResult,
    LyricsArtifact,
    PIPELINE_STAGES,
    Project,
    ProjectNextAction,
    ProjectSeriesLinkInput,
    PublishPackageArtifact,
    ReelsArtifact,
    ServerProfile,
    ServerProfileInput,
    STAGE_DISPLAY_CATALOG,
    STAGE_LABELS,
    SeriesBible,
    SeriesBibleInput,
    StageApproval,
    StageApprovalInput,
    StageCatalogItem,
    StageStatus,
    StaleLockRecoveryInput,
    StaleLockRecoveryResult,
    StoryboardArtifact,
    VideoScenesArtifact,
    WorkerQueueStatus,
    create_project_from_brief,
    utc_now,
)
from .ssh_generation import SshGenerationServer
from .storage import ProjectStorage


def get_project_next_action(project: Project, anti_repetition_report: AntiRepetitionReport | None = None) -> ProjectNextAction:
    if project.series_id is None:
        return ProjectNextAction(
            action_type="define_series",
            stage=None,
            label="Series Bible",
            message="Wybierz albo utwórz Series Bible zanim uruchomisz produkcję.",
            severity="blocker",
        )

    if project.episode_spec is None or not project.episode_spec.learning_objective.statement.strip():
        return ProjectNextAction(
            action_type="complete_episode_spec",
            stage=None,
            label="Episode Spec",
            message="Uzupełnij Episode Spec i konkretny learning objective.",
            severity="blocker",
        )

    if project.episode_spec.approval_status != "approved":
        return ProjectNextAction(
            action_type="approve_episode_spec",
            stage=None,
            label="Episode Spec",
            message="Episode Spec czeka na akceptację operatora.",
            severity="blocker",
        )

    if anti_repetition_report is None:
        return ProjectNextAction(
            action_type="run_anti_repetition_check",
            stage=None,
            label="Anti-Repetition",
            message="Uruchom Anti-Repetition check przed produkcją.",
            severity="warning",
        )

    if anti_repetition_report.status in {"blocker", "review_recommended"}:
        return ProjectNextAction(
            action_type="fix_repetition_risk",
            stage=None,
            label="Anti-Repetition",
            message=f"Projekt jest zbyt podobny do wcześniejszych materiałów w serii ({anti_repetition_report.score:.2f}).",
            severity="blocker" if anti_repetition_report.status == "blocker" else "warning",
        )

    review_stage = next((stage for stage in project.pipeline if stage.status == StageStatus.NEEDS_REVIEW), None)
    if review_stage is not None:
        label = STAGE_LABELS.get(review_stage.stage, review_stage.stage)
        return ProjectNextAction(
            action_type="approve",
            stage=review_stage.stage,
            label=label,
            message=f"{label} czeka na akceptację operatora.",
            severity="info",
        )

    runnable_stage = next((stage for stage in project.pipeline if stage.status == StageStatus.PENDING), None)
    if runnable_stage is not None:
        label = STAGE_LABELS.get(runnable_stage.stage, runnable_stage.stage)
        return ProjectNextAction(
            action_type="run",
            stage=runnable_stage.stage,
            label=label,
            message=f"Możesz uruchomić etap {label}.",
            severity="info",
        )

    return ProjectNextAction(
        action_type="done",
        stage=None,
        label="Pipeline",
        message="Pipeline produkcyjny jest domknięty.",
        severity="info",
    )


def normalize_job_status(status_value: StageStatus) -> tuple[str, str]:
    if status_value == StageStatus.FAILED:
        return "failed", "failed"
    if status_value == StageStatus.RUNNING:
        return "running", "running"
    if status_value == StageStatus.QUEUED:
        return "queued", "queued"
    if status_value == StageStatus.PENDING:
        return "queued", "created"
    if status_value == StageStatus.NEEDS_REVIEW:
        return "succeeded", "awaiting_review"
    return "succeeded", "completed"


SSH_WORKER_RESOURCE = "ssh_default"
ADMIN_TOKEN_ENV = "STUDIO_ADMIN_TOKEN"


def create_app(projects_root: Path | None = None) -> FastAPI:
    configured_root = os.getenv("STUDIO_PROJECTS_ROOT")
    default_root = Path(configured_root) if configured_root else Path(__file__).resolve().parents[3] / "projects"
    storage = ProjectStorage(projects_root or default_root)
    mock_server = MockGpuServer()
    ssh_server = SshGenerationServer()

    def set_pipeline_stage(project: Project, stage: str, job: Job) -> None:
        for pipeline_stage in project.pipeline:
            if pipeline_stage.stage == stage:
                pipeline_stage.status = job.status
                pipeline_stage.job_id = job.id
                pipeline_stage.updated_at = utc_now()
                break

    def queue_position_for(job: Job) -> int:
        if job.adapter != "ssh" or job.status != StageStatus.QUEUED:
            return 0
        queued_jobs = storage.list_queued_ssh_jobs()
        for index, queued_job in enumerate(queued_jobs, start=1):
            if queued_job.id == job.id:
                return index
        return 0

    def require_admin_token(x_studio_admin_token: str | None) -> None:
        expected = os.getenv(ADMIN_TOKEN_ENV)
        if not expected:
            raise HTTPException(status_code=503, detail="Studio admin token is not configured")
        if x_studio_admin_token is None:
            raise HTTPException(status_code=401, detail="Invalid studio admin token")
        if not secrets.compare_digest(x_studio_admin_token, expected):
            raise HTTPException(status_code=403, detail="Invalid studio admin token")

    def recover_stale_worker_lock(resource_key: str) -> StaleLockRecoveryResult:
        lock = storage.get_worker_lock_raw(resource_key)
        if lock is None or not storage.is_worker_lock_expired(lock):
            return StaleLockRecoveryResult(status="idle", reason="no_lock_or_not_stale")

        locked_job = storage.get_job(lock.job_id)
        previous_status = locked_job.status.value if locked_job is not None else None
        if locked_job is not None and locked_job.status in {StageStatus.QUEUED, StageStatus.RUNNING}:
            locked_job.status = StageStatus.FAILED
            locked_job.message = "SSH worker lease expired; stale lock was recovered."
            locked_job.failure_reason = "stale_lock_recovered"
            locked_job.updated_at = utc_now()
            storage.save_job(locked_job)
            storage.append_job_event(locked_job, "stale_lock_recovered", locked_job.message)
            locked_project = storage.get_project(locked_job.project_id)
            if locked_project is not None:
                set_pipeline_stage(locked_project, locked_job.stage, locked_job)
                storage.save_project(locked_project)

        storage.delete_worker_lock(resource_key)
        return StaleLockRecoveryResult(
            status="recovered",
            recovered_job_id=lock.job_id,
            previous_status=previous_status,
            new_status=StageStatus.FAILED.value if locked_job is not None else None,
            failure_reason="stale_lock_recovered",
            released_lock_id=lock.lock_id,
        )

    def execute_locked_ssh_job(job: Job, project: Project, profile: ServerProfile, lock_id: str) -> Job:
        job.status = StageStatus.RUNNING
        job.message = "SSH worker acquired; generating server artifacts."
        job.updated_at = utc_now()
        storage.save_job(job)
        storage.append_job_event(job, "ssh_started", "SSH worker acquired; server generation started.")
        set_pipeline_stage(project, job.stage, job)
        storage.save_project(project)
        try:
            remote_run = ssh_server.run_remote_pilot(project_id=job.project_id, brief=project.brief, stage=job.stage, profile=profile, job_id=job.id)
            current_lock = storage.get_worker_lock_raw(SSH_WORKER_RESOURCE)
            if current_lock is None or current_lock.job_id != job.id or current_lock.lock_id != lock_id or current_lock.attempt_id != job.attempt_id:
                storage.append_job_event(job, "late_worker_completion_ignored", "Worker completion ignored because the lock owner no longer matches.")
                return storage.get_job(job.id) or job
            storage.save_remote_pilot_run(job.project_id, remote_run)
            storage.append_job_event(job, "artifact_saved", "Server output manifest and artifacts were recorded.")
            job.status = StageStatus.FAILED if remote_run.status == "failed" else StageStatus.NEEDS_REVIEW if job.stage in HUMAN_REVIEW_STAGES else StageStatus.COMPLETED
            job.message = remote_run.message
            job.updated_at = remote_run.updated_at
        except Exception as exc:
            job.status = StageStatus.FAILED
            job.message = str(exc) or "SSH worker failed."
            job.updated_at = utc_now()
            storage.append_job_event(job, "failed", job.message)
        storage.save_job(job)
        if job.status != StageStatus.FAILED:
            storage.append_job_event(job, "completed", job.message)
        set_pipeline_stage(project, job.stage, job)
        storage.save_project(project)
        return job

    def dispatch_next_ssh_job(trigger: str = "manual", drain_remaining: bool = False, depth: int = 0) -> DispatchNextResult:
        recover_stale_worker_lock(SSH_WORKER_RESOURCE)
        profile = storage.get_server_profile()
        if profile is None or profile.mode != "ssh":
            return DispatchNextResult(status="idle", reason="ssh_profile_required")
        queued_job = storage.next_queued_ssh_job()
        if queued_job is None:
            return DispatchNextResult(status="idle", reason="no_queued_jobs_or_lock_busy")
        project = storage.get_project(queued_job.project_id)
        if project is None:
            return DispatchNextResult(status="idle", reason="project_not_found")
        lock = storage.acquire_worker_lock(SSH_WORKER_RESOURCE, queued_job.id, queued_job.attempt_id)
        if lock is None:
            return DispatchNextResult(status="idle", reason="no_queued_jobs_or_lock_busy")

        previous_status = queued_job.status.value
        storage.append_job_event(queued_job, "lock_acquired", f"Worker lock acquired by {trigger} dispatch.")
        try:
            dispatched_job = execute_locked_ssh_job(queued_job, project, profile, lock.lock_id)
        finally:
            storage.release_worker_lock(SSH_WORKER_RESOURCE, queued_job.id)
            storage.append_job_event(queued_job, "lock_released", "Worker lock released.")

        if drain_remaining and depth < 10:
            storage.append_job_event(dispatched_job, "auto_drain_triggered", "Dispatcher checked the next queued SSH job.")
            dispatch_next_ssh_job(trigger="auto_drain", drain_remaining=True, depth=depth + 1)

        return DispatchNextResult(
            status="dispatched",
            job_id=dispatched_job.id,
            previous_status=previous_status,
            new_status=dispatched_job.status.value,
            queue_position=queue_position_for(dispatched_job),
            runner=GenerationRunnerState(mode="single_flight", resource=SSH_WORKER_RESOURCE, state="released", trigger=trigger, attempt_id=dispatched_job.attempt_id),
        )

    app = FastAPI(title="AI Kids Music Studio API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3010",
            "http://127.0.0.1:3010",
            "http://localhost:3020",
            "http://127.0.0.1:3020",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "adapter": mock_server.adapter}

    @app.get("/api/projects", response_model=list[Project])
    def list_projects() -> list[Project]:
        return storage.list_projects()

    @app.get("/api/stages/catalog", response_model=list[StageCatalogItem])
    def list_stage_catalog() -> list[StageCatalogItem]:
        return [
            StageCatalogItem(
                stage=stage,
                label=STAGE_LABELS.get(stage, stage),
                display_name=STAGE_DISPLAY_CATALOG[stage]["display_name"],
                future_stage=STAGE_DISPLAY_CATALOG[stage]["future_stage"],
                description=STAGE_DISPLAY_CATALOG[stage]["description"],
            )
            for stage in PIPELINE_STAGES
        ]

    @app.get("/api/series", response_model=list[SeriesBible])
    def list_series() -> list[SeriesBible]:
        return storage.list_series()

    @app.post("/api/series", response_model=SeriesBible, status_code=status.HTTP_201_CREATED)
    def create_series(series_input: SeriesBibleInput) -> SeriesBible:
        if series_input.target_age_min > series_input.target_age_max:
            raise HTTPException(status_code=422, detail="target_age_min must be less than or equal to target_age_max")
        return storage.create_series(series_input)

    @app.get("/api/series/{series_id}", response_model=SeriesBible)
    def get_series(series_id: str) -> SeriesBible:
        series = storage.get_series(series_id)
        if series is None:
            raise HTTPException(status_code=404, detail="Series not found")
        return series

    @app.put("/api/series/{series_id}", response_model=SeriesBible)
    def update_series(series_id: str, series_input: SeriesBibleInput) -> SeriesBible:
        existing = storage.get_series(series_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Series not found")
        if series_input.target_age_min > series_input.target_age_max:
            raise HTTPException(status_code=422, detail="target_age_min must be less than or equal to target_age_max")
        series = SeriesBible(id=series_id, created_at=existing.created_at, updated_at=utc_now(), **series_input.model_dump())
        return storage.save_series(series)

    @app.post("/api/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
    def create_project(brief_input: BriefInput) -> Project:
        project = create_project_from_brief(brief_input)
        return storage.save_project(project)

    @app.get("/api/projects/{project_id}", response_model=Project)
    def get_project(project_id: str) -> Project:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    @app.put("/api/projects/{project_id}/series", response_model=Project)
    def link_project_series(project_id: str, link_input: ProjectSeriesLinkInput) -> Project:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        series = storage.get_series(link_input.series_id)
        if series is None:
            raise HTTPException(status_code=404, detail="Series not found")
        project.series_id = series.id
        if project.episode_spec is not None:
            project.episode_spec.series_id = series.id
            project.episode_spec.updated_at = utc_now()
        return storage.save_project(project)

    @app.get("/api/projects/{project_id}/episode-spec", response_model=EpisodeSpec)
    def get_episode_spec(project_id: str) -> EpisodeSpec:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.episode_spec is None:
            raise HTTPException(status_code=404, detail="Episode spec not found")
        return project.episode_spec

    @app.put("/api/projects/{project_id}/episode-spec", response_model=EpisodeSpec)
    def save_episode_spec(project_id: str, spec_input: EpisodeSpecInput) -> EpisodeSpec:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if spec_input.target_age_min is not None and spec_input.target_age_max is not None:
            if spec_input.target_age_min > spec_input.target_age_max:
                raise HTTPException(status_code=422, detail="target_age_min must be less than or equal to target_age_max")
        now = utc_now()
        created_at = project.episode_spec.created_at if project.episode_spec is not None else now
        spec = EpisodeSpec(
            project_id=project_id,
            series_id=project.series_id,
            approval_status="draft",
            approved_at=None,
            approved_by=None,
            approval_note="",
            created_at=created_at,
            updated_at=now,
            **spec_input.model_dump(),
        )
        project.episode_spec = spec
        storage.save_project(project)
        return spec

    @app.post("/api/projects/{project_id}/episode-spec/approve", response_model=Project)
    def approve_episode_spec(project_id: str, approval_input: StageApprovalInput) -> Project:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.episode_spec is None:
            raise HTTPException(status_code=404, detail="Episode spec not found")
        now = utc_now()
        project.episode_spec.approval_status = "approved"
        project.episode_spec.approved_at = now
        project.episode_spec.approved_by = "operator"
        project.episode_spec.approval_note = approval_input.note
        project.episode_spec.updated_at = now
        return storage.save_project(project)

    @app.get("/api/projects/{project_id}/jobs", response_model=list[Job])
    def list_project_jobs(project_id: str) -> list[Job]:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return storage.list_jobs(project_id)

    @app.get("/api/projects/{project_id}/approvals", response_model=list[StageApproval])
    def list_project_approvals(project_id: str) -> list[StageApproval]:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return storage.list_stage_approvals(project_id)

    @app.get("/api/projects/{project_id}/anti-repetition", response_model=AntiRepetitionReport)
    def get_anti_repetition_report(project_id: str) -> AntiRepetitionReport:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        report = storage.get_anti_repetition_report(project_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Anti-repetition report not found")
        return report

    @app.post("/api/projects/{project_id}/anti-repetition/run", response_model=AntiRepetitionReport)
    def run_anti_repetition_report(project_id: str) -> AntiRepetitionReport:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.series_id is None:
            raise HTTPException(status_code=409, detail="Project must be linked to a series first")
        if project.episode_spec is None:
            raise HTTPException(status_code=409, detail="Project must have an episode spec first")

        candidate_projects = [
            candidate
            for candidate in storage.list_projects()
            if candidate.id != project.id and candidate.series_id == project.series_id and candidate.episode_spec is not None
        ]
        report = build_anti_repetition_report(
            project,
            candidate_projects,
            current_lyrics=storage.get_lyrics(project_id),
            current_storyboard=storage.get_storyboard(project_id),
            other_lyrics_by_project={candidate.id: storage.get_lyrics(candidate.id) for candidate in candidate_projects},
            other_storyboard_by_project={candidate.id: storage.get_storyboard(candidate.id) for candidate in candidate_projects},
        )
        return storage.save_anti_repetition_report(project_id, report)

    @app.get("/api/projects/{project_id}/next-action", response_model=ProjectNextAction)
    def read_project_next_action(project_id: str) -> ProjectNextAction:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return get_project_next_action(project, storage.get_anti_repetition_report(project_id))

    @app.post("/api/server/test-connection")
    def test_server_connection():
        profile = storage.get_server_profile()
        if profile is not None and profile.mode == "ssh":
            return ssh_server.test_connection(profile)
        return mock_server.test_connection(profile)

    @app.get("/api/server/profile", response_model=ServerProfile)
    def get_server_profile() -> ServerProfile:
        profile = storage.get_server_profile()
        if profile is None:
            raise HTTPException(status_code=404, detail="Server profile not found")
        return profile

    @app.put("/api/server/profile", response_model=ServerProfile)
    def save_server_profile(profile_input: ServerProfileInput) -> ServerProfile:
        return storage.save_server_profile(profile_input)

    @app.get("/api/projects/{project_id}/remote-pilot")
    def get_remote_pilot(project_id: str):
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Remote pilot endpoint is retired; use project jobs instead")

    @app.post("/api/projects/{project_id}/remote-pilot")
    def run_remote_pilot(project_id: str):
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Remote pilot endpoint is retired; use project jobs instead")

    @app.post("/api/projects/{project_id}/jobs/{stage}", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
    def submit_job(project_id: str, stage: str) -> Job:
        if stage not in PIPELINE_STAGES:
            raise HTTPException(status_code=400, detail="Unknown pipeline stage")
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        stage_index = PIPELINE_STAGES.index(stage)
        if stage_index > 0:
            previous_stage_name = PIPELINE_STAGES[stage_index - 1]
            previous_stage = next(item for item in project.pipeline if item.stage == previous_stage_name)
            if previous_stage.status != StageStatus.COMPLETED:
                raise HTTPException(
                    status_code=409,
                    detail=f"Previous stage {previous_stage_name} must be completed first",
                )

        profile = storage.get_server_profile()
        if profile is not None and profile.mode == "ssh":
            job = Job(
                id=f"remote_{uuid4().hex[:12]}",
                project_id=project_id,
                stage=stage,
                status=StageStatus.QUEUED,
                adapter="ssh",
                message="Waiting for SSH worker slot.",
                attempt_id=f"attempt_{uuid4().hex[:12]}",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            storage.save_job(job)
            storage.append_job_event(job, "queued", "SSH job queued for the single-flight worker.")
            set_pipeline_stage(project, stage, job)
            storage.save_project(project)
            dispatch_next_ssh_job(trigger="auto_drain", drain_remaining=True)
            job = storage.get_job(job.id) or job
        else:
            job = mock_server.submit_job(project_id=project_id, stage=stage)
            storage.save_job(job)
            if stage == "lyrics.generate":
                storage.save_lyrics(project_id, mock_server.generate_lyrics(project.brief))
            if stage == "storyboard.generate":
                storage.save_storyboard(project_id, mock_server.generate_storyboard(project.brief, storage.get_lyrics(project_id)))
            if stage == "keyframes.generate":
                storage.save_keyframes(project_id, mock_server.generate_keyframes(project.brief, storage.get_storyboard(project_id)))
            if stage == "video.scenes.generate":
                storage.save_video_scenes(project_id, mock_server.generate_video_scenes(project.brief, storage.get_keyframes(project_id)))
            if stage == "render.full_episode":
                storage.save_full_episode(project_id, mock_server.generate_full_episode(project.brief, storage.get_video_scenes(project_id)))
            if stage == "render.reels":
                storage.save_reels(project_id, mock_server.generate_reels(project.brief, storage.get_full_episode(project_id)))
            if stage == "quality.compliance_report":
                storage.save_compliance_report(
                    project_id,
                    mock_server.generate_compliance_report(project.brief, storage.get_full_episode(project_id), storage.get_reels(project_id)),
                )
            if stage == "publish.prepare_package":
                storage.save_publish_package(
                    project_id,
                    mock_server.generate_publish_package(
                        project.brief,
                        storage.get_full_episode(project_id),
                        storage.get_reels(project_id),
                        storage.get_compliance_report(project_id),
                    ),
                )
        set_pipeline_stage(project, stage, job)
        storage.save_project(project)
        return job

    @app.post("/api/jobs/dispatch-next", response_model=DispatchNextResult)
    def dispatch_next_job(dispatch_input: DispatchNextInput, x_studio_admin_token: str | None = Header(default=None)) -> DispatchNextResult:
        require_admin_token(x_studio_admin_token)
        if dispatch_input.adapter != "ssh" or dispatch_input.resource != SSH_WORKER_RESOURCE:
            return DispatchNextResult(status="idle", reason="unsupported_resource")
        return dispatch_next_ssh_job(trigger="manual", drain_remaining=True)

    @app.post("/api/jobs/locks/heartbeat", response_model=LockHeartbeatResult)
    def heartbeat_worker_lock(heartbeat_input: LockHeartbeatInput, x_studio_admin_token: str | None = Header(default=None)) -> LockHeartbeatResult:
        require_admin_token(x_studio_admin_token)
        if heartbeat_input.adapter != "ssh" or heartbeat_input.resource_key != SSH_WORKER_RESOURCE:
            return LockHeartbeatResult(status="rejected", reason="unsupported_resource")
        recover_stale_worker_lock(SSH_WORKER_RESOURCE)
        lock = storage.heartbeat_worker_lock(
            heartbeat_input.resource_key,
            heartbeat_input.job_id,
            heartbeat_input.lock_id,
            heartbeat_input.attempt_id,
        )
        if lock is None:
            return LockHeartbeatResult(status="rejected", reason="lock_owner_mismatch")
        job = storage.get_job(heartbeat_input.job_id)
        if job is not None:
            storage.append_job_event(job, "lock_heartbeat", "SSH worker lease renewed.")
        return LockHeartbeatResult(status="renewed", heartbeat_at=lock.heartbeat_at, lease_expires_at=lock.lease_expires_at)

    @app.post("/api/jobs/locks/recover-stale", response_model=StaleLockRecoveryResult)
    def recover_stale_lock(recovery_input: StaleLockRecoveryInput, x_studio_admin_token: str | None = Header(default=None)) -> StaleLockRecoveryResult:
        require_admin_token(x_studio_admin_token)
        if recovery_input.adapter != "ssh" or recovery_input.resource_key != SSH_WORKER_RESOURCE:
            return StaleLockRecoveryResult(status="idle", reason="unsupported_resource")
        result = recover_stale_worker_lock(recovery_input.resource_key)
        if result.status == "recovered":
            result.dispatched_next = dispatch_next_ssh_job(trigger="auto_drain", drain_remaining=True)
        return result

    @app.get("/api/queue/ssh-default", response_model=WorkerQueueStatus)
    def get_ssh_queue_status() -> WorkerQueueStatus:
        recover_stale_worker_lock(SSH_WORKER_RESOURCE)
        queued_jobs = storage.list_queued_ssh_jobs()
        lock = storage.get_worker_lock(SSH_WORKER_RESOURCE)
        return WorkerQueueStatus(
            resource=SSH_WORKER_RESOURCE,
            adapter="ssh",
            queued_count=len(queued_jobs),
            queued_job_ids=[job.id for job in queued_jobs],
            current_lock=lock,
            current_job_id=lock.job_id if lock else None,
            oldest_queued_job_id=queued_jobs[0].id if queued_jobs else None,
        )

    @app.get("/api/jobs/{job_id}/events", response_model=list[JobEvent])
    def list_job_events(job_id: str, after: int = 0) -> list[JobEvent]:
        job = storage.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return storage.list_job_events(job_id, after=after)

    @app.get("/api/projects/{project_id}/jobs/{job_id}/artifacts", response_model=list[GenerationArtifact])
    def list_job_artifacts(project_id: str, job_id: str) -> list[GenerationArtifact]:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        run = storage.get_remote_pilot_run(project_id, job_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Remote job not found")
        return run.artifacts

    @app.get("/api/projects/{project_id}/jobs/{job_id}/log")
    def get_job_log(project_id: str, job_id: str) -> dict[str, list[str] | str]:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        run = storage.get_remote_pilot_run(project_id, job_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Remote job not found")
        profile = storage.get_server_profile()
        if profile is not None and profile.mode == "ssh":
            log_text = ssh_server.fetch_log(profile, run)
            return {"job_id": job_id, "log": log_text, "lines": log_text.splitlines()}
        return {"job_id": job_id, "log": "\n".join(run.logs), "lines": run.logs}

    @app.get("/api/projects/{project_id}/jobs/{job_id}/artifacts/{artifact_id}")
    def get_job_artifact(project_id: str, job_id: str, artifact_id: str) -> Response:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        run = storage.get_remote_pilot_run(project_id, job_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Remote job not found")
        profile = storage.get_server_profile()
        if profile is None or profile.mode != "ssh":
            raise HTTPException(status_code=409, detail="SSH server profile is required to read server artifacts")
        try:
            artifact, content = ssh_server.fetch_artifact(profile, run, artifact_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Artifact not found") from None
        except ValueError:
            raise HTTPException(status_code=502, detail="Artifact checksum mismatch") from None
        return Response(
            content=content,
            media_type=artifact.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.filename}"',
                "X-Artifact-SHA256": artifact.sha256,
            },
        )

    @app.post("/api/projects/{project_id}/stages/{stage}/approve", response_model=Project)
    def approve_stage(project_id: str, stage: str, approval_input: StageApprovalInput) -> Project:
        if stage not in PIPELINE_STAGES:
            raise HTTPException(status_code=400, detail="Unknown pipeline stage")
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        pipeline_stage = next((item for item in project.pipeline if item.stage == stage), None)
        if pipeline_stage is None:
            raise HTTPException(status_code=400, detail="Unknown pipeline stage")
        if pipeline_stage.status != StageStatus.NEEDS_REVIEW:
            raise HTTPException(status_code=409, detail="Stage is not waiting for review")

        now = utc_now()
        pipeline_stage.status = StageStatus.COMPLETED
        pipeline_stage.updated_at = now
        storage.save_stage_approval(
            StageApproval(
                id=f"approval_{stage.replace('.', '_')}_{now}",
                project_id=project_id,
                stage=stage,
                status="completed",
                note=approval_input.note,
                approved_at=now,
            )
        )
        return storage.save_project(project)

    def build_generation_job_detail(job: Job) -> GenerationJobDetail:
        normalized_status, phase = normalize_job_status(job.status)
        queue_position = queue_position_for(job)
        runner = None
        if job.adapter == "ssh":
            lock = storage.get_worker_lock_raw(SSH_WORKER_RESOURCE)
            if job.status == StageStatus.QUEUED:
                phase = "waiting_for_worker"
                runner = GenerationRunnerState(mode="single_flight", resource=SSH_WORKER_RESOURCE, state="waiting", attempt_id=job.attempt_id)
            elif job.status == StageStatus.RUNNING:
                phase = "generating_artifact"
                runner = GenerationRunnerState(
                    mode="single_flight",
                    resource=SSH_WORKER_RESOURCE,
                    state="acquired",
                    lock_id=lock.lock_id if lock and lock.job_id == job.id else None,
                    attempt_id=job.attempt_id,
                    heartbeat_at=lock.heartbeat_at if lock and lock.job_id == job.id else None,
                    lease_expires_at=lock.lease_expires_at if lock and lock.job_id == job.id else None,
                )
            else:
                runner = GenerationRunnerState(mode="single_flight", resource=SSH_WORKER_RESOURCE, state="released", attempt_id=job.attempt_id)
        run = storage.get_remote_pilot_run(job.project_id, job.id) if job.adapter == "ssh" else None
        artifacts = [
            GenerationArtifactView(
                **artifact.model_dump(),
                download_url=f"/api/projects/{job.project_id}/jobs/{job.id}/artifacts/{artifact.artifact_id}",
            )
            for artifact in (run.artifacts if run is not None else [])
        ]
        error = {"code": "runner_failed", "message": job.message} if normalized_status == "failed" else None
        finished_at = job.updated_at if normalized_status in {"succeeded", "failed", "cancelled"} else None
        return GenerationJobDetail(
            id=job.id,
            job_id=job.id,
            project_id=job.project_id,
            stage=job.stage,
            status=normalized_status,
            phase=phase,
            message=job.message,
            adapter=job.adapter,
            preview=run.preview if run is not None else None,
            artifacts=artifacts,
            log_url=f"/api/projects/{job.project_id}/jobs/{job.id}/log" if run is not None else None,
            error=error,
            attempt_id=job.attempt_id,
            failure_reason=job.failure_reason,
            queue_position=queue_position,
            runner=runner,
            created_at=job.created_at,
            started_at=job.created_at if job.adapter == "ssh" and normalized_status != "queued" else None,
            finished_at=finished_at,
            updated_at=job.updated_at,
        )

    @app.get("/api/jobs/{job_id}", response_model=GenerationJobDetail)
    def get_job(job_id: str) -> GenerationJobDetail:
        job = storage.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return build_generation_job_detail(job)

    @app.get("/api/projects/{project_id}/artifacts/lyrics", response_model=LyricsArtifact)
    def get_lyrics_artifact(project_id: str) -> LyricsArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        lyrics = storage.get_lyrics(project_id)
        if lyrics is None:
            raise HTTPException(status_code=404, detail="Lyrics artifact not found")
        return lyrics

    @app.get("/api/projects/{project_id}/artifacts/storyboard", response_model=StoryboardArtifact)
    def get_storyboard_artifact(project_id: str) -> StoryboardArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        storyboard = storage.get_storyboard(project_id)
        if storyboard is None:
            raise HTTPException(status_code=404, detail="Storyboard artifact not found")
        return storyboard

    @app.get("/api/projects/{project_id}/artifacts/keyframes", response_model=KeyframesArtifact)
    def get_keyframes_artifact(project_id: str) -> KeyframesArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        keyframes = storage.get_keyframes(project_id)
        if keyframes is None:
            raise HTTPException(status_code=404, detail="Keyframes artifact not found")
        return keyframes

    @app.get("/api/projects/{project_id}/artifacts/video-scenes", response_model=VideoScenesArtifact)
    def get_video_scenes_artifact(project_id: str) -> VideoScenesArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        video_scenes = storage.get_video_scenes(project_id)
        if video_scenes is None:
            raise HTTPException(status_code=404, detail="Video scenes artifact not found")
        return video_scenes

    @app.get("/api/projects/{project_id}/artifacts/full-episode", response_model=FullEpisodeArtifact)
    def get_full_episode_artifact(project_id: str) -> FullEpisodeArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        episode = storage.get_full_episode(project_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="Full episode artifact not found")
        return episode

    @app.get("/api/projects/{project_id}/artifacts/reels", response_model=ReelsArtifact)
    def get_reels_artifact(project_id: str) -> ReelsArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        reels = storage.get_reels(project_id)
        if reels is None:
            raise HTTPException(status_code=404, detail="Reels artifact not found")
        return reels

    @app.get("/api/projects/{project_id}/artifacts/compliance-report", response_model=ComplianceReportArtifact)
    def get_compliance_report_artifact(project_id: str) -> ComplianceReportArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        report = storage.get_compliance_report(project_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Compliance report artifact not found")
        return report

    @app.get("/api/projects/{project_id}/artifacts/publish-package", response_model=PublishPackageArtifact)
    def get_publish_package_artifact(project_id: str) -> PublishPackageArtifact:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        package = storage.get_publish_package(project_id)
        if package is None:
            raise HTTPException(status_code=404, detail="Publish package artifact not found")
        return package

    @app.get("/api/projects/{project_id}/artifacts", response_model=list[ArtifactInventoryItem])
    def list_project_artifacts(project_id: str) -> list[ArtifactInventoryItem]:
        project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return storage.list_artifacts(project_id)

    return app


app = create_app()
