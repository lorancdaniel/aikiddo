from uuid import uuid4

from .models import HUMAN_REVIEW_STAGES, Job, ServerConnection, StageStatus, utc_now


class MockGpuServer:
    adapter = "mock"

    def test_connection(self) -> ServerConnection:
        return ServerConnection(
            mode="mock",
            reachable=True,
            message="Mock GPU server is ready for local development.",
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
