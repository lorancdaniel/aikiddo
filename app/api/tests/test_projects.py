import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio_api.main import create_app


def make_client(tmp_path: Path, allow_local_mock: bool = True) -> TestClient:
    app = create_app(projects_root=tmp_path / "projects", allow_local_mock=allow_local_mock)
    return TestClient(app)


def create_minimal_series(client: TestClient, name: str = "English Action Songs") -> dict:
    return client.post(
        "/api/series",
        json={
            "name": name,
            "target_age_min": 3,
            "target_age_max": 5,
            "primary_language": "en",
            "learning_domain": "ESL",
            "series_premise": "Short movement songs for preschool English practice.",
            "main_characters": [],
            "visual_style": "bright 2D classroom scenes",
            "music_style": "upbeat call-and-response",
            "voice_rules": "clear pronunciation",
            "safety_rules": ["no unsafe actions"],
            "forbidden_content": ["violence"],
            "made_for_kids_default": True,
        },
    ).json()


def create_project_with_episode_spec(
    client: TestClient,
    *,
    series_id: str,
    title: str,
    topic: str,
    objective: str,
    vocabulary: list[str],
) -> dict:
    project = client.post(
        "/api/projects",
        json={
            "title": title,
            "topic": topic,
            "age_range": "3-5",
            "emotional_tone": "radosc",
            "educational_goal": objective,
            "characters": [],
        },
    ).json()
    client.put(f"/api/projects/{project['id']}/series", json={"series_id": series_id})
    client.put(
        f"/api/projects/{project['id']}/episode-spec",
        json={
            "working_title": title,
            "topic": topic,
            "target_age_min": 3,
            "target_age_max": 5,
            "learning_objective": {
                "statement": objective,
                "domain": "vocabulary",
                "vocabulary_terms": vocabulary,
                "success_criteria": ["child repeats target words"],
            },
            "format": "song_video",
            "target_duration_sec": 150,
            "audience_context": "both",
            "search_keywords": [topic, "preschool song"],
            "derivative_plan": {
                "make_shorts": True,
                "make_reels": True,
                "make_parent_teacher_page": True,
                "make_lyrics_page": True,
            },
            "made_for_kids": True,
        },
    )
    client.post(f"/api/projects/{project['id']}/episode-spec/approve", json={})
    return client.get(f"/api/projects/{project['id']}").json()


def remote_output_fixture(project_id: str, stage: str = "lyrics.generate", job_id: str = "remote_job_from_fixture") -> dict:
    storage_prefix = f"projects/{project_id}/jobs/{job_id}"
    return {
        "schema_version": "output.v1",
        "job_id": job_id,
        "project_id": project_id,
        "stage": stage,
        "status": "completed",
        "adapter": "ssh",
        "storage_policy": "server",
        "remote_job_dir": f"/home/daniel/aikiddo-worker/jobs/{job_id}",
        "output_files": [
            f"{storage_prefix}/lyrics.txt",
            f"{storage_prefix}/song_plan.json",
            f"{storage_prefix}/safety_notes.json",
            f"{storage_prefix}/audio_preview.wav",
        ],
        "artifacts": [
            {
                "artifact_id": "lyrics_txt",
                "type": "lyrics",
                "filename": "lyrics.txt",
                "mime_type": "text/plain",
                "size_bytes": 42,
                "sha256": "7fd5f87915ff579eb9909bbc9d11f5de96910160f7b24719288346c7f1f2d57c",
                "storage_key": f"{storage_prefix}/lyrics.txt",
                "public": False,
            },
            {
                "artifact_id": "song_plan_json",
                "type": "song_plan",
                "filename": "song_plan.json",
                "mime_type": "application/json",
                "size_bytes": 64,
                "sha256": "sha-song-plan",
                "storage_key": f"{storage_prefix}/song_plan.json",
                "public": False,
            },
            {
                "artifact_id": "safety_notes_json",
                "type": "safety_notes",
                "filename": "safety_notes.json",
                "mime_type": "application/json",
                "size_bytes": 64,
                "sha256": "sha-safety",
                "storage_key": f"{storage_prefix}/safety_notes.json",
                "public": False,
            },
            {
                "artifact_id": "audio_preview_wav",
                "type": "audio_preview",
                "filename": "audio_preview.wav",
                "mime_type": "audio/wav",
                "size_bytes": 88244,
                "sha256": "sha-audio-preview",
                "storage_key": f"{storage_prefix}/audio_preview.wav",
                "public": False,
            },
        ],
        "preview": {
            "title": "Server lyrics",
            "lyrics": "Colors in the rhythm\n",
            "song_plan": {"duration_target_sec": 60, "sections": ["verse", "chorus"]},
            "safety_notes": ["ready for human review"],
        },
        "logs": ["fixture completed"],
        "generated_at": "2026-04-25T20:00:00+00:00",
    }


def job_id_from_output_manifest_command(command: list[str]) -> str:
    return command[-1].split("/jobs/", 1)[1].split("/", 1)[0]


def deterministic_worker_env() -> dict[str, str]:
    return {**os.environ, "AIKIDDO_WORKER_MODE": "deterministic"}


def production_worker_env_without_openai_key() -> dict[str, str]:
    env = {**os.environ}
    env.pop("AIKIDDO_WORKER_MODE", None)
    env.pop("OPENAI_API_KEY", None)
    return env


def load_worker_module():
    worker_path = Path(__file__).resolve().parents[3] / "scripts" / "aikiddo_worker.py"
    spec = importlib.util.spec_from_file_location("aikiddo_worker_under_test", worker_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_job_manifest_from_ssh_script(script: str) -> dict:
    legacy_marker = "<<'JSON'\n"
    if legacy_marker in script:
        manifest_text = script.split(legacy_marker, 1)[1].split("\nJSON", 1)[0]
        return json.loads(manifest_text)
    marker = '(job_dir / "job_manifest.json").write_text('
    encoded_manifest = script.split(marker, 1)[1].split(', encoding="utf-8")', 1)[0]
    return json.loads(json.loads(encoded_manifest))


def test_aikiddo_worker_writes_server_output_contract(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    manifest = {
        "schema_version": "job.v1",
        "job_id": "remote_worker_contract",
        "project_id": "project_contract",
        "stage": "lyrics.generate",
        "job_type": "kids_song_pilot",
        "adapter": "ssh",
        "brief": {
            "id": "brief_contract",
            "title": "Colors Song",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
            "forbidden_motifs": [],
            "created_at": "2026-04-26T00:00:00+00:00",
        },
        "created_at": "2026-04-26T00:00:00+00:00",
    }
    (job_dir / "job_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    worker_path = Path(__file__).resolve().parents[3] / "scripts" / "aikiddo_worker.py"
    result = subprocess.run(
        [sys.executable, str(worker_path), str(job_dir)],
        text=True,
        capture_output=True,
        env=deterministic_worker_env(),
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    output = json.loads((job_dir / "output_manifest.json").read_text(encoding="utf-8"))
    assert output["schema_version"] == "output.v1"
    assert output["job_id"] == "remote_worker_contract"
    assert output["project_id"] == "project_contract"
    assert output["status"] == "completed"
    assert output["adapter"] == "ssh"
    assert output["storage_policy"] == "server"
    assert [artifact["artifact_id"] for artifact in output["artifacts"]] == [
        "lyrics_txt",
        "song_plan_json",
        "safety_notes_json",
        "audio_preview_wav",
    ]
    assert (job_dir / "lyrics.txt").exists()
    assert (job_dir / "song_plan.json").exists()
    assert (job_dir / "safety_notes.json").exists()
    assert (job_dir / "audio_preview.wav").exists()
    assert "runner=aikiddo_worker.py" in (job_dir / "worker.log").read_text(encoding="utf-8")


def test_aikiddo_worker_requires_openai_key_for_production_lyrics(tmp_path: Path) -> None:
    job_dir = tmp_path / "job_requires_provider"
    job_dir.mkdir()
    manifest = {
        "schema_version": "job.v1",
        "job_id": "remote_requires_provider",
        "project_id": "project_contract",
        "stage": "lyrics.generate",
        "job_type": "kids_song_pilot",
        "adapter": "ssh",
        "brief": {
            "id": "brief_contract",
            "title": "Colors Song",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
            "forbidden_motifs": [],
            "created_at": "2026-04-26T00:00:00+00:00",
        },
        "created_at": "2026-04-26T00:00:00+00:00",
    }
    (job_dir / "job_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    worker_path = Path(__file__).resolve().parents[3] / "scripts" / "aikiddo_worker.py"
    result = subprocess.run(
        [sys.executable, str(worker_path), str(job_dir)],
        text=True,
        capture_output=True,
        env=production_worker_env_without_openai_key(),
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert result.stderr.strip() == "worker_configuration_error=OPENAI_API_KEY is required for production text generation."
    assert not (job_dir / "output_manifest.json").exists()


def test_aikiddo_worker_uses_openai_provider_for_character_bible(monkeypatch) -> None:
    worker = load_worker_module()
    monkeypatch.setenv("AIKIDDO_WORKER_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-provider")

    def fake_call_openai_json(*, instructions: str, prompt: str, schema: dict) -> dict:
        assert "character and visual continuity planner" in instructions
        assert "characters.import_or_approve" in prompt
        assert schema["required"] == ["character_bible", "style_frame_prompt"]
        return {
            "character_bible": {
                "characters": ["brush_friend_v1"],
                "visual_style": "clean 2D classroom animation with rounded shapes",
                "continuity_rules": ["fixed color palette", "same proportions"],
                "approval_status": "draft",
            },
            "style_frame_prompt": "brush_friend_v1 in a safe bright bathroom classroom scene",
        }

    monkeypatch.setattr(worker, "call_openai_json", fake_call_openai_json)
    descriptors, payloads = worker.stage_files(
        "characters.import_or_approve",
        {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "age_range": "3-5",
            "characters": ["brush_friend_v1"],
        },
        {
            "job_id": "remote_character_provider",
            "project_id": "project_character_provider",
            "stage": "characters.import_or_approve",
            "pipeline_context": [{"stage": "lyrics.generate", "status": "completed"}],
        },
    )

    assert ("character_bible_json", "character_bible", "character_bible.json", "application/json") in descriptors
    assert payloads["character_bible.json"]["approval_status"] == "ready_for_human_review"
    assert "brush_friend_v1" in payloads["style_frame_prompt.txt"]


def test_aikiddo_worker_uses_openai_speech_for_audio_stage(tmp_path: Path, monkeypatch) -> None:
    worker = load_worker_module()
    monkeypatch.setenv("AIKIDDO_WORKER_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-provider")
    monkeypatch.setenv("AIKIDDO_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    monkeypatch.setenv("AIKIDDO_OPENAI_TTS_VOICE", "coral")
    lyrics_job_dir = tmp_path / "lyrics_job"
    lyrics_job_dir.mkdir()
    (lyrics_job_dir / "lyrics.txt").write_text("Brush, brush, smile bright.\n", encoding="utf-8")
    lyrics_output = {
        "remote_job_dir": str(lyrics_job_dir),
        "artifacts": [{"artifact_id": "lyrics_txt", "filename": "lyrics.txt"}],
    }
    lyrics_output_path = lyrics_job_dir / "output_manifest.json"
    lyrics_output_path.write_text(json.dumps(lyrics_output), encoding="utf-8")

    def fake_call_openai_speech(*, input_text: str, instructions: str) -> bytes:
        assert "Brush, brush" in input_text
        assert "AI-generated guide voice" in instructions
        return b"fake-mp3-bytes"

    monkeypatch.setattr(worker, "call_openai_speech", fake_call_openai_speech)
    descriptors, payloads = worker.stage_files(
        "audio.generate_or_import",
        {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "age_range": "3-5",
        },
        {
            "job_id": "remote_audio_provider",
            "project_id": "project_audio_provider",
            "stage": "audio.generate_or_import",
            "pipeline_context": [{"stage": "lyrics.generate", "output_manifest_path": str(lyrics_output_path)}],
        },
    )

    assert ("audio_preview_mp3", "audio_preview", "audio_preview.mp3", "audio/mpeg") in descriptors
    assert payloads["audio_preview.mp3"] == b"fake-mp3-bytes"
    assert payloads["audio_plan.json"]["disclosure"] == "AI-generated voice draft for operator review."
    assert payloads["audio_plan.json"]["voice"] == "coral"


def test_aikiddo_worker_uses_openai_provider_for_storyboard(tmp_path: Path, monkeypatch) -> None:
    worker = load_worker_module()
    monkeypatch.setenv("AIKIDDO_WORKER_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-provider")

    lyrics_job_dir = tmp_path / "lyrics_job"
    lyrics_job_dir.mkdir()
    (lyrics_job_dir / "lyrics.txt").write_text("Brush, brush, smile bright.\n", encoding="utf-8")
    lyrics_output_path = lyrics_job_dir / "output_manifest.json"
    lyrics_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(lyrics_job_dir),
                "artifacts": [{"artifact_id": "lyrics_txt", "filename": "lyrics.txt"}],
            }
        ),
        encoding="utf-8",
    )

    character_job_dir = tmp_path / "character_job"
    character_job_dir.mkdir()
    (character_job_dir / "character_bible.json").write_text(
        json.dumps({"characters": ["brush_friend_v1"], "visual_style": "soft 2D", "continuity_rules": ["same palette"]}),
        encoding="utf-8",
    )
    character_output_path = character_job_dir / "output_manifest.json"
    character_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(character_job_dir),
                "artifacts": [{"artifact_id": "character_bible_json", "filename": "character_bible.json"}],
            }
        ),
        encoding="utf-8",
    )

    audio_job_dir = tmp_path / "audio_job"
    audio_job_dir.mkdir()
    (audio_job_dir / "audio_plan.json").write_text(
        json.dumps({"title": "Brush Song", "format": "mp3", "status": "audio_preview_ready"}),
        encoding="utf-8",
    )
    audio_output_path = audio_job_dir / "output_manifest.json"
    audio_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(audio_job_dir),
                "artifacts": [{"artifact_id": "audio_plan_json", "filename": "audio_plan.json"}],
            }
        ),
        encoding="utf-8",
    )

    def fake_call_openai_json(*, instructions: str, prompt: str, schema: dict) -> dict:
        assert "storyboard planner" in instructions
        assert "Brush, brush" in prompt
        assert "brush_friend_v1" in prompt
        assert schema["properties"]["scenes"]["minItems"] == 3
        return {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "age_range": "3-5",
            "scenes": [
                {
                    "id": "scene_01_opening",
                    "duration_seconds": 12,
                    "action": "Brush friend waves beside the sink.",
                    "visual_prompt": "soft 2D bathroom classroom, brush_friend_v1 waving",
                    "lyric_reference": "Brush, brush",
                    "safety_note": "No unsafe bathroom climbing.",
                },
                {
                    "id": "scene_02_repeat",
                    "duration_seconds": 16,
                    "action": "Children repeat the brushing motion slowly.",
                    "visual_prompt": "preschool-safe slow brushing gesture",
                    "lyric_reference": "smile bright",
                    "safety_note": "Gentle motion only.",
                },
                {
                    "id": "scene_03_close",
                    "duration_seconds": 12,
                    "action": "Brush friend smiles at a clean sink.",
                    "visual_prompt": "calm closing shot with bright sink",
                    "lyric_reference": "smile bright",
                    "safety_note": "No product claims.",
                },
            ],
            "safety_checks": ["no fear pressure", "no unsafe imitation", "no rapid flashes"],
        }

    monkeypatch.setattr(worker, "call_openai_json", fake_call_openai_json)
    descriptors, payloads = worker.stage_files(
        "storyboard.generate",
        {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "age_range": "3-5",
        },
        {
            "job_id": "remote_storyboard_provider",
            "project_id": "project_storyboard_provider",
            "stage": "storyboard.generate",
            "pipeline_context": [
                {"stage": "lyrics.generate", "output_manifest_path": str(lyrics_output_path)},
                {"stage": "characters.import_or_approve", "output_manifest_path": str(character_output_path)},
                {"stage": "audio.generate_or_import", "output_manifest_path": str(audio_output_path)},
            ],
        },
    )

    assert descriptors == [("storyboard_json", "storyboard", "storyboard.json", "application/json")]
    assert payloads["storyboard.json"]["scenes"][0]["id"] == "scene_01_opening"
    assert payloads["storyboard.json"]["safety_checks"] == ["no fear pressure", "no unsafe imitation", "no rapid flashes"]


def test_aikiddo_worker_uses_openai_provider_for_keyframes(tmp_path: Path, monkeypatch) -> None:
    worker = load_worker_module()
    monkeypatch.setenv("AIKIDDO_WORKER_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-provider")

    character_job_dir = tmp_path / "character_job"
    character_job_dir.mkdir()
    (character_job_dir / "character_bible.json").write_text(
        json.dumps({"characters": ["brush_friend_v1"], "visual_style": "soft 2D", "continuity_rules": ["same palette"]}),
        encoding="utf-8",
    )
    (character_job_dir / "style_frame_prompt.txt").write_text(
        "brush_friend_v1 in a safe bright bathroom classroom scene",
        encoding="utf-8",
    )
    character_output_path = character_job_dir / "output_manifest.json"
    character_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(character_job_dir),
                "artifacts": [
                    {"artifact_id": "character_bible_json", "filename": "character_bible.json"},
                    {"artifact_id": "style_frame_prompt_txt", "filename": "style_frame_prompt.txt"},
                ],
            }
        ),
        encoding="utf-8",
    )

    storyboard_job_dir = tmp_path / "storyboard_job"
    storyboard_job_dir.mkdir()
    (storyboard_job_dir / "storyboard.json").write_text(
        json.dumps(
            {
                "title": "Brush Song",
                "topic": "tooth brushing",
                "scenes": [
                    {
                        "id": "scene_01_opening",
                        "duration_seconds": 12,
                        "action": "Brush friend waves beside the sink.",
                        "visual_prompt": "soft 2D bathroom classroom, brush_friend_v1 waving",
                        "lyric_reference": "Brush, brush",
                        "safety_note": "No unsafe bathroom climbing.",
                    }
                ],
                "safety_checks": ["no unsafe imitation"],
            }
        ),
        encoding="utf-8",
    )
    storyboard_output_path = storyboard_job_dir / "output_manifest.json"
    storyboard_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(storyboard_job_dir),
                "artifacts": [{"artifact_id": "storyboard_json", "filename": "storyboard.json"}],
            }
        ),
        encoding="utf-8",
    )

    def fake_call_openai_json(*, instructions: str, prompt: str, schema: dict) -> dict:
        assert "keyframe prompt planner" in instructions
        assert "scene_01_opening" in prompt
        assert "brush_friend_v1 in a safe bright bathroom classroom scene" in prompt
        assert schema["properties"]["frames"]["minItems"] == 3
        return {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "status": "draft",
            "frames": [
                {
                    "id": "keyframe_01",
                    "scene_id": "scene_01_opening",
                    "timestamp_seconds": 0,
                    "image_prompt": "soft 2D keyframe of brush_friend_v1 waving beside a safe sink",
                    "composition": "medium-wide shot, clear sink edge, calm background",
                    "continuity_note": "keep the same brush_friend_v1 palette",
                    "safety_note": "no climbing, no product claims",
                },
                {
                    "id": "keyframe_02",
                    "scene_id": "scene_01_opening",
                    "timestamp_seconds": 4,
                    "image_prompt": "gentle close keyframe of slow tooth brushing gesture",
                    "composition": "waist-up view, simple mirror shape, no brand labels",
                    "continuity_note": "same rounded style",
                    "safety_note": "gentle motion only",
                },
                {
                    "id": "keyframe_03",
                    "scene_id": "scene_01_opening",
                    "timestamp_seconds": 8,
                    "image_prompt": "calm closing keyframe with brush_friend_v1 smiling near a clean sink",
                    "composition": "centered character, soft classroom color accents",
                    "continuity_note": "same proportions and colors",
                    "safety_note": "preschool-safe bathroom framing",
                },
            ],
        }

    monkeypatch.setattr(worker, "call_openai_json", fake_call_openai_json)
    descriptors, payloads = worker.stage_files(
        "keyframes.generate",
        {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "age_range": "3-5",
        },
        {
            "job_id": "remote_keyframes_provider",
            "project_id": "project_keyframes_provider",
            "stage": "keyframes.generate",
            "pipeline_context": [
                {"stage": "characters.import_or_approve", "output_manifest_path": str(character_output_path)},
                {"stage": "storyboard.generate", "output_manifest_path": str(storyboard_output_path)},
            ],
        },
    )

    assert ("keyframes_json", "keyframes", "keyframes.json", "application/json") in descriptors
    assert ("keyframe_prompts_txt", "keyframe_prompts", "keyframe_prompts.txt", "text/plain") in descriptors
    assert payloads["keyframes.json"]["status"] == "ready_for_visual_review"
    assert payloads["keyframes.json"]["frames"][0]["id"] == "keyframe_01"
    assert "soft 2D keyframe of brush_friend_v1" in payloads["keyframe_prompts.txt"]


def test_aikiddo_worker_uses_openai_provider_for_video_scenes(tmp_path: Path, monkeypatch) -> None:
    worker = load_worker_module()
    monkeypatch.setenv("AIKIDDO_WORKER_MODE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-provider")

    audio_job_dir = tmp_path / "audio_job"
    audio_job_dir.mkdir()
    (audio_job_dir / "audio_plan.json").write_text(
        json.dumps({"title": "Brush Song", "format": "mp3", "status": "audio_preview_ready"}),
        encoding="utf-8",
    )
    audio_output_path = audio_job_dir / "output_manifest.json"
    audio_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(audio_job_dir),
                "artifacts": [{"artifact_id": "audio_plan_json", "filename": "audio_plan.json"}],
            }
        ),
        encoding="utf-8",
    )

    storyboard_job_dir = tmp_path / "storyboard_job"
    storyboard_job_dir.mkdir()
    (storyboard_job_dir / "storyboard.json").write_text(
        json.dumps(
            {
                "title": "Brush Song",
                "topic": "tooth brushing",
                "scenes": [
                    {
                        "id": "scene_01_opening",
                        "duration_seconds": 12,
                        "action": "Brush friend waves beside the sink.",
                        "visual_prompt": "soft 2D bathroom classroom, brush_friend_v1 waving",
                        "lyric_reference": "Brush, brush",
                        "safety_note": "No unsafe bathroom climbing.",
                    }
                ],
                "safety_checks": ["no unsafe imitation"],
            }
        ),
        encoding="utf-8",
    )
    storyboard_output_path = storyboard_job_dir / "output_manifest.json"
    storyboard_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(storyboard_job_dir),
                "artifacts": [{"artifact_id": "storyboard_json", "filename": "storyboard.json"}],
            }
        ),
        encoding="utf-8",
    )

    keyframes_job_dir = tmp_path / "keyframes_job"
    keyframes_job_dir.mkdir()
    (keyframes_job_dir / "keyframes.json").write_text(
        json.dumps(
            {
                "title": "Brush Song",
                "topic": "tooth brushing",
                "status": "ready_for_visual_review",
                "frames": [
                    {
                        "id": "keyframe_01",
                        "scene_id": "scene_01_opening",
                        "timestamp_seconds": 0,
                        "image_prompt": "soft 2D keyframe of brush_friend_v1 waving beside a safe sink",
                        "composition": "medium-wide shot",
                        "continuity_note": "same palette",
                        "safety_note": "no climbing",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (keyframes_job_dir / "keyframe_prompts.txt").write_text(
        "soft 2D keyframe of brush_friend_v1 waving beside a safe sink\n",
        encoding="utf-8",
    )
    keyframes_output_path = keyframes_job_dir / "output_manifest.json"
    keyframes_output_path.write_text(
        json.dumps(
            {
                "remote_job_dir": str(keyframes_job_dir),
                "artifacts": [
                    {"artifact_id": "keyframes_json", "filename": "keyframes.json"},
                    {"artifact_id": "keyframe_prompts_txt", "filename": "keyframe_prompts.txt"},
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_call_openai_json(*, instructions: str, prompt: str, schema: dict) -> dict:
        assert "video scene planner" in instructions
        assert "keyframe_01" in prompt
        assert "audio_preview_ready" in prompt
        assert "Do not claim that a video file has already been rendered." in prompt
        assert schema["properties"]["clips"]["minItems"] == 3
        return {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "render_policy": "draft",
            "status": "draft",
            "clips": [
                {
                    "id": "video_scene_01",
                    "source_keyframe_id": "keyframe_01",
                    "scene_id": "scene_01_opening",
                    "duration_seconds": 4,
                    "motion_prompt": "small friendly wave, no sudden motion",
                    "camera_motion": "locked gentle push-in",
                    "transition": "soft dissolve",
                    "render_notes": "render from approved keyframe, keep sink simple",
                    "safety_note": "no climbing or rapid flashes",
                },
                {
                    "id": "video_scene_02",
                    "source_keyframe_id": "keyframe_01",
                    "scene_id": "scene_01_opening",
                    "duration_seconds": 4,
                    "motion_prompt": "slow brushing gesture loop",
                    "camera_motion": "static medium shot",
                    "transition": "straight cut",
                    "render_notes": "keep character proportions stable",
                    "safety_note": "gentle motion only",
                },
                {
                    "id": "video_scene_03",
                    "source_keyframe_id": "keyframe_01",
                    "scene_id": "scene_01_opening",
                    "duration_seconds": 4,
                    "motion_prompt": "character smiles near the clean sink",
                    "camera_motion": "no camera movement",
                    "transition": "soft fade",
                    "render_notes": "prepare for human review",
                    "safety_note": "no product claims",
                },
            ],
        }

    monkeypatch.setattr(worker, "call_openai_json", fake_call_openai_json)
    descriptors, payloads = worker.stage_files(
        "video.scenes.generate",
        {
            "title": "Brush Song",
            "topic": "tooth brushing",
            "age_range": "3-5",
        },
        {
            "job_id": "remote_video_scenes_provider",
            "project_id": "project_video_scenes_provider",
            "stage": "video.scenes.generate",
            "pipeline_context": [
                {"stage": "audio.generate_or_import", "output_manifest_path": str(audio_output_path)},
                {"stage": "storyboard.generate", "output_manifest_path": str(storyboard_output_path)},
                {"stage": "keyframes.generate", "output_manifest_path": str(keyframes_output_path)},
            ],
        },
    )

    assert descriptors == [("video_scenes_json", "video_scenes", "video_scenes.json", "application/json")]
    assert payloads["video_scenes.json"]["render_policy"] == "server-owned scene files"
    assert payloads["video_scenes.json"]["status"] == "ready_for_scene_review"
    assert payloads["video_scenes.json"]["clips"][0]["source_keyframe_id"] == "keyframe_01"


@pytest.mark.parametrize(
    ("stage", "expected_artifact_id"),
    [
        ("brief.generate", "episode_brief_json"),
        ("lyrics.generate", "lyrics_txt"),
        ("characters.import_or_approve", "character_bible_json"),
        ("audio.generate_or_import", "audio_plan_json"),
        ("storyboard.generate", "storyboard_json"),
        ("keyframes.generate", "keyframes_json"),
        ("video.scenes.generate", "video_scenes_json"),
        ("render.full_episode", "full_episode_json"),
        ("render.reels", "reels_json"),
        ("quality.compliance_report", "compliance_report_json"),
        ("publish.prepare_package", "publish_package_json"),
    ],
)
def test_aikiddo_worker_is_stage_aware(tmp_path: Path, stage: str, expected_artifact_id: str) -> None:
    job_dir = tmp_path / stage.replace(".", "_").replace("/", "_")
    job_dir.mkdir()
    manifest = {
        "schema_version": "job.v1",
        "job_id": f"remote_{stage.replace('.', '_')}",
        "project_id": "project_contract",
        "stage": stage,
        "job_type": "kids_song_pilot",
        "adapter": "ssh",
        "brief": {
            "id": "brief_contract",
            "title": "Colors Song",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": ["brush_friend_v1"],
            "forbidden_motifs": ["fear pressure"],
            "created_at": "2026-04-26T00:00:00+00:00",
        },
        "created_at": "2026-04-26T00:00:00+00:00",
    }
    (job_dir / "job_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    worker_path = Path(__file__).resolve().parents[3] / "scripts" / "aikiddo_worker.py"
    result = subprocess.run(
        [sys.executable, str(worker_path), str(job_dir)],
        text=True,
        capture_output=True,
        env=deterministic_worker_env(),
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    output = json.loads((job_dir / "output_manifest.json").read_text(encoding="utf-8"))
    assert output["stage"] == stage
    assert output["status"] == "completed"
    assert output["preview"]["song_plan"]["stage"] == stage
    assert expected_artifact_id in [artifact["artifact_id"] for artifact in output["artifacts"]]
    assert all((job_dir / artifact["filename"]).exists() for artifact in output["artifacts"])
    worker_log = (job_dir / "worker.log").read_text(encoding="utf-8")
    assert f"stage={stage}" in worker_log
    assert "storage=server" in worker_log


def test_aikiddo_worker_persists_input_context_artifact(tmp_path: Path) -> None:
    job_dir = tmp_path / "job_with_context"
    job_dir.mkdir()
    manifest = {
        "schema_version": "job.v1",
        "job_id": "remote_storyboard_context",
        "project_id": "project_context",
        "stage": "storyboard.generate",
        "job_type": "kids_song_pilot",
        "adapter": "ssh",
        "pipeline_context": [
            {
                "stage": "lyrics.generate",
                "status": "completed",
                "job_id": "remote_lyrics_context",
                "output_manifest_path": "/srv/aikiddo/jobs/remote_lyrics_context/output_manifest.json",
                "artifacts": [{"artifact_id": "lyrics_txt", "filename": "lyrics.txt"}],
            }
        ],
        "brief": {
            "id": "brief_context",
            "title": "Colors Song",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
            "forbidden_motifs": [],
            "created_at": "2026-04-26T00:00:00+00:00",
        },
        "created_at": "2026-04-26T00:00:00+00:00",
    }
    (job_dir / "job_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    worker_path = Path(__file__).resolve().parents[3] / "scripts" / "aikiddo_worker.py"
    result = subprocess.run(
        [sys.executable, str(worker_path), str(job_dir)],
        text=True,
        capture_output=True,
        env=deterministic_worker_env(),
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    output = json.loads((job_dir / "output_manifest.json").read_text(encoding="utf-8"))
    context = json.loads((job_dir / "input_context.json").read_text(encoding="utf-8"))
    assert "input_context_json" in [artifact["artifact_id"] for artifact in output["artifacts"]]
    assert output["preview"]["song_plan"]["upstream_stage_count"] == 1
    assert context["schema_version"] == "input-context.v1"
    assert context["upstream_stages"][0]["stage"] == "lyrics.generate"
    assert context["upstream_stages"][0]["output_manifest_path"].endswith("/remote_lyrics_context/output_manifest.json")


def test_health_reports_mock_adapter(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "adapter": "mock"}


def test_health_reports_ssh_adapter_by_default(tmp_path: Path) -> None:
    client = make_client(tmp_path, allow_local_mock=False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "adapter": "ssh"}


def test_remote_pilot_endpoint_is_retired(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Remote pilot",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()

    response = client.post(f"/api/projects/{project['id']}/remote-pilot", json={"stage": "lyrics.generate"})
    read_response = client.get(f"/api/projects/{project['id']}/remote-pilot")

    assert response.status_code == 410
    assert read_response.status_code == 410
    assert response.json()["detail"] == "Remote pilot endpoint is retired; use project jobs instead"


def test_project_job_writes_server_manifest_through_ssh(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-worker")
    project = client.post(
        "/api/projects",
        json={
            "title": "Remote pilot",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    calls: list[dict] = []

    class Completed:
        def __init__(self, stdout: str = "ok\n") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        calls.append({"command": command, "input": input})
        if command[-1].startswith("cat "):
            job_id = job_id_from_output_manifest_command(command)
            return Completed(stdout=json.dumps(remote_output_fixture(project["id"], job_id=job_id)))
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    response = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["adapter"] == "ssh"
    assert job["status"] == "needs_review"
    assert job["stage"] == "lyrics.generate"
    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert detail["preview"]["lyrics"] == "Colors in the rhythm\n"
    assert [artifact["artifact_id"] for artifact in detail["artifacts"]] == [
        "lyrics_txt",
        "song_plan_json",
        "safety_notes_json",
        "audio_preview_wav",
    ]
    assert any("job_manifest.json" in call["input"] for call in calls if call["input"])
    assert any("export OPENAI_API_KEY=sk-test-worker" in call["input"] for call in calls if call["input"])
    assert not (tmp_path / "projects" / project["id"] / "remote-pilot.json").exists()
    assert (tmp_path / "projects" / project["id"] / "remote-runs" / f"{job['id']}.json").exists()


def test_ssh_job_manifest_includes_upstream_pipeline_context(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Context song",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    manifests: list[dict] = []
    job_projects: dict[str, str] = {}
    job_stages: dict[str, str] = {}

    class Completed:
        def __init__(self, stdout: str = "ok\n") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if input and "job_manifest.json" in input:
            manifest = extract_job_manifest_from_ssh_script(input)
            manifests.append(manifest)
            job_projects[manifest["job_id"]] = manifest["project_id"]
            job_stages[manifest["job_id"]] = manifest["stage"]
            return Completed(stdout="remote script completed\n")
        if command[-1].startswith("cat ") and command[-1].endswith("output_manifest.json"):
            job_id = command[-1].split("/jobs/", 1)[1].split("/", 1)[0]
            return Completed(stdout=json.dumps(remote_output_fixture(job_projects[job_id], stage=job_stages[job_id], job_id=job_id)))
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    lyrics_job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    client.post(f"/api/projects/{project['id']}/stages/lyrics.generate/approve", json={})
    characters_job = client.post(f"/api/projects/{project['id']}/jobs/characters.import_or_approve").json()

    assert lyrics_job["status"] == "needs_review"
    assert characters_job["status"] == "needs_review"
    assert manifests[0]["pipeline_context"] == [
        {"stage": "brief.generate", "status": "completed", "job_id": None}
    ]
    characters_context = manifests[1]["pipeline_context"]
    assert [item["stage"] for item in characters_context] == ["brief.generate", "lyrics.generate"]
    lyrics_context = next(item for item in characters_context if item["stage"] == "lyrics.generate")
    assert lyrics_context["status"] == "completed"
    assert lyrics_context["job_id"] == lyrics_job["id"]
    assert lyrics_context["output_manifest_path"].endswith(f"/jobs/{lyrics_job['id']}/output_manifest.json")
    assert lyrics_context["artifacts"][0]["artifact_id"] == "lyrics_txt"


def test_submit_job_uses_ssh_runner_when_profile_is_server_mode(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Server lyrics",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    class Completed:
        def __init__(self, stdout: str = "ok\n") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if command[-1].startswith("cat "):
            job_id = job_id_from_output_manifest_command(command)
            return Completed(stdout=json.dumps(remote_output_fixture(project["id"], job_id=job_id)))
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    response = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["adapter"] == "ssh"
    assert job["status"] == "needs_review"
    project_after_job = client.get(f"/api/projects/{project['id']}").json()
    lyrics_stage = next(stage for stage in project_after_job["pipeline"] if stage["stage"] == "lyrics.generate")
    assert lyrics_stage["job_id"] == job["id"]
    assert job["id"].startswith("remote_")
    assert lyrics_stage["status"] == "needs_review"
    assert not (tmp_path / "projects" / project["id"] / "lyrics.json").exists()
    assert not (tmp_path / "projects" / project["id"] / "remote-pilot.json").exists()
    assert (tmp_path / "projects" / project["id"] / "remote-runs" / f"{job['id']}.json").exists()


def test_ssh_job_fails_when_output_manifest_is_missing(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Missing manifest",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    class Completed:
        def __init__(self, stdout: str = "ok\n", stderr: str = "", returncode: int = 0) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if command[-1].startswith("cat ") and command[-1].endswith("output_manifest.json"):
            return Completed(stdout="", stderr="cat: output_manifest.json: No such file", returncode=1)
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    detail = client.get(f"/api/jobs/{job['id']}").json()

    assert job["status"] == "failed"
    assert detail["status"] == "failed"
    assert detail["phase"] == "failed"
    assert detail["error"] == {"code": "runner_failed", "message": "Output manifest could not be read."}
    assert detail["preview"] is None
    assert detail["artifacts"] == []
    assert (tmp_path / "projects" / project["id"] / "remote-runs" / f"{job['id']}.json").exists()


def test_ssh_job_fails_when_output_manifest_contract_is_invalid(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Invalid manifest",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    class Completed:
        def __init__(self, stdout: str = "ok\n", stderr: str = "", returncode: int = 0) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if command[-1].startswith("cat ") and command[-1].endswith("output_manifest.json"):
            output = remote_output_fixture(project["id"], job_id="another_job")
            return Completed(stdout=json.dumps(output))
        if command[-1].startswith("cat ") and command[-1].endswith("worker.log"):
            return Completed(stdout="", stderr="cat: worker.log: No such file", returncode=1)
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    detail = client.get(f"/api/jobs/{job['id']}").json()
    log_response = client.get(f"/api/projects/{project['id']}/jobs/{job['id']}/log").json()

    assert job["status"] == "failed"
    assert detail["status"] == "failed"
    assert detail["message"] == "Output manifest failed contract validation."
    assert detail["preview"] is None
    assert detail["artifacts"] == []
    assert "job_id" in log_response["log"]


def test_ssh_job_fails_when_output_manifest_is_malformed_json(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Malformed manifest",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    class Completed:
        def __init__(self, stdout: str = "ok\n") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if command[-1].startswith("cat ") and command[-1].endswith("output_manifest.json"):
            return Completed(stdout="{not-json")
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    detail = client.get(f"/api/jobs/{job['id']}").json()

    assert job["status"] == "failed"
    assert detail["status"] == "failed"
    assert detail["message"] == "Output manifest is not valid JSON."
    assert detail["preview"] is None
    assert detail["artifacts"] == []


def test_submit_job_queues_when_ssh_worker_slot_is_busy(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Queued server lyrics",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )
    locks_dir = tmp_path / "projects" / ".studio" / "worker-locks"
    locks_dir.mkdir(parents=True)
    (locks_dir / "ssh_default.json").write_text(
        json.dumps(
            {
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": "remote_busy",
                "acquired_at": "2099-01-01T00:00:00+00:00",
                "heartbeat_at": "2099-01-01T00:00:00+00:00",
                "lease_expires_at": "2099-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        raise AssertionError("SSH worker should not run while the single-flight slot is busy")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    response = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["adapter"] == "ssh"
    assert job["message"] == "Waiting for SSH worker slot."
    project_after_job = client.get(f"/api/projects/{project['id']}").json()
    lyrics_stage = next(stage for stage in project_after_job["pipeline"] if stage["stage"] == "lyrics.generate")
    assert lyrics_stage["status"] == "queued"
    assert lyrics_stage["job_id"] == job["id"]
    job_detail = client.get(f"/api/jobs/{job['id']}").json()
    assert job_detail["status"] == "queued"
    assert job_detail["phase"] == "waiting_for_worker"
    assert job_detail["queue_position"] == 1
    assert job_detail["runner"]["mode"] == "single_flight"
    assert job_detail["runner"]["resource"] == "ssh_default"
    assert job_detail["runner"]["state"] == "waiting"
    assert job_detail["runner"]["auto_dispatch"] is True
    assert job_detail["runner"]["trigger"] is None
    assert job_detail["runner"]["attempt_id"] == job["attempt_id"]
    assert job_detail["started_at"] is None
    assert not (tmp_path / "projects" / project["id"] / "remote-runs" / f"{job['id']}.json").exists()


def test_cancel_queued_ssh_job_marks_pipeline_cancelled(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Cancelable server lyrics",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )
    locks_dir = tmp_path / "projects" / ".studio" / "worker-locks"
    locks_dir.mkdir(parents=True)
    (locks_dir / "ssh_default.json").write_text(
        json.dumps(
            {
                "lock_id": "lock_busy_test",
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": "remote_busy",
                "attempt_id": "attempt_busy",
                "acquired_at": "2099-01-01T00:00:00+00:00",
                "heartbeat_at": "2099-01-01T00:00:00+00:00",
                "lease_expires_at": "2099-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        raise AssertionError("SSH worker should not run while the single-flight slot is busy")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    response = client.post(f"/api/jobs/{job['id']}/cancel")

    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == "cancelled"
    assert detail["phase"] == "cancelled"
    assert detail["failure_reason"] == "operator_cancelled"
    assert detail["message"] == "Job cancelled by operator."
    project_after_cancel = client.get(f"/api/projects/{project['id']}").json()
    lyrics_stage = next(stage for stage in project_after_cancel["pipeline"] if stage["stage"] == "lyrics.generate")
    assert lyrics_stage["status"] == "cancelled"
    assert lyrics_stage["job_id"] == job["id"]
    events = client.get(f"/api/jobs/{job['id']}/events").json()
    assert [event["event"] for event in events] == ["queued", "cancelled"]


def test_retry_cancelled_ssh_job_creates_new_attempt(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Retry server lyrics",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )
    locks_dir = tmp_path / "projects" / ".studio" / "worker-locks"
    locks_dir.mkdir(parents=True)
    (locks_dir / "ssh_default.json").write_text(
        json.dumps(
            {
                "lock_id": "lock_busy_test",
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": "remote_busy",
                "attempt_id": "attempt_busy",
                "acquired_at": "2099-01-01T00:00:00+00:00",
                "heartbeat_at": "2099-01-01T00:00:00+00:00",
                "lease_expires_at": "2099-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    def fake_run(*args, **kwargs):
        raise AssertionError("SSH worker should not run while the single-flight slot is busy")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    cancelled_job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    client.post(f"/api/jobs/{cancelled_job['id']}/cancel")
    response = client.post(f"/api/jobs/{cancelled_job['id']}/retry")

    assert response.status_code == 202
    result = response.json()
    assert result["retried_from_job_id"] == cancelled_job["id"]
    retry_detail = result["job"]
    assert retry_detail["id"] != cancelled_job["id"]
    assert retry_detail["status"] == "queued"
    assert retry_detail["queue_position"] == 1
    project_after_retry = client.get(f"/api/projects/{project['id']}").json()
    lyrics_stage = next(stage for stage in project_after_retry["pipeline"] if stage["stage"] == "lyrics.generate")
    assert lyrics_stage["status"] == "queued"
    assert lyrics_stage["job_id"] == retry_detail["id"]
    old_events = client.get(f"/api/jobs/{cancelled_job['id']}/events").json()
    new_events = client.get(f"/api/jobs/{retry_detail['id']}/events").json()
    assert [event["event"] for event in old_events] == ["queued", "cancelled", "retry_requested"]
    assert [event["event"] for event in new_events] == ["queued", "retry_of"]


def test_dispatch_next_runs_oldest_queued_ssh_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_ADMIN_TOKEN", "test-admin-token")
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Dispatch server lyrics",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )
    locks_dir = tmp_path / "projects" / ".studio" / "worker-locks"
    locks_dir.mkdir(parents=True)
    lock_file = locks_dir / "ssh_default.json"
    lock_file.write_text(
        json.dumps(
            {
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": "remote_busy",
                "acquired_at": "2099-01-01T00:00:00+00:00",
                "heartbeat_at": "2099-01-01T00:00:00+00:00",
                "lease_expires_at": "2099-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    class Completed:
        def __init__(self, stdout: str = "ok\n") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if command[-1].startswith("cat "):
            job_id = job_id_from_output_manifest_command(command)
            return Completed(stdout=json.dumps(remote_output_fixture(project["id"], job_id=job_id)))
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    queued_job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    lock_file.unlink()
    response = client.post(
        "/api/jobs/dispatch-next",
        json={"adapter": "ssh", "resource": "ssh_default"},
        headers={"X-Studio-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "dispatched"
    assert result["job_id"] == queued_job["id"]
    assert result["previous_status"] == "queued"
    assert result["new_status"] == "needs_review"
    assert result["queue_position"] == 0
    assert result["runner"]["mode"] == "single_flight"
    assert result["runner"]["resource"] == "ssh_default"
    assert result["runner"]["state"] == "released"
    assert result["runner"]["auto_dispatch"] is True
    assert result["runner"]["trigger"] == "manual"
    assert result["runner"]["attempt_id"] == queued_job["attempt_id"]
    dispatched_detail = client.get(f"/api/jobs/{queued_job['id']}").json()
    assert dispatched_detail["status"] == "succeeded"
    assert dispatched_detail["phase"] == "awaiting_review"
    assert dispatched_detail["preview"]["lyrics"] == "Colors in the rhythm\n"
    project_after_dispatch = client.get(f"/api/projects/{project['id']}").json()
    lyrics_stage = next(stage for stage in project_after_dispatch["pipeline"] if stage["stage"] == "lyrics.generate")
    assert lyrics_stage["status"] == "needs_review"
    assert (tmp_path / "projects" / project["id"] / "remote-runs" / f"{queued_job['id']}.json").exists()
    assert not lock_file.exists()


def test_submit_job_auto_drains_existing_ssh_queue_before_new_job(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    series = create_minimal_series(client)
    older_project = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Older queue song",
        topic="colors",
        objective="child repeats color words",
        vocabulary=["red", "blue"],
    )
    client.post(f"/api/projects/{older_project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )
    locks_dir = tmp_path / "projects" / ".studio" / "worker-locks"
    locks_dir.mkdir(parents=True)
    lock_file = locks_dir / "ssh_default.json"
    lock_file.write_text(
        json.dumps(
            {
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": "remote_busy",
                "acquired_at": "2099-01-01T00:00:00+00:00",
                "heartbeat_at": "2099-01-01T00:00:00+00:00",
                "lease_expires_at": "2099-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    job_projects: dict[str, str] = {}
    run_order: list[str] = []

    class Completed:
        def __init__(self, stdout: str = "ok\n") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if input and "job_manifest.json" in input:
            manifest = extract_job_manifest_from_ssh_script(input)
            job_projects[manifest["job_id"]] = manifest["project_id"]
            run_order.append(manifest["job_id"])
            return Completed(stdout="remote script completed\n")
        if command[-1].startswith("cat ") and command[-1].endswith("output_manifest.json"):
            job_id = command[-1].split("/jobs/", 1)[1].split("/", 1)[0]
            return Completed(stdout=json.dumps(remote_output_fixture(job_projects[job_id], job_id=job_id)))
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    older_job = client.post(f"/api/projects/{older_project['id']}/jobs/lyrics.generate").json()
    assert older_job["status"] == "queued"
    assert run_order == []
    queue_status = client.get("/api/queue/ssh-default").json()
    assert queue_status["queued_count"] == 1
    assert queue_status["queued_job_ids"] == [older_job["id"]]
    assert queue_status["current_job_id"] == "remote_busy"

    lock_file.unlink()
    newer_project = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Newer queue song",
        topic="shapes",
        objective="child repeats shape words",
        vocabulary=["circle", "square"],
    )
    client.post(f"/api/projects/{newer_project['id']}/stages/brief.generate/approve", json={})
    newer_job = client.post(f"/api/projects/{newer_project['id']}/jobs/lyrics.generate").json()

    older_detail = client.get(f"/api/jobs/{older_job['id']}").json()
    newer_detail = client.get(f"/api/jobs/{newer_job['id']}").json()
    assert run_order == [older_job["id"], newer_job["id"]]
    assert older_detail["status"] == "succeeded"
    assert older_detail["phase"] == "awaiting_review"
    assert older_detail["queue_position"] == 0
    assert newer_detail["status"] == "succeeded"
    assert newer_detail["phase"] == "awaiting_review"
    assert newer_detail["queue_position"] == 0
    queue_status_after = client.get("/api/queue/ssh-default").json()
    assert queue_status_after["queued_count"] == 0
    assert queue_status_after["current_job_id"] is None
    older_events = client.get(f"/api/jobs/{older_job['id']}/events").json()
    assert [event["event"] for event in older_events] == [
        "queued",
        "lock_acquired",
        "ssh_started",
        "artifact_saved",
        "completed",
        "lock_released",
        "auto_drain_triggered",
    ]
    assert client.get(f"/api/jobs/{older_job['id']}/events?after=3").json()[0]["event"] == "artifact_saved"
    assert not lock_file.exists()
    assert (tmp_path / "projects" / older_project["id"] / "remote-runs" / f"{older_job['id']}.json").exists()
    assert (tmp_path / "projects" / newer_project["id"] / "remote-runs" / f"{newer_job['id']}.json").exists()


def test_expired_ssh_lock_fails_stale_job_and_allows_next_dispatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_ADMIN_TOKEN", "test-admin-token")
    client = make_client(tmp_path)
    series = create_minimal_series(client)
    stale_project = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Stale lock song",
        topic="colors",
        objective="child repeats color words",
        vocabulary=["red", "blue"],
    )
    client.post(f"/api/projects/{stale_project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )
    locks_dir = tmp_path / "projects" / ".studio" / "worker-locks"
    locks_dir.mkdir(parents=True)
    lock_file = locks_dir / "ssh_default.json"
    lock_file.write_text(
        json.dumps(
            {
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": "remote_busy",
                "acquired_at": "2099-01-01T00:00:00+00:00",
                "heartbeat_at": "2099-01-01T00:00:00+00:00",
                "lease_expires_at": "2099-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    job_projects: dict[str, str] = {}
    run_order: list[str] = []

    class Completed:
        def __init__(self, stdout: str = "ok\n") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if input and "job_manifest.json" in input:
            manifest = extract_job_manifest_from_ssh_script(input)
            job_projects[manifest["job_id"]] = manifest["project_id"]
            run_order.append(manifest["job_id"])
            return Completed(stdout="remote script completed\n")
        if command[-1].startswith("cat ") and command[-1].endswith("output_manifest.json"):
            job_id = command[-1].split("/jobs/", 1)[1].split("/", 1)[0]
            return Completed(stdout=json.dumps(remote_output_fixture(job_projects[job_id], job_id=job_id)))
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    stale_job = client.post(f"/api/projects/{stale_project['id']}/jobs/lyrics.generate").json()
    assert stale_job["status"] == "queued"
    lock_file.write_text(
        json.dumps(
            {
                "lock_id": "lock_stale_test",
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": stale_job["id"],
                "attempt_id": stale_job["attempt_id"],
                "acquired_at": "2099-01-01T00:00:00+00:00",
                "heartbeat_at": "2099-01-01T00:00:00+00:00",
                "lease_expires_at": "2099-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    heartbeat = client.post(
        "/api/jobs/locks/heartbeat",
        json={
            "adapter": "ssh",
            "resource_key": "ssh_default",
            "job_id": stale_job["id"],
            "lock_id": "lock_stale_test",
            "attempt_id": stale_job["attempt_id"],
        },
        headers={"X-Studio-Admin-Token": "test-admin-token"},
    ).json()
    assert heartbeat["status"] == "renewed"
    assert heartbeat["heartbeat_at"] is not None
    assert heartbeat["lease_expires_at"] is not None
    lock_file.write_text(
        json.dumps(
            {
                "lock_id": "lock_stale_test",
                "resource_key": "ssh_default",
                "adapter": "ssh",
                "job_id": stale_job["id"],
                "attempt_id": stale_job["attempt_id"],
                "acquired_at": "2000-01-01T00:00:00+00:00",
                "heartbeat_at": "2000-01-01T00:00:00+00:00",
                "lease_expires_at": "2000-01-01T00:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    next_project = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="After stale lock song",
        topic="shapes",
        objective="child repeats shape words",
        vocabulary=["circle", "square"],
    )
    client.post(f"/api/projects/{next_project['id']}/stages/brief.generate/approve", json={})
    next_job = client.post(f"/api/projects/{next_project['id']}/jobs/lyrics.generate").json()

    stale_detail = client.get(f"/api/jobs/{stale_job['id']}").json()
    next_detail = client.get(f"/api/jobs/{next_job['id']}").json()
    stale_events = client.get(f"/api/jobs/{stale_job['id']}/events").json()
    queue_status = client.get("/api/queue/ssh-default").json()

    assert run_order == [next_job["id"]]
    assert stale_detail["status"] == "failed"
    assert stale_detail["phase"] == "failed"
    assert stale_detail["error"]["code"] == "runner_failed"
    assert "lease expired" in stale_detail["error"]["message"]
    assert [event["event"] for event in stale_events] == ["queued", "lock_heartbeat", "stale_lock_recovered"]
    assert next_detail["status"] == "succeeded"
    assert next_detail["phase"] == "awaiting_review"
    assert queue_status["queued_count"] == 0
    assert queue_status["current_job_id"] is None
    assert not lock_file.exists()


def test_dispatch_next_requires_admin_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_ADMIN_TOKEN", "test-admin-token")
    client = make_client(tmp_path)

    missing = client.post("/api/jobs/dispatch-next", json={"adapter": "ssh", "resource": "ssh_default"})
    wrong = client.post(
        "/api/jobs/locks/recover-stale",
        json={"adapter": "ssh", "resource_key": "ssh_default"},
        headers={"X-Studio-Admin-Token": "wrong-token"},
    )

    assert missing.status_code == 401
    assert missing.json()["detail"] == "Invalid studio admin token"
    assert wrong.status_code == 403
    assert wrong.json()["detail"] == "Invalid studio admin token"


def test_dispatch_next_is_fail_closed_without_configured_admin_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("STUDIO_ADMIN_TOKEN", raising=False)
    client = make_client(tmp_path)

    response = client.post(
        "/api/jobs/dispatch-next",
        json={"adapter": "ssh", "resource": "ssh_default"},
        headers={"X-Studio-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Studio admin token is not configured"


def test_dispatch_next_is_idle_without_queued_ssh_jobs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STUDIO_ADMIN_TOKEN", "test-admin-token")
    client = make_client(tmp_path)
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    response = client.post(
        "/api/jobs/dispatch-next",
        json={"adapter": "ssh", "resource": "ssh_default"},
        headers={"X-Studio-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "idle",
        "reason": "no_queued_jobs_or_lock_busy",
        "job_id": None,
        "previous_status": None,
        "new_status": None,
        "queue_position": 0,
        "runner": None,
    }


def test_remote_job_artifact_contract_is_exposed_by_backend(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Server lyrics",
            "topic": "colors",
            "age_range": "3-5",
            "emotional_tone": "calm",
            "educational_goal": "child names one color",
            "characters": [],
        },
    ).json()
    client.post(f"/api/projects/{project['id']}/stages/brief.generate/approve", json={})
    client.put(
        "/api/server/profile",
        json={
            "mode": "ssh",
            "label": "GPU tower",
            "host": "studio.local",
            "username": "daniel",
            "port": 22,
            "remote_root": "/home/daniel/aikiddo-worker",
            "ssh_key_path": "~/.ssh/id_ed25519",
            "tailscale_name": "studio",
        },
    )

    class Completed:
        def __init__(self, stdout: str = "ok\n", stdout_bytes: bytes | None = None) -> None:
            self.returncode = 0
            self.stdout = stdout if stdout_bytes is None else stdout_bytes
            self.stderr = ""

    def fake_run(command, *, input=None, text=None, capture_output=None, timeout=None, check=None):
        if command[-1].startswith("cat ") and command[-1].endswith("output_manifest.json"):
            job_id = job_id_from_output_manifest_command(command)
            return Completed(stdout=json.dumps(remote_output_fixture(project["id"], job_id=job_id)))
        if command[-1].startswith("cat ") and command[-1].endswith("worker.log"):
            return Completed(stdout="job=remote_job_from_fixture\nstorage=server\n")
        if command[-1].startswith("cat ") and command[-1].endswith("lyrics.txt"):
            return Completed(stdout_bytes=b"Colors in the rhythm\n")
        return Completed(stdout="remote script completed\n")

    monkeypatch.setattr("studio_api.ssh_generation.subprocess.run", fake_run)

    job = client.post(f"/api/projects/{project['id']}/jobs/lyrics.generate").json()
    artifacts = client.get(f"/api/projects/{project['id']}/jobs/{job['id']}/artifacts")
    log_response = client.get(f"/api/projects/{project['id']}/jobs/{job['id']}/log")
    artifact_response = client.get(f"/api/projects/{project['id']}/jobs/{job['id']}/artifacts/lyrics_txt")
    job_detail_response = client.get(f"/api/jobs/{job['id']}")

    assert artifacts.status_code == 200
    assert [artifact["artifact_id"] for artifact in artifacts.json()] == [
        "lyrics_txt",
        "song_plan_json",
        "safety_notes_json",
        "audio_preview_wav",
    ]
    assert artifacts.json()[0]["storage_key"].startswith(f"projects/{project['id']}/jobs/")
    assert log_response.status_code == 200
    assert "storage=server" in log_response.json()["log"]
    assert artifact_response.status_code == 200
    assert artifact_response.text == "Colors in the rhythm\n"
    assert artifact_response.headers["x-artifact-sha256"] == "7fd5f87915ff579eb9909bbc9d11f5de96910160f7b24719288346c7f1f2d57c"
    assert job_detail_response.status_code == 200
    job_detail = job_detail_response.json()
    assert job_detail["id"] == job["id"]
    assert job_detail["status"] == "succeeded"
    assert job_detail["phase"] == "awaiting_review"
    assert job_detail["preview"]["lyrics"] == "Colors in the rhythm\n"
    assert job_detail["artifacts"][0]["download_url"].endswith(f"/jobs/{job['id']}/artifacts/lyrics_txt")
    assert job_detail["log_url"].endswith(f"/jobs/{job['id']}/log")
    assert job_detail["error"] is None
    assert job_detail["queue_position"] == 0
    assert job_detail["runner"]["mode"] == "single_flight"
    assert job_detail["runner"]["resource"] == "ssh_default"
    assert job_detail["runner"]["state"] == "released"
    assert job_detail["runner"]["auto_dispatch"] is True
    assert job_detail["runner"]["trigger"] is None
    assert job_detail["runner"]["attempt_id"] == job["attempt_id"]
    assert job_detail["started_at"] == job_detail["created_at"]
    assert job_detail["finished_at"] == job_detail["updated_at"]


def test_create_project_persists_project_and_brief(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/projects",
        json={
            "title": "Szczoteczka bohater",
            "topic": "mycie zebow",
            "age_range": "3-5",
            "emotional_tone": "radosc",
            "educational_goal": "dziecko pamieta o porannym myciu zebow",
            "characters": ["toothbrush_friend_v1"],
        },
    )

    assert response.status_code == 201
    project = response.json()
    project_id = project["id"]
    project_dir = tmp_path / "projects" / project_id

    assert project["title"] == "Szczoteczka bohater"
    assert project["pipeline"][0]["stage"] == "brief.generate"
    assert project["pipeline"][0]["status"] == "needs_review"

    saved_project = json.loads((project_dir / "project.json").read_text())
    saved_brief = json.loads((project_dir / "brief.json").read_text())
    assert saved_project["id"] == project_id
    assert saved_brief["topic"] == "mycie zebow"
    assert saved_brief["characters"] == ["toothbrush_friend_v1"]


def test_stage_catalog_exposes_display_names_without_renaming_stage_ids(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/stages/catalog")

    assert response.status_code == 200
    catalog = {item["stage"]: item for item in response.json()}
    assert catalog["render.full_episode"]["display_name"] == "Primary video"
    assert catalog["render.full_episode"]["future_stage"] == "render.primary_video"
    assert catalog["quality.compliance_report"]["display_name"] == "Safety, quality & rights review"
    assert catalog["quality.compliance_report"]["future_stage"] == "safety_quality_rights_review"


def test_series_bible_can_be_created_and_linked_to_project(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Action colors",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "energia",
            "educational_goal": "dziecko powtarza kolory po angielsku",
            "characters": [],
        },
    ).json()

    series_response = client.post(
        "/api/series",
        json={
            "name": "English Action Songs",
            "target_age_min": 3,
            "target_age_max": 5,
            "primary_language": "en",
            "secondary_language": "pl",
            "learning_domain": "ESL",
            "series_premise": "Short movement songs for preschool English practice.",
            "main_characters": [
                {
                    "name": "Mila",
                    "role": "teacher",
                    "visual_description": "Warm preschool teacher in simple bright 2D style.",
                    "personality": "calm, playful, precise",
                    "voice_notes": "clear pronunciation, medium tempo",
                }
            ],
            "visual_style": "bright 2D classroom scenes",
            "music_style": "upbeat call-and-response",
            "voice_rules": "simple words, clear pronunciation, no shouting",
            "safety_rules": ["no unsafe actions", "no fear pressure"],
            "forbidden_content": ["violence", "brand mascots", "endless-watch prompts"],
            "thumbnail_rules": "single clear action with high contrast object",
            "made_for_kids_default": True,
        },
    )

    assert series_response.status_code == 201
    series = series_response.json()
    assert series["status"] == "draft"
    assert series["name"] == "English Action Songs"

    link_response = client.put(f"/api/projects/{project['id']}/series", json={"series_id": series["id"]})

    assert link_response.status_code == 200
    linked_project = link_response.json()
    assert linked_project["series_id"] == series["id"]

    listed_series = client.get("/api/series")
    assert listed_series.status_code == 200
    assert [item["id"] for item in listed_series.json()] == [series["id"]]


def test_episode_spec_can_be_saved_approved_and_used_by_next_action(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={
            "title": "Colors with movement",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radosc",
            "educational_goal": "dziecko rozpoznaje pięć kolorów",
            "characters": [],
        },
    ).json()
    series = client.post(
        "/api/series",
        json={
            "name": "English Action Songs",
            "target_age_min": 3,
            "target_age_max": 5,
            "primary_language": "en",
            "learning_domain": "ESL",
            "series_premise": "Short movement songs for preschool English practice.",
            "main_characters": [],
            "visual_style": "bright 2D classroom scenes",
            "music_style": "upbeat call-and-response",
            "voice_rules": "clear pronunciation",
            "safety_rules": ["no unsafe actions"],
            "forbidden_content": ["violence"],
            "made_for_kids_default": True,
        },
    ).json()

    missing_strategy_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert missing_strategy_action["action_type"] == "define_series"
    assert missing_strategy_action["severity"] == "blocker"

    client.put(f"/api/projects/{project['id']}/series", json={"series_id": series["id"]})
    missing_spec_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert missing_spec_action["action_type"] == "complete_episode_spec"

    spec_response = client.put(
        f"/api/projects/{project['id']}/episode-spec",
        json={
            "working_title": "Colors Action Song",
            "topic": "basic colors",
            "target_age_min": 3,
            "target_age_max": 5,
            "learning_objective": {
                "statement": "Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
                "domain": "vocabulary",
                "vocabulary_terms": ["red", "blue", "yellow", "green", "purple"],
                "success_criteria": ["child repeats five colors", "child matches colors to objects"],
            },
            "format": "song_video",
            "target_duration_sec": 150,
            "audience_context": "both",
            "search_keywords": ["colors song", "preschool ESL"],
            "hook_idea": "Children point to classroom objects while singing colors.",
            "derivative_plan": {
                "make_shorts": True,
                "make_reels": True,
                "make_parent_teacher_page": True,
                "make_lyrics_page": True,
            },
            "made_for_kids": True,
            "risk_notes": "Avoid template repetition and brand-like characters.",
        },
    )

    assert spec_response.status_code == 200
    assert spec_response.json()["approval_status"] == "draft"

    needs_approval_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert needs_approval_action["action_type"] == "approve_episode_spec"

    approve_response = client.post(f"/api/projects/{project['id']}/episode-spec/approve", json={"note": "Cel edukacyjny jest konkretny."})
    assert approve_response.status_code == 200
    assert approve_response.json()["episode_spec"]["approval_status"] == "approved"

    check_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert check_action["action_type"] == "run_anti_repetition_check"

    client.post(f"/api/projects/{project['id']}/anti-repetition/run")
    brief_action = client.get(f"/api/projects/{project['id']}/next-action").json()
    assert brief_action["action_type"] == "approve"
    assert brief_action["stage"] == "brief.generate"


def test_mock_server_connection_is_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/api/server/test-connection")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "mock",
        "reachable": True,
        "message": "Mock GPU server is ready for local development.",
    }


def test_server_connection_requires_ssh_profile_by_default(tmp_path: Path) -> None:
    client = make_client(tmp_path, allow_local_mock=False)

    response = client.post("/api/server/test-connection")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "ssh",
        "reachable": False,
        "message": "SSH server profile is required before generation.",
    }


def test_server_profile_can_be_saved_and_loaded(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    save_response = client.put(
        "/api/server/profile",
        json={
            "mode": "mock",
            "label": "GPU tower draft",
            "host": "gpu-studio.tailnet.local",
            "username": "studio",
            "port": 22,
            "remote_root": "/srv/ai-kids-studio",
            "ssh_key_path": "~/.ssh/ai_kids_studio",
            "tailscale_name": "gpu-studio",
        },
    )

    assert save_response.status_code == 200
    profile = save_response.json()
    assert profile["label"] == "GPU tower draft"
    assert profile["host"] == "gpu-studio.tailnet.local"
    assert profile["remote_root"] == "/srv/ai-kids-studio"
    assert profile["updated_at"]

    loaded_response = client.get("/api/server/profile")
    assert loaded_response.status_code == 200
    assert loaded_response.json() == profile

    config_file = tmp_path / "projects" / ".studio" / "server-profile.json"
    saved = json.loads(config_file.read_text())
    assert saved["username"] == "studio"
    assert "password" not in saved


def test_mock_connection_uses_saved_server_profile(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.put(
        "/api/server/profile",
        json={
            "mode": "mock",
            "label": "GPU tower draft",
            "host": "gpu-studio.tailnet.local",
            "username": "studio",
            "port": 22,
            "remote_root": "/srv/ai-kids-studio",
            "ssh_key_path": "~/.ssh/ai_kids_studio",
            "tailscale_name": "gpu-studio",
        },
    )

    response = client.post("/api/server/test-connection")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "mock",
        "reachable": True,
        "message": "Mock GPU server profile 'GPU tower draft' is ready for local development.",
    }


def test_generation_requires_ssh_profile_by_default(tmp_path: Path) -> None:
    client = make_client(tmp_path, allow_local_mock=False)
    created = client.post(
        "/api/projects",
        json={
            "title": "Server required",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "spokój",
            "educational_goal": "dziecko rozpoznaje podstawowe kolory",
            "characters": [],
        },
    ).json()

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    response = client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")

    assert response.status_code == 409
    assert response.json() == {"detail": "SSH server profile is required before generation"}
    project = client.get(f"/api/projects/{created['id']}").json()
    lyric_stage = next(item for item in project["pipeline"] if item["stage"] == "lyrics.generate")
    assert lyric_stage["status"] == "pending"
    assert lyric_stage["job_id"] is None


def test_submit_mock_job_updates_pipeline_and_job_can_be_read(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowy refren",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "ciekawosc",
            "educational_goal": "dziecko rozpoznaje podstawowe kolory",
            "characters": [],
        },
    ).json()

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["project_id"] == created["id"]
    assert job["stage"] == "lyrics.generate"
    assert job["status"] == "needs_review"
    assert job["adapter"] == "mock"

    read_job = client.get(f"/api/jobs/{job['id']}")
    assert read_job.status_code == 200
    assert read_job.json()["id"] == job["id"]

    project = client.get(f"/api/projects/{created['id']}").json()
    lyric_stage = next(item for item in project["pipeline"] if item["stage"] == "lyrics.generate")
    assert lyric_stage["status"] == "needs_review"
    assert lyric_stage["job_id"] == job["id"]

    lyrics_file = tmp_path / "projects" / created["id"] / "lyrics.json"
    lyrics = json.loads(lyrics_file.read_text())
    assert lyrics["title"] == "Kolorowy refren"
    assert lyrics["chorus"]
    assert lyrics["verses"]
    assert lyrics["safety_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/lyrics")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == lyrics


def test_project_jobs_can_be_listed_in_creation_order(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Historia pracy",
            "topic": "rytmy",
            "age_range": "4-6",
            "emotional_tone": "energia",
            "educational_goal": "dziecko rozpoznaje prosty rytm",
            "characters": [],
        },
    ).json()

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    lyrics_job = client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate").json()
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    characters_job = client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve").json()

    response = client.get(f"/api/projects/{created['id']}/jobs")

    assert response.status_code == 200
    jobs = response.json()
    assert [job["id"] for job in jobs] == [lyrics_job["id"], characters_job["id"]]
    assert [job["stage"] for job in jobs] == ["lyrics.generate", "characters.import_or_approve"]
    assert [job["adapter"] for job in jobs] == ["mock", "mock"]
    assert jobs[0]["status"] == "needs_review"
    assert jobs[1]["status"] == "needs_review"


def test_project_stage_approvals_can_be_listed_in_approval_order(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Audyt akceptacji",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "spokój",
            "educational_goal": "dziecko rozpoznaje kolor czerwony",
            "characters": [],
        },
    ).json()

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={"note": "Brief gotowy."})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={"note": "Tekst bezpieczny."})

    response = client.get(f"/api/projects/{created['id']}/approvals")

    assert response.status_code == 200
    approvals = response.json()
    assert [approval["stage"] for approval in approvals] == ["brief.generate", "lyrics.generate"]
    assert [approval["note"] for approval in approvals] == ["Brief gotowy.", "Tekst bezpieczny."]
    assert [approval["status"] for approval in approvals] == ["completed", "completed"]
    assert approvals[0]["approved_at"] <= approvals[1]["approved_at"]


def test_project_next_action_guides_operator_through_review_and_run_steps(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Następny krok",
            "topic": "liczenie",
            "age_range": "4-6",
            "emotional_tone": "ciekawość",
            "educational_goal": "dziecko liczy do trzech",
            "characters": [],
        },
    ).json()
    series = client.post(
        "/api/series",
        json={
            "name": "Counting Songs",
            "target_age_min": 4,
            "target_age_max": 6,
            "primary_language": "pl",
            "learning_domain": "math",
            "series_premise": "Songs that teach early counting through simple movement.",
            "main_characters": [],
            "visual_style": "bright simple shapes",
            "music_style": "gentle clapping rhythm",
            "voice_rules": "slow and clear",
            "safety_rules": ["no unsafe actions"],
            "forbidden_content": ["fear"],
            "made_for_kids_default": True,
        },
    ).json()
    client.put(f"/api/projects/{created['id']}/series", json={"series_id": series["id"]})
    client.put(
        f"/api/projects/{created['id']}/episode-spec",
        json={
            "working_title": "Liczymy do trzech",
            "topic": "liczenie",
            "target_age_min": 4,
            "target_age_max": 6,
            "learning_objective": {
                "statement": "Dziecko liczy do trzech i powtarza liczby w rytmie piosenki.",
                "domain": "counting",
                "vocabulary_terms": ["jeden", "dwa", "trzy"],
                "success_criteria": ["child counts to three", "child repeats each number"],
            },
            "format": "song_video",
            "target_duration_sec": 120,
            "audience_context": "both",
            "search_keywords": ["liczenie do trzech", "piosenka dla dzieci"],
            "derivative_plan": {
                "make_shorts": True,
                "make_reels": True,
                "make_parent_teacher_page": True,
                "make_lyrics_page": True,
            },
            "made_for_kids": True,
        },
    )
    client.post(f"/api/projects/{created['id']}/episode-spec/approve", json={})
    client.post(f"/api/projects/{created['id']}/anti-repetition/run")

    first_action = client.get(f"/api/projects/{created['id']}/next-action")
    assert first_action.status_code == 200
    assert first_action.json() == {
        "action_type": "approve",
        "stage": "brief.generate",
        "label": "Brief",
        "message": "Brief czeka na akceptację operatora.",
        "severity": "info",
    }

    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    second_action = client.get(f"/api/projects/{created['id']}/next-action")
    assert second_action.status_code == 200
    assert second_action.json() == {
        "action_type": "run",
        "stage": "lyrics.generate",
        "label": "Tekst",
        "message": "Możesz uruchomić etap Tekst.",
        "severity": "info",
    }

    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    third_action = client.get(f"/api/projects/{created['id']}/next-action")
    assert third_action.status_code == 200
    assert third_action.json() == {
        "action_type": "approve",
        "stage": "lyrics.generate",
        "label": "Tekst",
        "message": "Tekst czeka na akceptację operatora.",
        "severity": "info",
    }


def test_cannot_start_stage_when_previous_review_gate_is_unapproved(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Zablokowany tekst",
            "topic": "mycie rąk",
            "age_range": "3-5",
            "emotional_tone": "spokoj",
            "educational_goal": "dziecko pamięta o myciu rąk",
            "characters": [],
        },
    ).json()

    response = client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")

    assert response.status_code == 409
    assert response.json()["detail"] == "Previous stage brief.generate must be completed first"


def test_storyboard_job_writes_reviewable_storyboard_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")

    response = client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "storyboard.generate"
    assert job["status"] == "needs_review"

    storyboard_file = tmp_path / "projects" / created["id"] / "storyboard.json"
    storyboard = json.loads(storyboard_file.read_text())
    assert storyboard["title"] == "Kolorowa przygoda"
    assert len(storyboard["scenes"]) == 4
    assert storyboard["scenes"][0]["visual_prompt"]
    assert storyboard["safety_checks"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/storyboard")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == storyboard

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "storyboard.generate")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_keyframes_job_writes_reviewable_keyframe_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "keyframes.generate"
    assert job["status"] == "needs_review"

    keyframes_file = tmp_path / "projects" / created["id"] / "keyframes.json"
    keyframes = json.loads(keyframes_file.read_text())
    assert keyframes["title"] == "Kolorowa przygoda"
    assert len(keyframes["frames"]) == 4
    assert keyframes["frames"][0]["scene_id"] == "scene_01_opening"
    assert keyframes["frames"][0]["image_prompt"]
    assert keyframes["consistency_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/keyframes")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == keyframes

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "keyframes.generate")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_video_scenes_job_writes_reviewable_video_scenes_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "video.scenes.generate"
    assert job["status"] == "needs_review"

    video_scenes_file = tmp_path / "projects" / created["id"] / "video-scenes.json"
    video_scenes = json.loads(video_scenes_file.read_text())
    assert video_scenes["title"] == "Kolorowa przygoda"
    assert len(video_scenes["scenes"]) == 4
    assert video_scenes["scenes"][0]["source_keyframe_id"] == "keyframe_01"
    assert video_scenes["scenes"][0]["motion_prompt"]
    assert video_scenes["render_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/video-scenes")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == video_scenes

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "video.scenes.generate")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_full_episode_render_writes_completed_episode_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "render.full_episode"
    assert job["status"] == "completed"

    episode_file = tmp_path / "projects" / created["id"] / "full-episode.json"
    episode = json.loads(episode_file.read_text())
    assert episode["title"] == "Kolorowa przygoda"
    assert episode["episode_slug"] == "kolorowa-przygoda"
    assert episode["duration_seconds"] == 44
    assert episode["scene_count"] == 4
    assert episode["assembly_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/full-episode")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == episode

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "render.full_episode")
    assert stage["status"] == "completed"
    assert stage["job_id"] == job["id"]


def test_reels_render_writes_completed_reels_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")

    response = client.post(f"/api/projects/{created['id']}/jobs/render.reels")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "render.reels"
    assert job["status"] == "completed"

    reels_file = tmp_path / "projects" / created["id"] / "reels.json"
    reels = json.loads(reels_file.read_text())
    assert reels["title"] == "Kolorowa przygoda"
    assert len(reels["reels"]) == 3
    assert reels["reels"][0]["aspect_ratio"] == "9:16"
    assert reels["reels"][0]["output_path"].endswith("reel-01.mp4")
    assert reels["distribution_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/reels")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == reels

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "render.reels")
    assert stage["status"] == "completed"
    assert stage["job_id"] == job["id"]


def test_compliance_report_writes_reviewable_quality_artifact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")
    client.post(f"/api/projects/{created['id']}/jobs/render.reels")

    response = client.post(f"/api/projects/{created['id']}/jobs/quality.compliance_report")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "quality.compliance_report"
    assert job["status"] == "needs_review"

    compliance_file = tmp_path / "projects" / created["id"] / "compliance-report.json"
    report = json.loads(compliance_file.read_text())
    assert report["title"] == "Kolorowa przygoda"
    assert report["overall_status"] == "ready_for_human_review"
    assert len(report["checks"]) >= 4
    assert report["checks"][0]["status"] == "pass"
    assert report["episode_output_path"].endswith("full-episode.mp4")
    assert report["reel_output_paths"][0].endswith("reel-01.mp4")
    assert report["operator_notes"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/compliance-report")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == report

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "quality.compliance_report")
    assert stage["status"] == "needs_review"
    assert stage["job_id"] == job["id"]


def test_publish_prepare_package_writes_completed_package_manifest(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")
    client.post(f"/api/projects/{created['id']}/jobs/render.reels")
    client.post(f"/api/projects/{created['id']}/jobs/quality.compliance_report")
    client.post(f"/api/projects/{created['id']}/stages/quality.compliance_report/approve", json={})

    response = client.post(f"/api/projects/{created['id']}/jobs/publish.prepare_package")

    assert response.status_code == 202
    job = response.json()
    assert job["stage"] == "publish.prepare_package"
    assert job["status"] == "completed"

    package_file = tmp_path / "projects" / created["id"] / "publish-package.json"
    package = json.loads(package_file.read_text())
    assert package["title"] == "Kolorowa przygoda"
    assert package["package_status"] == "ready"
    assert package["package_path"].endswith("publish/kolorowa-przygoda")
    assert package["episode_output_path"].endswith("full-episode.mp4")
    assert package["reel_output_paths"][0].endswith("reel-01.mp4")
    assert "compliance-report.json" in package["included_manifests"]
    assert package["publishing_metadata"]["audience"] == "3-5"
    assert package["operator_checklist"]

    artifact_response = client.get(f"/api/projects/{created['id']}/artifacts/publish-package")
    assert artifact_response.status_code == 200
    assert artifact_response.json() == package

    project = client.get(f"/api/projects/{created['id']}").json()
    stage = next(item for item in project["pipeline"] if item["stage"] == "publish.prepare_package")
    assert stage["status"] == "completed"
    assert stage["job_id"] == job["id"]


def test_anti_repetition_report_flags_similar_project_in_same_series(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    series = create_minimal_series(client)
    first = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )
    second = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )

    response = client.post(f"/api/projects/{second['id']}/anti-repetition/run")

    assert response.status_code == 200
    report = response.json()
    assert report["project_id"] == second["id"]
    assert report["series_id"] == series["id"]
    assert report["status"] == "blocker"
    assert report["score"] >= 0.7
    assert report["compared_projects_count"] == 1
    assert report["closest_matches"][0]["project_id"] == first["id"]
    assert "similar title" in report["closest_matches"][0]["reasons"]

    saved_response = client.get(f"/api/projects/{second['id']}/anti-repetition")
    assert saved_response.status_code == 200
    assert saved_response.json()["id"] == report["id"]


def test_anti_repetition_ignores_projects_from_other_series(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    first_series = create_minimal_series(client, "Colors Songs")
    second_series = create_minimal_series(client, "Routine Songs")
    create_project_with_episode_spec(
        client,
        series_id=first_series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )
    second = create_project_with_episode_spec(
        client,
        series_id=second_series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )

    response = client.post(f"/api/projects/{second['id']}/anti-repetition/run")

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "ok"
    assert report["score"] == 0
    assert report["compared_projects_count"] == 0
    assert report["closest_matches"] == []


def test_next_action_surfaces_anti_repetition_blocker_before_pipeline_run(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    series = create_minimal_series(client)
    create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )
    second = create_project_with_episode_spec(
        client,
        series_id=series["id"],
        title="Colors Action Song",
        topic="basic colors",
        objective="Dziecko 3-5 lat rozpoznaje i powtarza pięć kolorów po angielsku.",
        vocabulary=["red", "blue", "yellow", "green", "purple"],
    )

    missing_report_action = client.get(f"/api/projects/{second['id']}/next-action").json()
    assert missing_report_action["action_type"] == "run_anti_repetition_check"

    client.post(f"/api/projects/{second['id']}/anti-repetition/run")
    blocker_action = client.get(f"/api/projects/{second['id']}/next-action").json()

    assert blocker_action["action_type"] == "fix_repetition_risk"
    assert blocker_action["severity"] == "blocker"
    assert "zbyt podobny" in blocker_action["message"]


def test_artifact_inventory_lists_project_manifest_files(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Kolorowa przygoda",
            "topic": "kolory",
            "age_range": "3-5",
            "emotional_tone": "radość",
            "educational_goal": "dziecko rozpoznaje kolory w scenach",
            "characters": ["rainbow_friend_v1"],
        },
    ).json()
    client.post(f"/api/projects/{created['id']}/stages/brief.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/lyrics.generate")
    client.post(f"/api/projects/{created['id']}/stages/lyrics.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/characters.import_or_approve")
    client.post(f"/api/projects/{created['id']}/stages/characters.import_or_approve/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/audio.generate_or_import")
    client.post(f"/api/projects/{created['id']}/jobs/storyboard.generate")
    client.post(f"/api/projects/{created['id']}/stages/storyboard.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/keyframes.generate")
    client.post(f"/api/projects/{created['id']}/stages/keyframes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/video.scenes.generate")
    client.post(f"/api/projects/{created['id']}/stages/video.scenes.generate/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/render.full_episode")
    client.post(f"/api/projects/{created['id']}/jobs/render.reels")
    client.post(f"/api/projects/{created['id']}/jobs/quality.compliance_report")
    client.post(f"/api/projects/{created['id']}/stages/quality.compliance_report/approve", json={})
    client.post(f"/api/projects/{created['id']}/jobs/publish.prepare_package")

    response = client.get(f"/api/projects/{created['id']}/artifacts")

    assert response.status_code == 200
    inventory = response.json()
    filenames = [item["file_name"] for item in inventory]
    assert filenames == [
        "brief.json",
        "lyrics.json",
        "storyboard.json",
        "keyframes.json",
        "video-scenes.json",
        "full-episode.json",
        "reels.json",
        "compliance-report.json",
        "publish-package.json",
    ]
    publish_item = next(item for item in inventory if item["file_name"] == "publish-package.json")
    assert publish_item["artifact_type"] == "publish_package"
    assert publish_item["available"] is True
    assert publish_item["relative_path"].endswith("publish-package.json")


def test_approve_review_stage_marks_it_completed_and_writes_review(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Zatwierdzany brief",
            "topic": "sprzatanie zabawek",
            "age_range": "3-5",
            "emotional_tone": "spokoj",
            "educational_goal": "dziecko odkłada zabawki po zabawie",
            "characters": [],
        },
    ).json()

    response = client.post(
        f"/api/projects/{created['id']}/stages/brief.generate/approve",
        json={"note": "Brief jest bezpieczny i gotowy do tekstu."},
    )

    assert response.status_code == 200
    project = response.json()
    brief_stage = next(item for item in project["pipeline"] if item["stage"] == "brief.generate")
    assert brief_stage["status"] == "completed"

    review_file = tmp_path / "projects" / created["id"] / "reviews" / "brief.generate.approval.json"
    review = json.loads(review_file.read_text())
    assert review["stage"] == "brief.generate"
    assert review["status"] == "completed"
    assert review["note"] == "Brief jest bezpieczny i gotowy do tekstu."


def test_cannot_approve_stage_that_is_not_waiting_for_review(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/projects",
        json={
            "title": "Za wczesna akceptacja",
            "topic": "liczenie",
            "age_range": "3-5",
            "emotional_tone": "ciekawosc",
            "educational_goal": "dziecko liczy do pięciu",
            "characters": [],
        },
    ).json()

    response = client.post(f"/api/projects/{created['id']}/stages/audio.generate_or_import/approve", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "Stage is not waiting for review"
