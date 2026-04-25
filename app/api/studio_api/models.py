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

STAGE_DISPLAY_CATALOG = {
    "brief.generate": {
        "display_name": "Episode brief",
        "future_stage": "episode.spec",
        "description": "Operator brief for one publishable content unit.",
    },
    "lyrics.generate": {
        "display_name": "Lyrics",
        "future_stage": "lyrics.script_generate",
        "description": "Educational lyrics and script lines.",
    },
    "characters.import_or_approve": {
        "display_name": "Visual style sample",
        "future_stage": "visual.sample_generate",
        "description": "Project-level style sample that should eventually be inherited from a series bible.",
    },
    "audio.generate_or_import": {
        "display_name": "Song audio",
        "future_stage": "song.audio_generate",
        "description": "Generated or imported song audio.",
    },
    "storyboard.generate": {
        "display_name": "Timed storyboard",
        "future_stage": "storyboard.timed_generate",
        "description": "Scene plan aligned to the song structure.",
    },
    "keyframes.generate": {
        "display_name": "Visual samples",
        "future_stage": "visual.sample_generate",
        "description": "Representative frames for visual continuity review.",
    },
    "video.scenes.generate": {
        "display_name": "Scene renders",
        "future_stage": "scenes.render_generate",
        "description": "Rendered scene clips assembled from approved visual direction.",
    },
    "render.full_episode": {
        "display_name": "Primary video",
        "future_stage": "render.primary_video",
        "description": "Primary horizontal video output; full episodes move to a future compilation step.",
    },
    "render.reels": {
        "display_name": "Derivatives",
        "future_stage": "derivatives.generate",
        "description": "Shorts, reels, teasers, thumbnail variants, and companion assets.",
    },
    "quality.compliance_report": {
        "display_name": "Safety, quality & rights review",
        "future_stage": "safety_quality_rights_review",
        "description": "Human-readable readiness check for kids quality, rights, and platform risk.",
    },
    "publish.prepare_package": {
        "display_name": "Publish package",
        "future_stage": "publish.package_prepare",
        "description": "Metadata, manifests, and upload-ready publishing materials.",
    },
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


class AntiRepetitionSignals(BaseModel):
    title_similarity: float | None = None
    topic_similarity: float | None = None
    objective_similarity: float | None = None
    vocabulary_overlap: float | None = None
    lyrics_similarity: float | None = None
    storyboard_similarity: float | None = None


class AntiRepetitionMatch(BaseModel):
    project_id: str
    title: str
    score: float
    reasons: list[str]


class AntiRepetitionReport(BaseModel):
    id: str
    project_id: str
    series_id: str | None = None
    status: Literal["ok", "warning", "review_recommended", "blocker"]
    score: float
    compared_projects_count: int
    closest_matches: list[AntiRepetitionMatch]
    signals: AntiRepetitionSignals
    generated_at: str


class StageCatalogItem(BaseModel):
    stage: str
    label: str
    display_name: str
    future_stage: str
    description: str


class SeriesCharacter(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=80)
    visual_description: str = Field(min_length=1, max_length=500)
    personality: str = Field(min_length=1, max_length=240)
    voice_notes: str = Field(default="", max_length=240)


class SeriesBibleInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    status: Literal["draft", "active", "archived"] = "draft"
    target_age_min: int = Field(ge=0, le=18)
    target_age_max: int = Field(ge=0, le=18)
    primary_language: str = Field(min_length=2, max_length=16)
    secondary_language: str | None = Field(default=None, max_length=16)
    learning_domain: str = Field(min_length=1, max_length=80)
    series_premise: str = Field(min_length=1, max_length=600)
    main_characters: list[SeriesCharacter] = Field(default_factory=list)
    visual_style: str = Field(min_length=1, max_length=600)
    music_style: str = Field(min_length=1, max_length=320)
    voice_rules: str = Field(min_length=1, max_length=500)
    safety_rules: list[str] = Field(default_factory=list)
    forbidden_content: list[str] = Field(default_factory=list)
    thumbnail_rules: str = Field(default="", max_length=320)
    made_for_kids_default: bool = True


class SeriesBible(SeriesBibleInput):
    id: str
    created_at: str
    updated_at: str


class ProjectSeriesLinkInput(BaseModel):
    series_id: str


class LearningObjective(BaseModel):
    statement: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=80)
    vocabulary_terms: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class DerivativePlan(BaseModel):
    make_shorts: bool = True
    make_reels: bool = True
    make_parent_teacher_page: bool = True
    make_lyrics_page: bool = True


class EpisodeSpecInput(BaseModel):
    working_title: str = Field(min_length=1, max_length=160)
    topic: str = Field(min_length=1, max_length=160)
    target_age_min: int | None = Field(default=None, ge=0, le=18)
    target_age_max: int | None = Field(default=None, ge=0, le=18)
    learning_objective: LearningObjective
    format: Literal["song_video", "short", "compilation_seed", "lesson_clip"] = "song_video"
    target_duration_sec: int = Field(ge=15, le=3600)
    audience_context: Literal["home", "classroom", "both"] = "both"
    search_keywords: list[str] = Field(default_factory=list)
    hook_idea: str = Field(default="", max_length=500)
    derivative_plan: DerivativePlan = Field(default_factory=DerivativePlan)
    made_for_kids: bool = True
    risk_notes: str = Field(default="", max_length=700)


class EpisodeSpec(EpisodeSpecInput):
    project_id: str
    series_id: str | None = None
    approval_status: Literal["draft", "approved", "needs_changes"] = "draft"
    approved_at: str | None = None
    approved_by: str | None = None
    approval_note: str = ""
    created_at: str
    updated_at: str


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
    series_id: str | None = None
    episode_spec: EpisodeSpec | None = None
    pipeline: list[PipelineStage]
    created_at: str
    updated_at: str


class ProjectNextAction(BaseModel):
    action_type: Literal[
        "approve",
        "run",
        "done",
        "define_series",
        "complete_episode_spec",
        "approve_episode_spec",
        "run_anti_repetition_check",
        "fix_rejected_stage",
        "fix_repetition_risk",
        "complete_publish_package",
        "enter_performance_metrics",
    ]
    stage: str | None
    label: str
    message: str
    severity: Literal["info", "warning", "blocker"] = "info"


class Job(BaseModel):
    id: str
    project_id: str
    stage: str
    status: StageStatus
    adapter: Literal["mock", "ssh"]
    message: str
    created_at: str
    updated_at: str


class ServerConnection(BaseModel):
    mode: Literal["mock", "ssh"]
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


class RemotePilotInput(BaseModel):
    stage: str = Field(default="lyrics.generate", min_length=1, max_length=120)


class GenerationArtifact(BaseModel):
    artifact_id: str
    type: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    storage_key: str
    public: bool = False


class GenerationArtifactView(GenerationArtifact):
    download_url: str


class GenerationPreview(BaseModel):
    title: str
    lyrics: str
    song_plan: dict
    safety_notes: list[str]


class GenerationRunnerState(BaseModel):
    mode: Literal["single_flight"]
    resource: str
    state: Literal["waiting", "acquired", "released"]


class GenerationJobDetail(BaseModel):
    id: str
    job_id: str
    project_id: str
    stage: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    phase: str
    message: str
    adapter: Literal["mock", "ssh"]
    preview: GenerationPreview | None = None
    artifacts: list[GenerationArtifactView] = Field(default_factory=list)
    log_url: str | None = None
    error: dict | None = None
    queue_position: int = 0
    runner: GenerationRunnerState | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str


class WorkerLock(BaseModel):
    resource_key: str
    adapter: Literal["ssh"]
    job_id: str
    acquired_at: str
    heartbeat_at: str
    lease_expires_at: str


class RemotePilotRun(BaseModel):
    id: str
    project_id: str
    stage: str
    schema_version: str = "output.v1"
    status: Literal["completed", "failed"]
    adapter: Literal["ssh"]
    remote_job_dir: str
    job_manifest_path: str
    output_manifest_path: str
    output_files: list[str]
    artifacts: list[GenerationArtifact] = Field(default_factory=list)
    preview: GenerationPreview | None = None
    message: str
    logs: list[str]
    created_at: str
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
