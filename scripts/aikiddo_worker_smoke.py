#!/usr/bin/env python3
"""Run a deterministic end-to-end smoke test for the Aikiddo worker.

This script is intended for a fresh Ubuntu/SSH host before enabling real
provider calls. It validates that Python, filesystem writes, upstream manifest
threading, and the worker contract are healthy without requiring OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


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


def slugify(value: str) -> str:
    return "-".join("".join(character.lower() if character.isalnum() else " " for character in value).split())


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def brief_payload() -> dict[str, Any]:
    return {
        "id": "smoke_brief",
        "title": "Smoke Test Song",
        "topic": "friendly routines",
        "age_range": "3-5",
        "emotional_tone": "calm",
        "educational_goal": "child repeats one safe routine phrase",
        "characters": ["routine_friend_v1"],
        "forbidden_motifs": ["fear pressure", "unsafe imitation"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def run_stage(*, root: pathlib.Path, worker_path: pathlib.Path, stage: str, upstream: list[dict[str, Any]]) -> dict[str, Any]:
    job_id = f"smoke_{slugify(stage)}"
    job_dir = root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "job.v1",
        "job_id": job_id,
        "project_id": "smoke_project",
        "stage": stage,
        "job_type": "kids_song_pilot",
        "adapter": "ssh",
        "pipeline_context": upstream,
        "brief": brief_payload(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(job_dir / "job_manifest.json", manifest)

    env = {**os.environ, "AIKIDDO_WORKER_MODE": "deterministic"}
    result = subprocess.run(
        [sys.executable, str(worker_path), str(job_dir)],
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{stage} failed with code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

    output_path = job_dir / "output_manifest.json"
    if not output_path.exists():
        raise RuntimeError(f"{stage} did not write output_manifest.json")
    output = json.loads(output_path.read_text(encoding="utf-8"))
    if output.get("status") != "completed":
        raise RuntimeError(f"{stage} completed with unexpected status {output.get('status')!r}")
    if not output.get("artifacts"):
        raise RuntimeError(f"{stage} did not produce artifacts")
    return {
        "stage": stage,
        "status": output["status"],
        "job_id": job_id,
        "output_manifest_path": str(output_path),
        "artifacts": output["artifacts"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Aikiddo worker smoke test.")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("/tmp/aikiddo-worker-smoke"))
    args = parser.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    worker_path = repo_root / "scripts" / "aikiddo_worker.py"
    args.root.mkdir(parents=True, exist_ok=True)

    upstream: list[dict[str, Any]] = []
    for stage in PIPELINE_STAGES:
        upstream.append(run_stage(root=args.root, worker_path=worker_path, stage=stage, upstream=upstream))

    final_manifest = pathlib.Path(upstream[-1]["output_manifest_path"])
    print(f"aikiddo_worker_smoke=ok root={args.root} final_stage={PIPELINE_STAGES[-1]} final_manifest={final_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
