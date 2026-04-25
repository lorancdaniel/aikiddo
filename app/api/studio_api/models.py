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

STAGE_LABELS = {
    "brief.generate": "Brief",
    "lyrics.generate": "Tekst",
    "characters.import_or_approve": "Postacie",
    "audio.generate_or_import": "Audio",
    "storyboard.generate": "Storyboard",
    "keyframes.generate": "Keyframes",
    "video.scenes.generate": "Sceny",
    "render.full_episode": "Odcinek",
    "render.reels": "Rolki",
    "quality.compliance_report": "Kontrola",
    "publish.prepare_package": "Paczka",
}

HUMAN_REVIEW_STAGES = {
    "brief.generate",
    "lyrics.generate",
    "characters.import_or_approve",
    "storyboard.generate",
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


class LyricsArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    structure: list[str]
    chorus: list[str]
    verses: list[list[str]]
    rhythm_notes: list[str]
    safety_notes: list[str]
    created_at: str


class StoryboardScene(BaseModel):
    id: str
    duration_seconds: int
    lyric_anchor: str
    action: str
    visual_prompt: str
    camera: str
    safety_note: str


class StoryboardArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    scenes: list[StoryboardScene]
    safety_checks: list[str]
    created_at: str


class KeyframeFrame(BaseModel):
    id: str
    scene_id: str
    timestamp_seconds: int
    image_prompt: str
    composition: str
    palette: list[str]
    continuity_note: str


class KeyframesArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    frames: list[KeyframeFrame]
    consistency_notes: list[str]
    created_at: str


class VideoSceneClip(BaseModel):
    id: str
    scene_id: str
    source_keyframe_id: str
    duration_seconds: int
    motion_prompt: str
    camera_motion: str
    transition: str
    safety_note: str


class VideoScenesArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    scenes: list[VideoSceneClip]
    render_notes: list[str]
    created_at: str


class FullEpisodeArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    episode_slug: str
    duration_seconds: int
    scene_count: int
    output_path: str
    poster_frame: str
    audio_mix: str
    assembly_notes: list[str]
    created_at: str


class ReelClip(BaseModel):
    id: str
    source_episode_slug: str
    source_scene_ids: list[str]
    duration_seconds: int
    aspect_ratio: str
    hook: str
    output_path: str
    caption: str
    safety_note: str


class ReelsArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    reels: list[ReelClip]
    distribution_notes: list[str]
    created_at: str


class ComplianceCheck(BaseModel):
    id: str
    label: str
    status: Literal["pass", "review"]
    evidence: str


class ComplianceReportArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    overall_status: Literal["ready_for_human_review"]
    episode_output_path: str
    reel_output_paths: list[str]
    checks: list[ComplianceCheck]
    operator_notes: list[str]
    created_at: str


class PublishPackageArtifact(BaseModel):
    title: str
    topic: str
    age_range: str
    package_status: Literal["ready"]
    package_path: str
    episode_output_path: str
    reel_output_paths: list[str]
    included_manifests: list[str]
    publishing_metadata: dict[str, str]
    operator_checklist: list[str]
    created_at: str


class ArtifactInventoryItem(BaseModel):
    artifact_type: str
    file_name: str
    relative_path: str
    available: bool
    updated_at: str | None = None


class PipelineStage(BaseModel):
    stage: str
    status: StageStatus = StageStatus.PENDING
    job_id: str | None = None
    updated_at: str


class StageApprovalInput(BaseModel):
    note: str = Field(default="", max_length=500)


class StageApproval(BaseModel):
    id: str
    project_id: str
    stage: str
    status: Literal["completed"]
    note: str
    approved_at: str


class Project(BaseModel):
    id: str
    title: str
    brief: Brief
    pipeline: list[PipelineStage]
    created_at: str
    updated_at: str


class ProjectNextAction(BaseModel):
    action_type: Literal["approve", "run", "done"]
    stage: str | None
    label: str
    message: str


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


class ServerProfileInput(BaseModel):
    mode: Literal["mock", "ssh"] = "mock"
    label: str = Field(min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=180)
    username: str = Field(min_length=1, max_length=80)
    port: int = Field(ge=1, le=65535)
    remote_root: str = Field(min_length=1, max_length=240)
    ssh_key_path: str = Field(min_length=1, max_length=240)
    tailscale_name: str = Field(min_length=1, max_length=120)


class ServerProfile(ServerProfileInput):
    updated_at: str


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
