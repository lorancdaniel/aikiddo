from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class StageStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"


PIPELINE_STAGES = [
    "brief.generate",
    "lyrics.generate",
    "characters.import_or_approve",
    "audio.generate_or_import",
    "storyboard.generate",
    "keyframes.generate",
    "video.scenes.generate",
    "render.full_episode",
    "render.reels",
    "quality.compliance_report",
    "publish.prepare_package",
]

HUMAN_REVIEW_STAGES = {
    "brief.generate",
    "lyrics.generate",
    "characters.import_or_approve",
    "keyframes.generate",
    "video.scenes.generate",
    "quality.compliance_report",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BriefInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=160)
    age_range: str = Field(min_length=1, max_length=40)
    emotional_tone: str = Field(min_length=1, max_length=80)
    educational_goal: str = Field(min_length=1, max_length=240)
    characters: list[str] = Field(default_factory=list)


class Brief(BriefInput):
    id: str
    created_at: str
    forbidden_motifs: list[str] = Field(
        default_factory=lambda: [
            "violence",
            "fear-based pressure",
            "unsafe behavior",
            "endless-watch prompts",
        ]
    )


class PipelineStage(BaseModel):
    stage: str
    status: StageStatus = StageStatus.PENDING
    job_id: str | None = None
    updated_at: str


class Project(BaseModel):
    id: str
    title: str
    brief: Brief
    pipeline: list[PipelineStage]
    created_at: str
    updated_at: str


class Job(BaseModel):
    id: str
    project_id: str
    stage: str
    status: StageStatus
    adapter: Literal["mock"]
    message: str
    created_at: str
    updated_at: str


class ServerConnection(BaseModel):
    mode: Literal["mock"]
    reachable: bool
    message: str


def create_project_from_brief(brief_input: BriefInput) -> Project:
    now = utc_now()
    project_id = f"project_{uuid4().hex[:12]}"
    brief = Brief(id=f"brief_{uuid4().hex[:12]}", created_at=now, **brief_input.model_dump())
    pipeline = [
        PipelineStage(
            stage=stage,
            status=StageStatus.NEEDS_REVIEW if stage == "brief.generate" else StageStatus.PENDING,
            updated_at=now,
        )
        for stage in PIPELINE_STAGES
    ]
    return Project(
        id=project_id,
        title=brief_input.title,
        brief=brief,
        pipeline=pipeline,
        created_at=now,
        updated_at=now,
    )
