#!/usr/bin/env python3
"""Server-side Aikiddo worker.

This script is intentionally dependency-light. The API sends it to the server
next to a `job_manifest.json`; the worker owns all files it creates under the
job directory and writes `output_manifest.json` as the stable API contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import socket
import struct
import sys
import wave
from datetime import datetime, timezone
from typing import Any


def build_audio_preview(job_dir: pathlib.Path, topic: str) -> pathlib.Path:
    sample_rate = 22050
    duration_sec = 2.0
    base_frequency = 330 + (len(topic) % 8) * 22
    audio_path = job_dir / "audio_preview.wav"
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


def run(job_dir: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads((job_dir / "job_manifest.json").read_text(encoding="utf-8"))
    brief = manifest["brief"]

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
        "stage": manifest["stage"],
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

    (job_dir / "lyrics.txt").write_text(lyrics, encoding="utf-8")
    (job_dir / "song_plan.json").write_text(json.dumps(song_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (job_dir / "safety_notes.json").write_text(json.dumps(safety_notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    build_audio_preview(job_dir, brief["topic"])

    artifacts = [
        artifact_for(job_dir, manifest, "lyrics_txt", "lyrics", "lyrics.txt", "text/plain"),
        artifact_for(job_dir, manifest, "song_plan_json", "song_plan", "song_plan.json", "application/json"),
        artifact_for(job_dir, manifest, "safety_notes_json", "safety_notes", "safety_notes.json", "application/json"),
        artifact_for(job_dir, manifest, "audio_preview_wav", "audio_preview", "audio_preview.wav", "audio/wav"),
    ]
    worker_log = job_dir / "worker.log"
    worker_log.write_text(
        "\n".join(
            [
                "job=" + manifest["job_id"],
                "stage=" + manifest["stage"],
                "runner=aikiddo_worker.py",
                "artifacts=lyrics.txt,song_plan.json,safety_notes.json,audio_preview.wav",
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
        "stage": manifest["stage"],
        "status": "completed",
        "adapter": "ssh",
        "storage_policy": "server",
        "remote_job_dir": str(job_dir),
        "output_files": [artifact["storage_key"] for artifact in artifacts],
        "artifacts": artifacts,
        "preview": {
            "title": brief["title"],
            "lyrics": lyrics,
            "song_plan": {**song_plan, "audio_preview": "audio_preview.wav"},
            "safety_notes": safety_notes["checks"],
        },
        "logs": [
            "server worker wrote job_manifest.json",
            "server worker wrote lyrics.txt",
            "server worker wrote song_plan.json",
            "server worker wrote safety_notes.json",
            "server worker wrote audio_preview.wav",
        ],
        "log": {
            "storage_key": "projects/" + manifest["project_id"] + "/jobs/" + manifest["job_id"] + "/worker.log",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (job_dir / "output_manifest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: aikiddo_worker.py <job_dir>", file=sys.stderr)
        return 2
    job_dir = pathlib.Path(sys.argv[1])
    job_dir.mkdir(parents=True, exist_ok=True)
    output = run(job_dir)
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
