import json
from pathlib import Path

from .models import ComplianceReportArtifact, FullEpisodeArtifact, Job, KeyframesArtifact, LyricsArtifact, Project, PublishPackageArtifact, ReelsArtifact, ServerProfile, ServerProfileInput, StageApproval, StoryboardArtifact, VideoScenesArtifact, utc_now


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

    def save_storyboard(self, project_id: str, storyboard: StoryboardArtifact) -> StoryboardArtifact:
        (self.project_dir(project_id) / "storyboard.json").write_text(
            json.dumps(storyboard.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return storyboard

    def get_storyboard(self, project_id: str) -> StoryboardArtifact | None:
        storyboard_file = self.project_dir(project_id) / "storyboard.json"
        if not storyboard_file.exists():
            return None
        return StoryboardArtifact.model_validate_json(storyboard_file.read_text(encoding="utf-8"))

    def save_keyframes(self, project_id: str, keyframes: KeyframesArtifact) -> KeyframesArtifact:
        (self.project_dir(project_id) / "keyframes.json").write_text(
            json.dumps(keyframes.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return keyframes

    def get_keyframes(self, project_id: str) -> KeyframesArtifact | None:
        keyframes_file = self.project_dir(project_id) / "keyframes.json"
        if not keyframes_file.exists():
            return None
        return KeyframesArtifact.model_validate_json(keyframes_file.read_text(encoding="utf-8"))

    def save_video_scenes(self, project_id: str, video_scenes: VideoScenesArtifact) -> VideoScenesArtifact:
        (self.project_dir(project_id) / "video-scenes.json").write_text(
            json.dumps(video_scenes.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return video_scenes

    def get_video_scenes(self, project_id: str) -> VideoScenesArtifact | None:
        video_scenes_file = self.project_dir(project_id) / "video-scenes.json"
        if not video_scenes_file.exists():
            return None
        return VideoScenesArtifact.model_validate_json(video_scenes_file.read_text(encoding="utf-8"))

    def save_full_episode(self, project_id: str, episode: FullEpisodeArtifact) -> FullEpisodeArtifact:
        (self.project_dir(project_id) / "full-episode.json").write_text(
            json.dumps(episode.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return episode

    def get_full_episode(self, project_id: str) -> FullEpisodeArtifact | None:
        episode_file = self.project_dir(project_id) / "full-episode.json"
        if not episode_file.exists():
            return None
        return FullEpisodeArtifact.model_validate_json(episode_file.read_text(encoding="utf-8"))

    def save_reels(self, project_id: str, reels: ReelsArtifact) -> ReelsArtifact:
        (self.project_dir(project_id) / "reels.json").write_text(
            json.dumps(reels.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return reels

    def get_reels(self, project_id: str) -> ReelsArtifact | None:
        reels_file = self.project_dir(project_id) / "reels.json"
        if not reels_file.exists():
            return None
        return ReelsArtifact.model_validate_json(reels_file.read_text(encoding="utf-8"))

    def save_compliance_report(self, project_id: str, report: ComplianceReportArtifact) -> ComplianceReportArtifact:
        (self.project_dir(project_id) / "compliance-report.json").write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report

    def get_compliance_report(self, project_id: str) -> ComplianceReportArtifact | None:
        report_file = self.project_dir(project_id) / "compliance-report.json"
        if not report_file.exists():
            return None
        return ComplianceReportArtifact.model_validate_json(report_file.read_text(encoding="utf-8"))

    def save_publish_package(self, project_id: str, package: PublishPackageArtifact) -> PublishPackageArtifact:
        (self.project_dir(project_id) / "publish-package.json").write_text(
            json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return package

    def get_publish_package(self, project_id: str) -> PublishPackageArtifact | None:
        package_file = self.project_dir(project_id) / "publish-package.json"
        if not package_file.exists():
            return None
        return PublishPackageArtifact.model_validate_json(package_file.read_text(encoding="utf-8"))

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
