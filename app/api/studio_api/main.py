from pathlib import Path
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .mock_server import MockGpuServer
from .models import (
    BriefInput,
    Job,
    PIPELINE_STAGES,
    Project,
    ServerProfile,
    ServerProfileInput,
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

        job = mock_server.submit_job(project_id=project_id, stage=stage)
        storage.save_job(job)
        for pipeline_stage in project.pipeline:
            if pipeline_stage.stage == stage:
                pipeline_stage.status = job.status
                pipeline_stage.job_id = job.id
                pipeline_stage.updated_at = utc_now()
                break
        storage.save_project(project)
        return job

    @app.get("/api/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str) -> Job:
        job = storage.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    return app


app = create_app()
