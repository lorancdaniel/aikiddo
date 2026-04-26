#!/usr/bin/env python3
"""Server-side Aikiddo worker.

The API sends this script to the remote job directory together with
`job_manifest.json`. The worker owns all files it creates under that directory
and writes `output_manifest.json` as the stable API contract.
"""

from __future__ import annotations

import hashlib
import base64
import json
import math
import os
import pathlib
import shlex
import shutil
import socket
import struct
import subprocess
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


def call_openai_image(*, prompt: str) -> bytes:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise WorkerConfigurationError("OPENAI_API_KEY is required for production image generation.")
    model = os.getenv("AIKIDDO_OPENAI_IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1"
    size = os.getenv("AIKIDDO_OPENAI_IMAGE_SIZE", "1536x1024").strip() or "1536x1024"
    timeout = int(os.getenv("AIKIDDO_OPENAI_TIMEOUT_SEC", "90"))
    request_payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
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
        raise WorkerConfigurationError(f"OpenAI image generation failed with HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise WorkerConfigurationError(f"OpenAI image generation failed: {exc.reason}") from exc

    data = payload.get("data", [])
    if not data or not isinstance(data[0], dict) or not isinstance(data[0].get("b64_json"), str):
        raise WorkerConfigurationError("OpenAI image generation returned no b64_json image.")
    return base64.b64decode(data[0]["b64_json"])


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


def collect_upstream_artifact_paths(manifest: dict[str, Any], *, stage: str) -> dict[str, pathlib.Path]:
    paths: dict[str, pathlib.Path] = {}
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
            filename = artifact.get("filename")
            if filename:
                paths[str(filename)] = remote_job_dir / str(filename)
    return paths


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


def make_openai_keyframes_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> tuple[dict[str, Any], str]:
    storyboard = read_upstream_artifact_json(manifest, stage="storyboard.generate", artifact_id="storyboard_json")
    character_bible = read_upstream_artifact_json(
        manifest,
        stage="characters.import_or_approve",
        artifact_id="character_bible_json",
    )
    style_frame_prompt = read_upstream_artifact_text(
        manifest,
        stage="characters.import_or_approve",
        artifact_id="style_frame_prompt_txt",
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "topic", "frames", "status"],
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "frames": {
                "type": "array",
                "minItems": 3,
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "scene_id",
                        "timestamp_seconds",
                        "image_prompt",
                        "composition",
                        "continuity_note",
                        "safety_note",
                    ],
                    "properties": {
                        "id": {"type": "string"},
                        "scene_id": {"type": "string"},
                        "timestamp_seconds": {"type": "integer"},
                        "image_prompt": {"type": "string"},
                        "composition": {"type": "string"},
                        "continuity_note": {"type": "string"},
                        "safety_note": {"type": "string"},
                    },
                },
            },
            "status": {"type": "string"},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "storyboard": storyboard,
            "character_bible": character_bible,
            "style_frame_prompt": style_frame_prompt,
            "requirements": [
                "Create inspectable keyframe prompts for each important storyboard beat.",
                "Keep visual continuity with the approved character bible and style frame prompt.",
                "Write image prompts that are preschool-safe and ready for a later image generator.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side keyframe prompt planner for Aikiddo kids music videos.",
        prompt=prompt,
        schema=schema,
    )
    payload["title"] = str(payload.get("title") or brief["title"])
    payload["topic"] = str(payload.get("topic") or brief["topic"])
    payload["status"] = "ready_for_visual_review"
    prompt_lines = [str(frame["image_prompt"]).strip() for frame in payload["frames"]]
    return payload, "\n".join(prompt_lines) + "\n"


def make_openai_video_scenes_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    keyframes = read_upstream_artifact_json(manifest, stage="keyframes.generate", artifact_id="keyframes_json")
    keyframe_prompts = read_upstream_artifact_text(manifest, stage="keyframes.generate", artifact_id="keyframe_prompts_txt")
    storyboard = read_upstream_artifact_json(manifest, stage="storyboard.generate", artifact_id="storyboard_json")
    audio_plan = read_upstream_artifact_json(manifest, stage="audio.generate_or_import", artifact_id="audio_plan_json")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "topic", "clips", "render_policy", "status"],
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "clips": {
                "type": "array",
                "minItems": 3,
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "source_keyframe_id",
                        "source_keyframe_image",
                        "scene_id",
                        "duration_seconds",
                        "motion_prompt",
                        "camera_motion",
                        "transition",
                        "render_notes",
                        "safety_note",
                    ],
                    "properties": {
                        "id": {"type": "string"},
                        "source_keyframe_id": {"type": "string"},
                        "source_keyframe_image": {"type": "string"},
                        "scene_id": {"type": "string"},
                        "duration_seconds": {"type": "integer"},
                        "motion_prompt": {"type": "string"},
                        "camera_motion": {"type": "string"},
                        "transition": {"type": "string"},
                        "render_notes": {"type": "string"},
                        "safety_note": {"type": "string"},
                    },
                },
            },
            "render_policy": {"type": "string"},
            "status": {"type": "string"},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "keyframes": keyframes,
            "keyframe_prompts": keyframe_prompts,
            "storyboard": storyboard,
            "audio_plan": audio_plan,
            "requirements": [
                "Create server-renderable scene plans from approved keyframes.",
                "Do not claim that a video file has already been rendered.",
                "Keep camera motion gentle and suitable for preschool audiences.",
                "Map every clip to a source keyframe and storyboard scene.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side video scene planner for Aikiddo kids music videos.",
        prompt=prompt,
        schema=schema,
    )
    payload["title"] = str(payload.get("title") or brief["title"])
    payload["topic"] = str(payload.get("topic") or brief["topic"])
    payload["render_policy"] = "server-owned scene files"
    payload["status"] = "ready_for_scene_review"
    return payload


def make_openai_full_episode_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    video_scenes = read_upstream_artifact_json(manifest, stage="video.scenes.generate", artifact_id="video_scenes_json")
    audio_plan = read_upstream_artifact_json(manifest, stage="audio.generate_or_import", artifact_id="audio_plan_json")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "episode_slug",
            "duration_seconds",
            "scene_count",
            "output_path",
            "poster_frame",
            "audio_mix_note",
            "assembly_notes",
            "status",
        ],
        "properties": {
            "title": {"type": "string"},
            "episode_slug": {"type": "string"},
            "duration_seconds": {"type": "integer"},
            "scene_count": {"type": "integer"},
            "output_path": {"type": "string"},
            "poster_frame": {"type": "string"},
            "audio_mix_note": {"type": "string"},
            "assembly_notes": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string"},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "video_scenes": video_scenes,
            "audio_plan": audio_plan,
            "requirements": [
                "Create a server render manifest for assembling one full episode from scene plans.",
                "Do not claim that the MP4 has already been rendered.",
                "Use a stable output_path under renders/<episode_slug>/full-episode.mp4.",
                "Set scene_count from the scene plan and duration_seconds from the planned clips.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side full episode render manifest planner for Aikiddo.",
        prompt=prompt,
        schema=schema,
    )
    payload["title"] = str(payload.get("title") or brief["title"])
    payload["episode_slug"] = str(payload.get("episode_slug") or slugify(brief["title"]) or "episode")
    payload["output_path"] = str(payload.get("output_path") or f"renders/{payload['episode_slug']}/full-episode.mp4")
    payload["status"] = "server_render_manifest_ready"
    return payload


def make_full_episode_render_plan(manifest: dict[str, Any], full_episode: dict[str, Any]) -> tuple[dict[str, Any], str]:
    video_scenes = read_upstream_artifact_json(manifest, stage="video.scenes.generate", artifact_id="video_scenes_json")
    audio_plan = read_upstream_artifact_json(manifest, stage="audio.generate_or_import", artifact_id="audio_plan_json")
    image_paths = collect_upstream_artifact_paths(manifest, stage="keyframes.generate")
    episode_slug = str(full_episode.get("episode_slug") or slugify(str(full_episode.get("title") or "episode")) or "episode")
    scene_dir = f"renders/{episode_slug}/scenes"
    clips: list[dict[str, Any]] = []
    commands: list[str] = [f"mkdir -p {shlex.quote(scene_dir)}"]
    for index, clip in enumerate(video_scenes.get("clips", []), start=1):
        clip_id = str(clip.get("id") or f"video_scene_{index:02d}")
        keyframe_id = str(clip.get("source_keyframe_id") or f"keyframe_{index:02d}")
        source_image = str(clip.get("source_keyframe_image") or f"{keyframe_id}.png")
        if source_image not in image_paths:
            raise WorkerConfigurationError(f"Required keyframe image {source_image} is missing from keyframes.generate output.")
        source_image_path = image_paths[source_image]
        duration_seconds = max(1, int(clip.get("duration_seconds") or 4))
        output_path = f"{scene_dir}/{clip_id}.mp4"
        clips.append(
            {
                "id": clip_id,
                "source_keyframe_id": keyframe_id,
                "source_keyframe_image": source_image,
                "source_image_path": str(source_image_path),
                "duration_seconds": duration_seconds,
                "motion_prompt": str(clip.get("motion_prompt") or ""),
                "camera_motion": str(clip.get("camera_motion") or ""),
                "transition": str(clip.get("transition") or "cut"),
                "output_path": output_path,
            }
        )
        video_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        commands.append(
            " ".join(
                [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-t",
                    str(duration_seconds),
                    "-i",
                    shlex.quote(str(source_image_path)),
                    "-vf",
                    shlex.quote(video_filter),
                    "-r",
                    "30",
                    "-pix_fmt",
                    "yuv420p",
                    shlex.quote(output_path),
                ]
            )
        )
    concat_list_path = f"renders/{episode_slug}/concat-list.txt"
    final_output_path = str(full_episode.get("output_path") or f"renders/{episode_slug}/full-episode.mp4")
    commands.append(f"# Write approved scene paths to {shlex.quote(concat_list_path)} before final assembly.")
    commands.append(f"ffmpeg -y -f concat -safe 0 -i {shlex.quote(concat_list_path)} -c copy {shlex.quote(final_output_path)}")
    render_plan = {
        "title": str(full_episode.get("title") or video_scenes.get("title") or "Untitled episode"),
        "episode_slug": episode_slug,
        "scene_count": len(clips),
        "duration_seconds": sum(int(clip["duration_seconds"]) for clip in clips),
        "audio_plan_status": str(audio_plan.get("status") or "unknown"),
        "audio_format": str(audio_plan.get("format") or "unknown"),
        "clips": clips,
        "concat_list_path": concat_list_path,
        "output_path": final_output_path,
        "status": "render_plan_ready",
    }
    return render_plan, "\n".join(commands) + "\n"


def ffmpeg_command() -> str:
    command = os.getenv("AIKIDDO_FFMPEG_BIN", "ffmpeg")
    if pathlib.Path(command).is_absolute():
        if pathlib.Path(command).exists():
            return command
    elif shutil.which(command):
        return command
    raise WorkerConfigurationError("FFmpeg is required for render.full_episode. Install ffmpeg or set AIKIDDO_FFMPEG_BIN.")


def render_full_episode_video_assets(job_dir: pathlib.Path, render_plan: dict[str, Any]) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    ffmpeg = ffmpeg_command()
    clips = render_plan.get("clips", [])
    if not isinstance(clips, list) or not clips:
        raise WorkerConfigurationError("render.full_episode requires at least one clip in render_plan.json.")

    descriptors: list[tuple[str, str, str, str]] = []
    logs: list[str] = []
    scene_paths: list[pathlib.Path] = []
    video_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    for index, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict):
            raise WorkerConfigurationError("render.full_episode clips must be JSON objects.")
        source_path = pathlib.Path(str(clip.get("source_image_path") or ""))
        if not source_path.exists():
            raise WorkerConfigurationError(f"Source keyframe image does not exist: {source_path}")
        output_rel = pathlib.Path(str(clip.get("output_path") or f"renders/{render_plan['episode_slug']}/scenes/video_scene_{index:02d}.mp4"))
        output_path = job_dir / output_rel
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration_seconds = max(1, int(clip.get("duration_seconds") or 4))
        command = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-t",
            str(duration_seconds),
            "-i",
            str(source_path),
            "-vf",
            video_filter,
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            str(output_rel),
        ]
        try:
            subprocess.run(command, cwd=job_dir, text=True, capture_output=True, check=True)
        except subprocess.CalledProcessError as exc:
            raise WorkerConfigurationError(f"FFmpeg scene render failed: {(exc.stderr or exc.stdout or str(exc))[:500]}") from exc
        scene_paths.append(output_path)
        descriptors.append((f"scene_video_{index:02d}_mp4", "scene_video", str(output_rel), "video/mp4"))

    concat_rel = pathlib.Path(str(render_plan.get("concat_list_path") or f"renders/{render_plan['episode_slug']}/concat-list.txt"))
    concat_path = job_dir / concat_rel
    concat_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path.write_text("".join(f"file '{scene_path}'\n" for scene_path in scene_paths), encoding="utf-8")

    output_rel = pathlib.Path(str(render_plan.get("output_path") or f"renders/{render_plan['episode_slug']}/full-episode.mp4"))
    output_path = job_dir / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_rel),
        "-c",
        "copy",
        str(output_rel),
    ]
    try:
        subprocess.run(command, cwd=job_dir, text=True, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise WorkerConfigurationError(f"FFmpeg full episode assembly failed: {(exc.stderr or exc.stdout or str(exc))[:500]}") from exc
    descriptors.append(("full_episode_mp4", "full_episode_video", str(output_rel), "video/mp4"))
    logs.append(f"Rendered full episode MP4: {output_rel}")
    return descriptors, logs


def make_openai_reels_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    full_episode = read_upstream_artifact_json(manifest, stage="render.full_episode", artifact_id="full_episode_json")
    video_scenes = read_upstream_artifact_json(manifest, stage="video.scenes.generate", artifact_id="video_scenes_json")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "topic", "age_range", "reels", "distribution_notes", "status"],
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "age_range": {"type": "string"},
            "reels": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "source_episode_slug",
                        "source_scene_ids",
                        "duration_seconds",
                        "aspect_ratio",
                        "hook",
                        "output_path",
                        "caption",
                        "safety_note",
                    ],
                    "properties": {
                        "id": {"type": "string"},
                        "source_episode_slug": {"type": "string"},
                        "source_scene_ids": {"type": "array", "items": {"type": "string"}},
                        "duration_seconds": {"type": "integer"},
                        "aspect_ratio": {"type": "string"},
                        "hook": {"type": "string"},
                        "output_path": {"type": "string"},
                        "caption": {"type": "string"},
                        "safety_note": {"type": "string"},
                    },
                },
            },
            "distribution_notes": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string"},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "full_episode": full_episode,
            "video_scenes": video_scenes,
            "requirements": [
                "Create short-form render manifests for vertical clips derived from the full episode.",
                "Do not claim that reel MP4 files have already been rendered.",
                "Use vertical 9:16 aspect ratio for every reel.",
                "Map each reel to one or more source scene ids from the scene plan.",
                "Keep hooks and captions preschool-safe, non-manipulative, and ready for operator review.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side short-form reels render manifest planner for Aikiddo.",
        prompt=prompt,
        schema=schema,
    )
    payload["title"] = str(payload.get("title") or brief["title"])
    payload["topic"] = str(payload.get("topic") or brief["topic"])
    payload["age_range"] = str(payload.get("age_range") or brief["age_range"])
    payload["status"] = "server_reel_manifests_ready"
    return payload


def make_openai_compliance_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    full_episode = read_upstream_artifact_json(manifest, stage="render.full_episode", artifact_id="full_episode_json")
    reels = read_upstream_artifact_json(manifest, stage="render.reels", artifact_id="reels_json")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "topic",
            "age_range",
            "overall_status",
            "episode_output_path",
            "reel_output_paths",
            "checks",
            "operator_notes",
        ],
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "age_range": {"type": "string"},
            "overall_status": {"type": "string"},
            "episode_output_path": {"type": "string"},
            "reel_output_paths": {"type": "array", "items": {"type": "string"}},
            "checks": {
                "type": "array",
                "minItems": 4,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "label", "status", "evidence"],
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "status": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                },
            },
            "operator_notes": {"type": "array", "items": {"type": "string"}},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "full_episode": full_episode,
            "reels": reels,
            "requirements": [
                "Review the server render manifests for child-safe language, sensory pacing, story completion, and distribution readiness.",
                "Do not approve publication automatically.",
                "Use pass only when the manifest evidence supports it; use review when the operator must inspect final rendered files or upload settings.",
                "Include episode_output_path and every reel output path from the upstream manifests.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side safety and quality compliance reviewer for Aikiddo.",
        prompt=prompt,
        schema=schema,
    )
    payload["title"] = str(payload.get("title") or brief["title"])
    payload["topic"] = str(payload.get("topic") or brief["topic"])
    payload["age_range"] = str(payload.get("age_range") or brief["age_range"])
    payload["overall_status"] = "ready_for_human_review"
    return payload


def make_openai_publish_package_payload(manifest: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    full_episode = read_upstream_artifact_json(manifest, stage="render.full_episode", artifact_id="full_episode_json")
    reels = read_upstream_artifact_json(manifest, stage="render.reels", artifact_id="reels_json")
    compliance_report = read_upstream_artifact_json(
        manifest,
        stage="quality.compliance_report",
        artifact_id="compliance_report_json",
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "topic",
            "age_range",
            "package_status",
            "package_path",
            "episode_output_path",
            "reel_output_paths",
            "included_manifests",
            "publishing_metadata",
            "operator_checklist",
        ],
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string"},
            "age_range": {"type": "string"},
            "package_status": {"type": "string"},
            "package_path": {"type": "string"},
            "episode_output_path": {"type": "string"},
            "reel_output_paths": {"type": "array", "items": {"type": "string"}},
            "included_manifests": {"type": "array", "items": {"type": "string"}},
            "publishing_metadata": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "operator_checklist": {"type": "array", "items": {"type": "string"}},
        },
    }
    prompt = json.dumps(
        {
            "job_id": manifest["job_id"],
            "project_id": manifest["project_id"],
            "stage": manifest["stage"],
            "brief": brief,
            "full_episode": full_episode,
            "reels": reels,
            "compliance_report": compliance_report,
            "requirements": [
                "Create a publish package manifest for a human operator handoff.",
                "Do not upload, submit, schedule, or publish anything.",
                "Include the full episode output path, every reel output path, and all required upstream manifests.",
                "Prepare publishing metadata as strings only, suitable for later human review.",
                "Include an operator checklist for final title, description, thumbnail, made-for-kids setting, and file existence checks.",
                "Return only JSON matching the schema.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    payload = call_openai_json(
        instructions="You are the server-side publish package manifest planner for Aikiddo.",
        prompt=prompt,
        schema=schema,
    )
    payload["title"] = str(payload.get("title") or brief["title"])
    payload["topic"] = str(payload.get("topic") or brief["topic"])
    payload["age_range"] = str(payload.get("age_range") or brief["age_range"])
    payload["package_status"] = "ready"
    return payload


def ensure_stage_can_run(stage: str) -> None:
    if worker_mode() == "deterministic":
        return
    if stage not in {
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
    }:
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
        if worker_mode() == "deterministic":
            frames = [
                {"id": f"keyframe_{index:02d}", "scene_id": f"scene_{index:02d}", "prompt": f"{topic} preschool animation keyframe {index}"}
                for index in range(1, 5)
            ]
            keyframes_payload = {"title": title, "topic": topic, "frames": frames, "status": "ready_for_visual_review"}
            keyframe_prompts = "\n".join(frame["prompt"] for frame in frames) + "\n"
            descriptors = [
                ("keyframes_json", "keyframes", "keyframes.json", "application/json"),
                ("keyframe_prompts_txt", "keyframe_prompts", "keyframe_prompts.txt", "text/plain"),
            ]
            payloads = {
                "keyframes.json": keyframes_payload,
                "keyframe_prompts.txt": keyframe_prompts,
            }
        else:
            keyframes_payload, keyframe_prompts = make_openai_keyframes_payload(manifest, brief)
            descriptors = [
                ("keyframes_json", "keyframes", "keyframes.json", "application/json"),
                ("keyframe_prompts_txt", "keyframe_prompts", "keyframe_prompts.txt", "text/plain"),
            ]
            payloads = {
                "keyframes.json": keyframes_payload,
                "keyframe_prompts.txt": keyframe_prompts,
            }
            for index, frame in enumerate(keyframes_payload["frames"], start=1):
                filename = f"keyframe_{index:02d}.png"
                frame["image_filename"] = filename
                descriptors.append((f"keyframe_{index:02d}_png", "keyframe_image", filename, "image/png"))
                payloads[filename] = call_openai_image(prompt=str(frame["image_prompt"]))
        return descriptors, payloads

    if stage == "video.scenes.generate":
        if worker_mode() == "deterministic":
            video_scenes = {
                "title": title,
                "topic": topic,
                "clips": [
                    {"id": f"video_scene_{index:02d}", "source_keyframe_id": f"keyframe_{index:02d}", "duration_seconds": 8 + index}
                    for index in range(1, 5)
                ],
                "render_policy": "server-owned scene files",
                "status": "ready_for_scene_review",
            }
        else:
            video_scenes = make_openai_video_scenes_payload(manifest, brief)
        return [("video_scenes_json", "video_scenes", "video_scenes.json", "application/json")], {
            "video_scenes.json": video_scenes,
        }

    if stage == "render.full_episode":
        if worker_mode() != "deterministic":
            full_episode = make_openai_full_episode_payload(manifest, brief)
            render_plan, ffmpeg_commands = make_full_episode_render_plan(manifest, full_episode)
            return [
                ("full_episode_json", "full_episode", "full_episode.json", "application/json"),
                ("render_plan_json", "render_plan", "render_plan.json", "application/json"),
                ("ffmpeg_commands_txt", "render_commands", "ffmpeg_commands.txt", "text/plain"),
            ], {
                "full_episode.json": full_episode,
                "render_plan.json": render_plan,
                "ffmpeg_commands.txt": ffmpeg_commands,
            }
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
        if worker_mode() != "deterministic":
            return [("reels_json", "reels", "reels.json", "application/json")], {
                "reels.json": make_openai_reels_payload(manifest, brief),
            }
        reels = [
            {"id": "reel_01", "aspect_ratio": "9:16", "duration_seconds": 18, "output_path": f"renders/{episode_slug}/reel-01.mp4"},
            {"id": "reel_02", "aspect_ratio": "9:16", "duration_seconds": 20, "output_path": f"renders/{episode_slug}/reel-02.mp4"},
            {"id": "reel_03", "aspect_ratio": "9:16", "duration_seconds": 16, "output_path": f"renders/{episode_slug}/reel-03.mp4"},
        ]
        return [("reels_json", "reels", "reels.json", "application/json")], {
            "reels.json": {"title": title, "topic": topic, "reels": reels, "status": "server_reel_manifests_ready"},
        }

    if stage == "quality.compliance_report":
        if worker_mode() != "deterministic":
            return [("compliance_report_json", "compliance_report", "compliance_report.json", "application/json")], {
                "compliance_report.json": make_openai_compliance_payload(manifest, brief),
            }
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
        if worker_mode() != "deterministic":
            return [("publish_package_json", "publish_package", "publish_package.json", "application/json")], {
                "publish_package.json": make_openai_publish_package_payload(manifest, brief),
            }
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
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        elif filename.endswith(".json"):
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, payload)
        elif filename.endswith(".wav"):
            build_audio_preview(job_dir, brief["topic"], filename=filename)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(payload), encoding="utf-8")
    render_logs: list[str] = []
    if stage == "render.full_episode" and worker_mode() != "deterministic" and isinstance(payloads.get("render_plan.json"), dict):
        rendered_descriptors, render_logs = render_full_episode_video_assets(job_dir, payloads["render_plan.json"])
        descriptors = [*descriptors, *rendered_descriptors]
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
    logs.extend(render_logs)
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
