from pathlib import Path
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .mock_server import MockGpuServer
from .models import (
    BriefInput,
    ComplianceReportArtifact,
    FullEpisodeArtifact,
    Job,
    KeyframesArtifact,
    LyricsArtifact,
    PIPELINE_STAGES,
    Project,
    ReelsArtifact,
    ServerProfile,
    ServerProfileInput,
    StageApproval,
    StageApprovalInput,
    StageStatus,
    StoryboardArtifact,
    VideoScenesArtifact,
    create_project_from_brief,
    utc_now,
)
from .storage import ProjectStorage


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

    return app


app = create_app()
