from uuid import uuid4

from .models import HUMAN_REVIEW_STAGES, Job, ServerConnection, ServerProfile, StageStatus, utc_now


class MockGpuServer:
    adapter = "mock"

    def test_connection(self, profile: ServerProfile | None = None) -> ServerConnection:
        if profile is not None:
            message = f"Mock GPU server profile '{profile.label}' is ready for local development."
        else:
            message = "Mock GPU server is ready for local development."
        return ServerConnection(
            mode="mock",
            reachable=True,
            message=message,
        )

    def submit_job(self, project_id: str, stage: str) -> Job:
        now = utc_now()
        status = StageStatus.NEEDS_REVIEW if stage in HUMAN_REVIEW_STAGES else StageStatus.COMPLETED
        return Job(
            id=f"job_{uuid4().hex[:12]}",
            project_id=project_id,
            stage=stage,
            status=status,
            adapter="mock",
            message=f"Mock job for {stage} finished locally.",
            created_at=now,
            updated_at=now,
        )
