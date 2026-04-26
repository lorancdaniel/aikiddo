import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import AntiRepetitionReport, ArtifactInventoryItem, ComplianceReportArtifact, FullEpisodeArtifact, Job, JobEvent, KeyframesArtifact, LyricsArtifact, Project, PublishPackageArtifact, ReelsArtifact, RemotePilotRun, SeriesBible, SeriesBibleInput, ServerProfile, ServerProfileInput, StageApproval, StageStatus, StoryboardArtifact, VideoScenesArtifact, WorkerLock, utc_now


ARTIFACT_MANIFESTS = [
    ("brief", "brief.json"),
    ("lyrics", "lyrics.json"),
    ("storyboard", "storyboard.json"),
    ("keyframes", "keyframes.json"),
    ("video_scenes", "video-scenes.json"),
    ("full_episode", "full-episode.json"),
    ("reels", "reels.json"),
    ("compliance_report", "compliance-report.json"),
    ("anti_repetition", "anti-repetition.json"),
    ("remote_pilot", "remote-pilot.json"),
    ("publish_package", "publish-package.json"),
]


def utc_now_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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

    def series_dir(self) -> Path:
        directory = self.studio_dir / "series"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_series(self, series: SeriesBible) -> SeriesBible:
        series.updated_at = utc_now()
        (self.series_dir() / f"{series.id}.json").write_text(
            json.dumps(series.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return series

    def create_series(self, series_input: SeriesBibleInput) -> SeriesBible:
        now = utc_now()
        series = SeriesBible(
            id=f"series_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            created_at=now,
            updated_at=now,
            **series_input.model_dump(),
        )
        return self.save_series(series)

    def list_series(self) -> list[SeriesBible]:
        directory = self.series_dir()
        series = [
            SeriesBible.model_validate_json(series_file.read_text(encoding="utf-8"))
            for series_file in sorted(directory.glob("*.json"))
        ]
        return sorted(series, key=lambda item: item.created_at, reverse=True)

    def get_series(self, series_id: str) -> SeriesBible | None:
        series_file = self.series_dir() / f"{series_id}.json"
        if not series_file.exists():
            return None
        return SeriesBible.model_validate_json(series_file.read_text(encoding="utf-8"))

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

    def list_jobs(self, project_id: str) -> list[Job]:
        jobs_dir = self.project_dir(project_id) / "jobs"
        if not jobs_dir.exists():
            return []
        jobs = [Job.model_validate_json(job_file.read_text(encoding="utf-8")) for job_file in sorted(jobs_dir.glob("*.json"))]
        return sorted(jobs, key=lambda job: job.created_at)

    def job_events_file(self, job: Job) -> Path:
        return self.project_dir(job.project_id) / "jobs" / f"{job.id}.events.jsonl"

    def append_job_event(self, job: Job, event: str, message: str) -> JobEvent:
        events = self.list_job_events(job.id)
        job_event = JobEvent(
            cursor=len(events) + 1,
            job_id=job.id,
            event=event,
            message=message,
            created_at=utc_now(),
        )
        events_file = self.job_events_file(job)
        events_file.parent.mkdir(parents=True, exist_ok=True)
        with events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(job_event.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return job_event

    def list_job_events(self, job_id: str, after: int = 0) -> list[JobEvent]:
        job = self.get_job(job_id)
        if job is None:
            return []
        events_file = self.job_events_file(job)
        if not events_file.exists():
            return []
        events = [
            JobEvent.model_validate_json(line)
            for line in events_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [event for event in events if event.cursor > after]

    def list_all_jobs(self) -> list[Job]:
        jobs = [
            Job.model_validate_json(job_file.read_text(encoding="utf-8"))
            for job_file in sorted(self.projects_root.glob("*/jobs/*.json"))
            if not job_file.name.endswith(".events.jsonl")
        ]
        return sorted(jobs, key=lambda job: job.created_at)

    def list_queued_ssh_jobs(self) -> list[Job]:
        return [job for job in self.list_all_jobs() if job.adapter == "ssh" and job.status == StageStatus.QUEUED]

    def next_queued_ssh_job(self) -> Job | None:
        queued_jobs = self.list_queued_ssh_jobs()
        return queued_jobs[0] if queued_jobs else None

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

    def save_anti_repetition_report(self, project_id: str, report: AntiRepetitionReport) -> AntiRepetitionReport:
        (self.project_dir(project_id) / "anti-repetition.json").write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report

    def get_anti_repetition_report(self, project_id: str) -> AntiRepetitionReport | None:
        report_file = self.project_dir(project_id) / "anti-repetition.json"
        if not report_file.exists():
            return None
        return AntiRepetitionReport.model_validate_json(report_file.read_text(encoding="utf-8"))

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

    def save_remote_pilot_run(self, project_id: str, run: RemotePilotRun) -> RemotePilotRun:
        remote_runs_dir = self.project_dir(project_id) / "remote-runs"
        remote_runs_dir.mkdir(parents=True, exist_ok=True)
        (remote_runs_dir / f"{run.id}.json").write_text(
            json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.project_dir(project_id) / "remote-pilot.json").write_text(
            json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run

    def get_remote_pilot_run(self, project_id: str, run_id: str | None = None) -> RemotePilotRun | None:
        if run_id is not None:
            run_file = self.project_dir(project_id) / "remote-runs" / f"{run_id}.json"
            if not run_file.exists():
                return None
            return RemotePilotRun.model_validate_json(run_file.read_text(encoding="utf-8"))
        run_file = self.project_dir(project_id) / "remote-pilot.json"
        if not run_file.exists():
            return None
        return RemotePilotRun.model_validate_json(run_file.read_text(encoding="utf-8"))

    def list_artifacts(self, project_id: str) -> list[ArtifactInventoryItem]:
        project_dir = self.project_dir(project_id)
        inventory: list[ArtifactInventoryItem] = []
        for artifact_type, file_name in ARTIFACT_MANIFESTS:
            artifact_file = project_dir / file_name
            updated_at = None
            if artifact_file.exists():
                updated_at = utc_now_from_timestamp(artifact_file.stat().st_mtime)
            inventory.append(
                ArtifactInventoryItem(
                    artifact_type=artifact_type,
                    file_name=file_name,
                    relative_path=f"projects/{project_id}/{file_name}",
                    available=artifact_file.exists(),
                    updated_at=updated_at,
                )
            )
        return [item for item in inventory if item.available]

    def get_job(self, job_id: str) -> Job | None:
        matches = list(self.projects_root.glob(f"*/jobs/{job_id}.json"))
        if not matches:
            return None
        return Job.model_validate_json(matches[0].read_text(encoding="utf-8"))

    def worker_locks_dir(self) -> Path:
        directory = self.studio_dir / "worker-locks"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def worker_lock_file(self, resource_key: str) -> Path:
        return self.worker_locks_dir() / f"{resource_key}.json"

    def get_worker_lock(self, resource_key: str) -> WorkerLock | None:
        lock = self.get_worker_lock_raw(resource_key)
        if lock is None:
            return None
        if parse_utc(lock.lease_expires_at) <= datetime.now(timezone.utc):
            return None
        return lock

    def get_worker_lock_raw(self, resource_key: str) -> WorkerLock | None:
        lock_file = self.worker_lock_file(resource_key)
        if not lock_file.exists():
            return None
        return WorkerLock.model_validate_json(lock_file.read_text(encoding="utf-8"))

    def is_worker_lock_expired(self, lock: WorkerLock) -> bool:
        return parse_utc(lock.lease_expires_at) <= datetime.now(timezone.utc)

    def delete_worker_lock(self, resource_key: str) -> None:
        self.worker_lock_file(resource_key).unlink(missing_ok=True)

    def acquire_worker_lock(self, resource_key: str, job_id: str, attempt_id: str | None = None, lease_seconds: int = 900) -> WorkerLock | None:
        existing = self.get_worker_lock(resource_key)
        if existing is not None:
            return None
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lock = WorkerLock(
            resource_key=resource_key,
            adapter="ssh",
            job_id=job_id,
            attempt_id=attempt_id,
            acquired_at=now,
            heartbeat_at=now,
            lease_expires_at=(now_dt + timedelta(seconds=lease_seconds)).isoformat(),
        )
        lock_file = self.worker_lock_file(resource_key)
        try:
            with lock_file.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(lock.model_dump(mode="json"), ensure_ascii=False, indent=2))
        except FileExistsError:
            return None
        return lock

    def heartbeat_worker_lock(
        self,
        resource_key: str,
        job_id: str,
        lock_id: str,
        attempt_id: str | None,
        lease_seconds: int = 900,
    ) -> WorkerLock | None:
        lock = self.get_worker_lock(resource_key)
        if lock is None:
            return None
        if lock.job_id != job_id or lock.lock_id != lock_id or lock.attempt_id != attempt_id:
            return None
        now_dt = datetime.now(timezone.utc)
        lock.heartbeat_at = now_dt.isoformat()
        lock.lease_expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        self.worker_lock_file(resource_key).write_text(
            json.dumps(lock.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return lock

    def release_worker_lock(self, resource_key: str, job_id: str) -> None:
        lock_file = self.worker_lock_file(resource_key)
        if not lock_file.exists():
            return
        lock = WorkerLock.model_validate_json(lock_file.read_text(encoding="utf-8"))
        if lock.job_id == job_id:
            lock_file.unlink(missing_ok=True)

    def save_stage_approval(self, approval: StageApproval) -> StageApproval:
        reviews_dir = self.project_dir(approval.project_id) / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        (reviews_dir / f"{approval.stage}.approval.json").write_text(
            json.dumps(approval.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return approval

    def list_stage_approvals(self, project_id: str) -> list[StageApproval]:
        reviews_dir = self.project_dir(project_id) / "reviews"
        if not reviews_dir.exists():
            return []
        approvals = [
            StageApproval.model_validate_json(approval_file.read_text(encoding="utf-8"))
            for approval_file in sorted(reviews_dir.glob("*.approval.json"))
        ]
        return sorted(approvals, key=lambda approval: approval.approved_at)

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
