#!/usr/bin/env python3
"""Server-side Aikiddo worker.

The API sends this script to the remote job directory together with
`job_manifest.json`. The worker owns all files it creates under that directory
and writes `output_manifest.json` as the stable API contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import socket
import struct
import sys
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from typing import Any


class WorkerConfigurationError(RuntimeError):
    pass


def worker_mode() -> str:
    return os.getenv("AIKIDDO_WORKER_MODE", "openai").strip().lower()


def slugify(value: str) -> str:
    return "-".join("".join(character.lower() if character.isalnum() else " " for character in value).split())


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_audio_preview(job_dir: pathlib.Path, topic: str, filename: str = "audio_preview.wav") -> pathlib.Path:
    sample_rate = 22050
    duration_sec = 2.0
    base_frequency = 330 + (len(topic) % 8) * 22
    audio_path = job_dir / filename
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = []
        for index in range(int(sample_rate * duration_sec)):
            envelope = min(index / 1200, 1.0) * min((sample_rate * duration_sec - index) / 1200, 1.0)
            sample = int(18000 * envelope * math.sin(2 * math.pi * base_frequency * index / sample_rate))
            frames.append(struct.pack("<h", sample))
        wav.writeframes(b"".join(frames))
    return audio_path


def artifact_for(job_dir: pathlib.Path, manifest: dict[str, Any], artifact_id: str, artifact_type: str, filename: str, mime_type: str) -> dict[str, Any]:
    path = job_dir / filename
    payload = path.read_bytes()
    return {
        "artifact_id": artifact_id,
        "type": artifact_type,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "storage_key": "projects/" + manifest["project_id"] + "/jobs/" + manifest["job_id"] + "/" + filename,
        "public": False,
    }


def make_lyrics_payload(brief: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    lyrics = "\n".join(
        [
            brief["title"],
            "",
            "[Verse]",
            "We name it slowly, then we sing it clear,",
            "Small bright words that little voices hear.",
            "",
            "[Chorus]",
            brief["topic"].capitalize() + " in the rhythm, one more time,",
            "Clap it, say it, keep it kind.",
        ]
    ) + "\n"
    song_plan = {
        "title": brief["title"],
        "topic": brief["topic"],
        "age_range": brief["age_range"],
        "duration_target_sec": 60,
        "sections": ["verse", "chorus"],
        "storage_policy": "server",
    }
    safety_notes = {
        "status": "ready_for_human_review",
        "checks": [
            "age range is explicit",
            "educational topic is explicit",
            "no direct publishing without human approval",
        ],
        "host": socket.gethostname(),
    }
    return lyrics, song_plan, safety_notes


def response_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def call_openai_json(*, instructions: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise WorkerConfigurationError("OPENAI_API_KEY is required for production text generation.")
    model = os.getenv("AIKIDDO_OPENAI_TEXT_MODEL", "gpt-5").strip() or "gpt-5"
    timeout = int(os.getenv("AIKIDDO_OPENAI_TIMEOUT_SEC", "90"))
    request_payload = {
        "model": model,
        "instructions": instructions,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "aikiddo_stage_payload",
                "strict": True,
                "schema": schema,
            }
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise WorkerConfigurationError(f"OpenAI text generation failed with HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise WorkerConfigurationError(f"OpenAI text generation failed: {exc.reason}") from exc

    text = response_output_text(payload)
    if not text:
        raise WorkerConfigurationError("OpenAI text generation returned no text output.")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkerConfigurationError("OpenAI text generation returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise WorkerConfigurationError("OpenAI text generation returned a non-object JSON payload.")
    return parsed


def call_openai_speech(*, input_text: str, instructions: str) -> bytes:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise WorkerConfigurationError("OPENAI_API_KEY is required for production audio generation.")
    model = os.getenv("AIKIDDO_OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip() or "gpt-4o-mini-tts"
    voice = os.getenv("AIKIDDO_OPENAI_TTS_VOICE", "coral").strip() or "coral"
    timeout = int(os.getenv("AIKIDDO_OPENAI_TIMEOUT_SEC", "90"))
    request_payload = {
        "model": model,
        "voice": voice,
        "input": input_text[:4096],
        "instructions": instructions,
        "response_format": "mp3",
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise WorkerConfigurationError(f"OpenAI speech generation failed with HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise WorkerConfigurationError(f"OpenAI speech generation failed: {exc.reason}") from exc


def find_upstream_artifact_path(manifest: dict[str, Any], *, stage: str, artifact_id: str) -> pathlib.Path:
    for upstream in manifest.get("pipeline_context", []):
        if upstream.get("stage") != stage:
            continue
        output_manifest_path = upstream.get("output_manifest_path")
        if not output_manifest_path:
            continue
        output_manifest_file = pathlib.Path(str(output_manifest_path))
        if not output_manifest_file.exists():
            continue
        output_manifest = json.loads(output_manifest_file.read_text(encoding="utf-8"))
        remote_job_dir = pathlib.Path(str(output_manifest.get("remote_job_dir", output_manifest_file.parent)))
        for artifact in output_manifest.get("artifacts", []):
            if artifact.get("artifact_id") == artifact_id:
                return remote_job_dir / str(artifact["filename"])
    raise WorkerConfigurationError(f"Required upstream artifact {stage}/{artifact_id} is missing.")


def read_upstream_artifact_text(manifest: dict[str, Any], *, stage: str, artifact_id: str) -> str:
    return find_upstream_artifact_path(manifest, stage=stage, artifact_id=artifact_id).read_text(encoding="utf-8")


def read_upstream_artifact_json(manifest: dict[str, Any], *, stage: str, artifact_id: str) -> dict[str, Any]:
    payload = json.loads(find_upstream_artifact_path(manifest, stage=stage, artifact_id=artifact_id).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorkerConfigurationError(f"Required upstream artifact {stage}/{artifact_id} must be a JSON object.")
    return payload


def make_openai_lyrics_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["lyrics", "song_plan", "safety_notes"],
        "properties": {
            "lyrics": {"type": "string"},
            "song_plan": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "topic", "age_range", "duration_target_sec", "sections", "storage_policy"],
                "properties": {
                    "title": {"type": "string"},
                    "topic": {"type": "string"},
                    "age_range": {"type": "string"},
                    "duration_target_sec": {"type": "integer"},
                    "sections": {"type": "array", "items": {"type": "string"}},
                    "storage_policy": {"type": "string"},
                },
            },
            "safety_notes": {
                "type": "object",
                "additionalProperties": False,
                "required": ["status", "checks", "host"],
                "properties": {
                    "status": {"type": "string"},
                    "checks": {"type": "array", "items": {"type": "string"}},
                    "host": {"type": "string"},
                },
            },
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "pipeline_context": manifest.get("pipeline_context", []),
            "requirements": [
                "Write age-appropriate lyrics for children in the requested language implied by the brief.",
                "Keep the content safe for preschool audiences and suitable for later human review.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side lyric generator for Aikiddo. Produce safe, original, reviewable kids song materials.",
        prompt=prompt,
        schema=schema,
    )
    lyrics = str(payload["lyrics"]).strip() + "\n"
    song_plan = dict(payload["song_plan"])
    song_plan["storage_policy"] = "server"
    safety_notes = dict(payload["safety_notes"])
    safety_notes["host"] = socket.gethostname()
    return lyrics, song_plan, safety_notes


def make_openai_character_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> tuple[dict[str, Any], str]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["character_bible", "style_frame_prompt"],
        "properties": {
            "character_bible": {
                "type": "object",
                "additionalProperties": False,
                "required": ["characters", "visual_style", "continuity_rules", "approval_status"],
                "properties": {
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "visual_style": {"type": "string"},
                    "continuity_rules": {"type": "array", "items": {"type": "string"}},
                    "approval_status": {"type": "string"},
                },
            },
            "style_frame_prompt": {"type": "string"},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "pipeline_context": manifest.get("pipeline_context", []),
            "requirements": [
                "Create a concise character bible for a preschool-safe AI music video.",
                "Respect any existing character names from the brief; invent only stable placeholder names when missing.",
                "Write one visual style frame prompt that can later feed an image generator.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side character and visual continuity planner for Aikiddo.",
        prompt=prompt,
        schema=schema,
    )
    character_bible = dict(payload["character_bible"])
    character_bible["approval_status"] = "ready_for_human_review"
    return character_bible, str(payload["style_frame_prompt"]).strip() + "\n"


def make_openai_audio_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    lyrics = read_upstream_artifact_text(manifest, stage="lyrics.generate", artifact_id="lyrics_txt")
    audio_bytes = call_openai_speech(
        input_text=lyrics,
        instructions=(
            "Perform as a warm AI-generated guide voice for a preschool educational song draft. "
            "Keep the delivery cheerful, clear, gentle, and explicitly suitable for human review before publishing."
        ),
    )
    audio_plan = {
        "title": brief["title"],
        "topic": brief["topic"],
        "source_stage": "lyrics.generate",
        "model": os.getenv("AIKIDDO_OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        "voice": os.getenv("AIKIDDO_OPENAI_TTS_VOICE", "coral"),
        "format": "mp3",
        "disclosure": "AI-generated voice draft for operator review.",
        "status": "audio_preview_ready",
    }
    return audio_plan, audio_bytes


def make_openai_storyboard_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    lyrics = read_upstream_artifact_text(manifest, stage="lyrics.generate", artifact_id="lyrics_txt")
    character_bible = read_upstream_artifact_json(manifest, stage="characters.import_or_approve", artifact_id="character_bible_json")
    audio_plan = read_upstream_artifact_json(manifest, stage="audio.generate_or_import", artifact_id="audio_plan_json")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "topic", "age_range", "scenes", "safety_checks"],
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "age_range": {"type": "string"},
            "scenes": {
                "type": "array",
                "minItems": 3,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "duration_seconds", "action", "visual_prompt", "lyric_reference", "safety_note"],
                    "properties": {
                        "id": {"type": "string"},
                        "duration_seconds": {"type": "integer"},
                        "action": {"type": "string"},
                        "visual_prompt": {"type": "string"},
                        "lyric_reference": {"type": "string"},
                        "safety_note": {"type": "string"},
                    },
                },
            },
            "safety_checks": {"type": "array", "items": {"type": "string"}},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "lyrics": lyrics,
            "character_bible": character_bible,
            "audio_plan": audio_plan,
            "requirements": [
                "Create a timed preschool-safe storyboard for an AI music video.",
                "Keep actions easy to inspect by a human reviewer.",
                "Reference lyrics without inventing unsafe actions.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side storyboard planner for Aikiddo kids music videos.",
        prompt=prompt,
        schema=schema,
    )
    payload["title"] = str(payload.get("title") or brief["title"])
    payload["topic"] = str(payload.get("topic") or brief["topic"])
    payload["age_range"] = str(payload.get("age_range") or brief["age_range"])
    return payload


def ensure_stage_can_run(stage: str) -> None:
    if worker_mode() == "deterministic":
        return
    if stage not in {"lyrics.generate", "characters.import_or_approve", "audio.generate_or_import", "storyboard.generate"}:
        raise WorkerConfigurationError(
            f"Production worker for {stage} is not configured yet. "
            "Set AIKIDDO_WORKER_MODE=deterministic only for local development."
        )


def stage_files(stage: str, brief: dict[str, Any], manifest: dict[str, Any]) -> tuple[list[tuple[str, str, str, str]], dict[str, Any]]:
    topic = brief["topic"]
    title = brief["title"]
    age_range = brief["age_range"]
    episode_slug = slugify(title) or "episode"
    ensure_stage_can_run(stage)

    if stage == "brief.generate":
        payload = {
            "title": title,
            "topic": topic,
            "age_range": age_range,
            "emotional_tone": brief["emotional_tone"],
            "educational_goal": brief["educational_goal"],
            "characters": brief.get("characters", []),
            "safety_constraints": brief.get("forbidden_motifs", []),
            "server_status": "ready_for_operator_review",
        }
        return [("episode_brief_json", "episode_brief", "episode_brief.json", "application/json")], {
            "episode_brief.json": payload,
        }

    if stage == "lyrics.generate":
        if worker_mode() == "deterministic":
            lyrics, song_plan, safety_notes = make_lyrics_payload(brief)
        else:
            lyrics, song_plan, safety_notes = make_openai_lyrics_payload(manifest, brief)
        return [
            ("lyrics_txt", "lyrics", "lyrics.txt", "text/plain"),
            ("song_plan_json", "song_plan", "song_plan.json", "application/json"),
            ("safety_notes_json", "safety_notes", "safety_notes.json", "application/json"),
            ("audio_preview_wav", "audio_preview", "audio_preview.wav", "audio/wav"),
        ], {
            "lyrics.txt": lyrics,
            "song_plan.json": song_plan,
            "safety_notes.json": safety_notes,
            "audio_preview.wav": {"kind": "audio"},
        }

    if stage == "characters.import_or_approve":
        if worker_mode() == "deterministic":
            character_bible = {
                "characters": brief.get("characters", []) or ["hero_friend_v1"],
                "visual_style": "soft preschool-safe animation",
                "continuity_rules": ["same proportions", "same palette", "clear facial expressions"],
                "approval_status": "ready_for_human_review",
            }
            style_frame_prompt = f"friendly preschool character set for {topic}, consistent design, safe gestures\n"
        else:
            character_bible, style_frame_prompt = make_openai_character_payload(manifest, brief)
        return [
            ("character_bible_json", "character_bible", "character_bible.json", "application/json"),
            ("style_frame_prompt_txt", "style_frame_prompt", "style_frame_prompt.txt", "text/plain"),
        ], {
            "character_bible.json": character_bible,
            "style_frame_prompt.txt": style_frame_prompt,
        }

    if stage == "audio.generate_or_import":
        if worker_mode() == "deterministic":
            audio_plan = {
                "title": title,
                "tempo": "moderate",
                "duration_target_sec": 60,
                "loudness_policy": "child-safe gentle limiter",
                "status": "preview_ready",
            }
            return [
                ("audio_plan_json", "audio_plan", "audio_plan.json", "application/json"),
                ("audio_preview_wav", "audio_preview", "audio_preview.wav", "audio/wav"),
            ], {
                "audio_plan.json": audio_plan,
                "audio_preview.wav": {"kind": "audio"},
            }
        audio_plan, audio_preview = make_openai_audio_payload(manifest, brief)
        return [
            ("audio_plan_json", "audio_plan", "audio_plan.json", "application/json"),
            ("audio_preview_mp3", "audio_preview", "audio_preview.mp3", "audio/mpeg"),
        ], {
            "audio_plan.json": audio_plan,
            "audio_preview.mp3": audio_preview,
        }

    if stage == "storyboard.generate":
        if worker_mode() == "deterministic":
            storyboard = {
                "title": title,
                "topic": topic,
                "age_range": age_range,
                "scenes": [
                    {"id": "scene_01_opening", "duration_seconds": 12, "action": f"Introduce {topic} with a calm visual rhythm."},
                    {"id": "scene_02_discovery", "duration_seconds": 16, "action": "Show one learnable idea and invite repetition."},
                    {"id": "scene_03_repeat", "duration_seconds": 18, "action": "Return to the chorus with gentle movement."},
                    {"id": "scene_04_resolution", "duration_seconds": 14, "action": "Close the story without a cliffhanger."},
                ],
                "safety_checks": ["no fear pressure", "no unsafe imitation", "no rapid flashes"],
            }
        else:
            storyboard = make_openai_storyboard_payload(manifest, brief)
        return [("storyboard_json", "storyboard", "storyboard.json", "application/json")], {
            "storyboard.json": storyboard,
        }

    if stage == "keyframes.generate":
        frames = [
            {"id": f"keyframe_{index:02d}", "scene_id": f"scene_{index:02d}", "prompt": f"{topic} preschool animation keyframe {index}"}
            for index in range(1, 5)
        ]
        return [
            ("keyframes_json", "keyframes", "keyframes.json", "application/json"),
            ("keyframe_prompts_txt", "keyframe_prompts", "keyframe_prompts.txt", "text/plain"),
        ], {
            "keyframes.json": {"title": title, "topic": topic, "frames": frames, "status": "ready_for_visual_review"},
            "keyframe_prompts.txt": "\n".join(frame["prompt"] for frame in frames) + "\n",
        }

    if stage == "video.scenes.generate":
        clips = [
            {"id": f"video_scene_{index:02d}", "source_keyframe_id": f"keyframe_{index:02d}", "duration_seconds": 8 + index}
            for index in range(1, 5)
        ]
        return [("video_scenes_json", "video_scenes", "video_scenes.json", "application/json")], {
            "video_scenes.json": {
                "title": title,
                "topic": topic,
                "clips": clips,
                "render_policy": "server-owned scene files",
                "status": "ready_for_scene_review",
            },
        }

    if stage == "render.full_episode":
        return [
            ("full_episode_json", "full_episode", "full_episode.json", "application/json"),
            ("full_episode_placeholder_txt", "render_placeholder", "full_episode_placeholder.txt", "text/plain"),
        ], {
            "full_episode.json": {
                "title": title,
                "episode_slug": episode_slug,
                "duration_seconds": 60,
                "output_path": f"renders/{episode_slug}/full-episode.mp4",
                "status": "server_render_manifest_ready",
            },
            "full_episode_placeholder.txt": f"Server render placeholder for {episode_slug}. Replace with FFmpeg output.\n",
        }

    if stage == "render.reels":
        reels = [
            {"id": "reel_01", "aspect_ratio": "9:16", "duration_seconds": 18, "output_path": f"renders/{episode_slug}/reel-01.mp4"},
            {"id": "reel_02", "aspect_ratio": "9:16", "duration_seconds": 20, "output_path": f"renders/{episode_slug}/reel-02.mp4"},
            {"id": "reel_03", "aspect_ratio": "9:16", "duration_seconds": 16, "output_path": f"renders/{episode_slug}/reel-03.mp4"},
        ]
        return [("reels_json", "reels", "reels.json", "application/json")], {
            "reels.json": {"title": title, "topic": topic, "reels": reels, "status": "server_reel_manifests_ready"},
        }

    if stage == "quality.compliance_report":
        return [("compliance_report_json", "compliance_report", "compliance_report.json", "application/json")], {
            "compliance_report.json": {
                "title": title,
                "topic": topic,
                "overall_status": "ready_for_human_review",
                "checks": [
                    {"id": "language", "status": "pass", "evidence": "simple supportive language"},
                    {"id": "sensory", "status": "pass", "evidence": "calm pacing policy"},
                    {"id": "publishing", "status": "review", "evidence": "operator must inspect final uploads"},
                ],
            },
        }

    if stage == "publish.prepare_package":
        return [
            ("publish_package_json", "publish_package", "publish_package.json", "application/json"),
            ("upload_checklist_txt", "upload_checklist", "upload_checklist.txt", "text/plain"),
        ], {
            "publish_package.json": {
                "title": title,
                "package_path": f"publish/{episode_slug}",
                "included_manifests": ["job_manifest.json", "output_manifest.json", "worker.log"],
                "status": "ready_for_operator_upload",
            },
            "upload_checklist.txt": "Review title, description, thumbnail, made-for-kids setting, and final files before upload.\n",
        }

    return [("stage_manifest_json", "stage_manifest", "stage_manifest.json", "application/json")], {
        "stage_manifest.json": {"title": title, "topic": topic, "stage": stage, "status": "generated"},
    }


def write_stage_outputs(job_dir: pathlib.Path, manifest: dict[str, Any], stage: str, brief: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    pipeline_context = manifest.get("pipeline_context", [])
    if pipeline_context:
        write_json(
            job_dir / "input_context.json",
            {
                "schema_version": "input-context.v1",
                "job_id": manifest["job_id"],
                "project_id": manifest["project_id"],
                "stage": stage,
                "upstream_stages": pipeline_context,
            },
        )
    descriptors, payloads = stage_files(stage, brief, manifest)
    if pipeline_context:
        descriptors = [
            ("input_context_json", "input_context", "input_context.json", "application/json"),
            *descriptors,
        ]
    for filename, payload in payloads.items():
        path = job_dir / filename
        if isinstance(payload, bytes):
            path.write_bytes(payload)
        elif filename.endswith(".json"):
            write_json(path, payload)
        elif filename.endswith(".wav"):
            build_audio_preview(job_dir, brief["topic"], filename=filename)
        else:
            path.write_text(str(payload), encoding="utf-8")
    artifacts = [
        artifact_for(job_dir, manifest=manifest, artifact_id=artifact_id, artifact_type=artifact_type, filename=filename, mime_type=mime_type)
        for artifact_id, artifact_type, filename, mime_type in descriptors
    ]
    preview = {
        "title": brief["title"],
        "lyrics": payloads.get("lyrics.txt", f"{stage} generated server-side for {brief['title']}.\n"),
        "song_plan": {
            "stage": stage,
            "topic": brief["topic"],
            "artifact_count": len(artifacts),
            "upstream_stage_count": len(pipeline_context),
            "storage_policy": "server",
        },
        "safety_notes": [
            "server-owned generation",
            "human review remains required for gated stages",
            "no direct publishing without operator approval",
        ],
    }
    logs = [f"server worker wrote {filename}" for _, _, filename, _ in descriptors]
    return artifacts, preview, logs


def run(job_dir: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads((job_dir / "job_manifest.json").read_text(encoding="utf-8"))
    brief = manifest["brief"]
    stage = manifest["stage"]
    artifacts, preview, logs = write_stage_outputs(job_dir, manifest, stage, brief)

    worker_log = job_dir / "worker.log"
    worker_log.write_text(
        "\n".join(
            [
                "job=" + manifest["job_id"],
                "stage=" + stage,
                "runner=aikiddo_worker.py",
                "artifacts=" + ",".join(artifact["filename"] for artifact in artifacts),
                "storage=server",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output = {
        "schema_version": "output.v1",
        "job_id": manifest["job_id"],
        "project_id": manifest["project_id"],
        "stage": stage,
        "status": "completed",
        "adapter": "ssh",
        "storage_policy": "server",
        "remote_job_dir": str(job_dir),
        "output_files": [artifact["storage_key"] for artifact in artifacts],
        "artifacts": artifacts,
        "preview": preview,
        "logs": ["server worker wrote job_manifest.json", *logs],
        "log": {
            "storage_key": "projects/" + manifest["project_id"] + "/jobs/" + manifest["job_id"] + "/worker.log",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(job_dir / "output_manifest.json", output)
    return output

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: aikiddo_worker.py <job_dir>", file=sys.stderr)
        return 2
    job_dir = pathlib.Path(sys.argv[1])
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        output = run(job_dir)
    except WorkerConfigurationError as exc:
        print(f"worker_configuration_error={exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
