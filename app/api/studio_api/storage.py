import json
from pathlib import Path

from .models import Job, LyricsArtifact, Project, ServerProfile, ServerProfileInput, StageApproval, utc_now


class ProjectStorage:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.studio_dir = self.projects_root / ".studio"

    def project_dir(self, project_id: str) -> Path:
        return self.projects_root / project_id

    def save_project(self, project: Project) -> Project:
        project.updated_at = utc_now()
        project_dir = self.project_dir(project.id)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "project.json").write_text(
            json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (project_dir / "brief.json").write_text(
            json.dumps(project.brief.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return project

    def list_projects(self) -> list[Project]:
        projects: list[Project] = []
        for project_file in sorted(self.projects_root.glob("*/project.json")):
            projects.append(Project.model_validate_json(project_file.read_text(encoding="utf-8")))
        return sorted(projects, key=lambda project: project.created_at, reverse=True)

    def get_project(self, project_id: str) -> Project | None:
        project_file = self.project_dir(project_id) / "project.json"
        if not project_file.exists():
            return None
        return Project.model_validate_json(project_file.read_text(encoding="utf-8"))

    def save_job(self, job: Job) -> Job:
        jobs_dir = self.project_dir(job.project_id) / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        (jobs_dir / f"{job.id}.json").write_text(
            json.dumps(job.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return job

    def save_lyrics(self, project_id: str, lyrics: LyricsArtifact) -> LyricsArtifact:
        (self.project_dir(project_id) / "lyrics.json").write_text(
            json.dumps(lyrics.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return lyrics

    def get_lyrics(self, project_id: str) -> LyricsArtifact | None:
        lyrics_file = self.project_dir(project_id) / "lyrics.json"
        if not lyrics_file.exists():
            return None
        return LyricsArtifact.model_validate_json(lyrics_file.read_text(encoding="utf-8"))

    def get_job(self, job_id: str) -> Job | None:
        matches = list(self.projects_root.glob(f"*/jobs/{job_id}.json"))
        if not matches:
            return None
        return Job.model_validate_json(matches[0].read_text(encoding="utf-8"))

    def save_stage_approval(self, approval: StageApproval) -> StageApproval:
        reviews_dir = self.project_dir(approval.project_id) / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        (reviews_dir / f"{approval.stage}.approval.json").write_text(
            json.dumps(approval.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return approval

    def save_server_profile(self, profile_input: ServerProfileInput) -> ServerProfile:
        self.studio_dir.mkdir(parents=True, exist_ok=True)
        profile = ServerProfile(updated_at=utc_now(), **profile_input.model_dump())
        (self.studio_dir / "server-profile.json").write_text(
            json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return profile

    def get_server_profile(self) -> ServerProfile | None:
        profile_file = self.studio_dir / "server-profile.json"
        if not profile_file.exists():
            return None
        return ServerProfile.model_validate_json(profile_file.read_text(encoding="utf-8"))
