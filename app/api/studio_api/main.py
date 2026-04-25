from pathlib import Path
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .anti_repetition import build_anti_repetition_report
from .mock_server import MockGpuServer
from .models import (
    AntiRepetitionReport,
    ArtifactInventoryItem,
    BriefInput,
    ComplianceReportArtifact,
    EpisodeSpec,
    EpisodeSpecInput,
    FullEpisodeArtifact,
    Job,
    KeyframesArtifact,
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
    StoryboardArtifact,
    VideoScenesArtifact,
    create_project_from_brief,
    utc_now,
)
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
        message="Pipeline mock jest domknięty.",
        severity="info",
    )


def create_app(projects_root: Path | None = None) -> FastAPI:
    configured_root = os.getenv("STUDIO_PROJECTS_ROOT")
    default_root = Path(configured_root) if configured_root else Path(__file__).resolve().parents[3] / "projects"
    storage = ProjectStorage(projects_root or default_root)
    mock_server = MockGpuServer()

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
        return mock_server.test_connection(storage.get_server_profile())

    @app.get("/api/server/profile", response_model=ServerProfile)
    def get_server_profile() -> ServerProfile:
        profile = storage.get_server_profile()
        if profile is None:
            raise HTTPException(status_code=404, detail="Server profile not found")
        return profile

    @app.put("/api/server/profile", response_model=ServerProfile)
    def save_server_profile(profile_input: ServerProfileInput) -> ServerProfile:
        return storage.save_server_profile(profile_input)

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
        for pipeline_stage in project.pipeline:
            if pipeline_stage.stage == stage:
                pipeline_stage.status = job.status
                pipeline_stage.job_id = job.id
                pipeline_stage.updated_at = utc_now()
                break
        storage.save_project(project)
        return job

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

    @app.get("/api/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str) -> Job:
        job = storage.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

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
