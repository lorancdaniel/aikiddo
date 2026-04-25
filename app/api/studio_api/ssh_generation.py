import json
import shlex
import subprocess
from uuid import uuid4

from .models import Brief, GenerationArtifact, GenerationPreview, RemotePilotRun, ServerConnection, ServerProfile, utc_now


class SshGenerationServer:
    adapter = "ssh"

    def _ssh_base_command(self, profile: ServerProfile) -> list[str]:
        command = ["ssh", "-o", "BatchMode=yes", "-p", str(profile.port)]
        if profile.ssh_key_path.strip():
            command.extend(["-i", profile.ssh_key_path])
        command.append(f"{profile.username}@{profile.host}")
        return command

    def test_connection(self, profile: ServerProfile) -> ServerConnection:
        result = subprocess.run(
            [*self._ssh_base_command(profile), "hostname && whoami"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "SSH connection failed"
            return ServerConnection(mode="ssh", reachable=False, message=message)
        return ServerConnection(mode="ssh", reachable=True, message=result.stdout.strip())

    def run_remote_pilot(self, project_id: str, brief: Brief, stage: str, profile: ServerProfile) -> RemotePilotRun:
        now = utc_now()
        job_id = f"remote_{uuid4().hex[:12]}"
        remote_job_dir = f"{profile.remote_root.rstrip('/')}/jobs/{job_id}"
        job_manifest_path = f"{remote_job_dir}/job_manifest.json"
        output_manifest_path = f"{remote_job_dir}/output_manifest.json"
        job_manifest = {
            "schema_version": "job.v1",
            "job_id": job_id,
            "project_id": project_id,
            "stage": stage,
            "job_type": "kids_song_pilot",
            "adapter": self.adapter,
            "generation": {
                "runner": "remote_ssh",
                "mode": "real",
                "timeout_sec": 600,
            },
            "storage": {
                "server_owned": True,
                "artifact_root_policy": "project/job scoped",
                "client_may_upload_outputs": False,
            },
            "brief": brief.model_dump(mode="json"),
            "created_at": now,
        }
        manifest_json = json.dumps(job_manifest, ensure_ascii=False, indent=2)
        remote_script = f"""set -euo pipefail
job_dir={shlex.quote(remote_job_dir)}
mkdir -p "$job_dir"
cat > "$job_dir/job_manifest.json" <<'JSON'
{manifest_json}
JSON
python3 - "$job_dir" <<'PY'
import json
import hashlib
import pathlib
import socket
import sys
from datetime import datetime, timezone

job_dir = pathlib.Path(sys.argv[1])
manifest = json.loads((job_dir / "job_manifest.json").read_text(encoding="utf-8"))
brief = manifest["brief"]

lyrics = "\\n".join([
    brief["title"],
    "",
    "[Verse]",
    "We name it slowly, then we sing it clear,",
    "Small bright words that little voices hear.",
    "",
    "[Chorus]",
    brief["topic"].capitalize() + " in the rhythm, one more time,",
    "Clap it, say it, keep it kind.",
]) + "\\n"
song_plan = {{
    "title": brief["title"],
    "topic": brief["topic"],
    "age_range": brief["age_range"],
    "stage": manifest["stage"],
    "duration_target_sec": 60,
    "sections": ["verse", "chorus"],
    "storage_policy": "server",
}}
safety_notes = {{
    "status": "ready_for_human_review",
    "checks": [
        "age range is explicit",
        "educational topic is explicit",
        "no direct publishing without human approval",
    ],
    "host": socket.gethostname(),
}}
preview = {{
    "title": brief["title"],
    "lyrics": lyrics,
    "song_plan": song_plan,
    "safety_notes": safety_notes["checks"],
}}
files = [
    ("lyrics_txt", "lyrics", "lyrics.txt", "text/plain", lyrics),
    ("song_plan_json", "song_plan", "song_plan.json", "application/json", json.dumps(song_plan, ensure_ascii=False, indent=2) + "\\n"),
    ("safety_notes_json", "safety_notes", "safety_notes.json", "application/json", json.dumps(safety_notes, ensure_ascii=False, indent=2) + "\\n"),
]
artifacts = []
for artifact_id, artifact_type, filename, mime_type, content in files:
    path = job_dir / filename
    path.write_text(content, encoding="utf-8")
    payload = path.read_bytes()
    artifacts.append({{
        "artifact_id": artifact_id,
        "type": artifact_type,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "storage_key": "projects/" + manifest["project_id"] + "/jobs/" + manifest["job_id"] + "/" + filename,
        "public": False,
    }})
worker_log = job_dir / "worker.log"
worker_log.write_text(
    "\\n".join([
        "job=" + manifest["job_id"],
        "stage=" + manifest["stage"],
        "artifacts=lyrics.txt,song_plan.json,safety_notes.json",
        "storage=server",
    ]) + "\\n",
    encoding="utf-8",
)
output = {{
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
    "preview": preview,
    "logs": [
        "remote worker wrote job_manifest.json",
        "remote worker wrote lyrics.txt",
        "remote worker wrote song_plan.json",
        "remote worker wrote safety_notes.json",
    ],
    "log": {{
        "storage_key": "projects/" + manifest["project_id"] + "/jobs/" + manifest["job_id"] + "/worker.log",
    }},
    "generated_at": datetime.now(timezone.utc).isoformat(),
}}
(job_dir / "output_manifest.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(output, ensure_ascii=False))
PY
"""
        script_result = subprocess.run(
            [*self._ssh_base_command(profile), "bash", "-s"],
            input=remote_script,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if script_result.returncode != 0:
            return RemotePilotRun(
                id=job_id,
                project_id=project_id,
                stage=stage,
                status="failed",
                adapter="ssh",
                remote_job_dir=remote_job_dir,
                job_manifest_path=job_manifest_path,
                output_manifest_path=output_manifest_path,
                output_files=[],
                artifacts=[],
                preview=None,
                message=script_result.stderr.strip() or "Remote pilot failed",
                logs=[line for line in [script_result.stdout.strip(), script_result.stderr.strip()] if line],
                created_at=now,
                updated_at=utc_now(),
            )

        output_result = subprocess.run(
            [*self._ssh_base_command(profile), f"cat {shlex.quote(output_manifest_path)}"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        output = json.loads(output_result.stdout) if output_result.returncode == 0 else {}
        return RemotePilotRun(
            id=job_id,
            project_id=project_id,
            stage=stage,
            status=output.get("status", "completed"),
            adapter="ssh",
            remote_job_dir=output.get("remote_job_dir", remote_job_dir),
            job_manifest_path=job_manifest_path,
            output_manifest_path=output_manifest_path,
            output_files=output.get("output_files", []),
            artifacts=[GenerationArtifact.model_validate(artifact) for artifact in output.get("artifacts", [])],
            preview=GenerationPreview.model_validate(output["preview"]) if output.get("preview") else None,
            message="Server generation completed.",
            logs=output.get("logs", [script_result.stdout.strip()]),
            created_at=now,
            updated_at=utc_now(),
        )

    def fetch_artifact(self, profile: ServerProfile, run: RemotePilotRun, artifact_id: str) -> tuple[GenerationArtifact, bytes]:
        artifact = next((item for item in run.artifacts if item.artifact_id == artifact_id), None)
        if artifact is None:
            raise FileNotFoundError(artifact_id)
        remote_path = f"{run.remote_job_dir.rstrip('/')}/{artifact.filename}"
        result = subprocess.run(
            [*self._ssh_base_command(profile), f"cat {shlex.quote(remote_path)}"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise FileNotFoundError(artifact_id)
        return artifact, result.stdout

    def fetch_log(self, profile: ServerProfile, run: RemotePilotRun) -> str:
        remote_path = f"{run.remote_job_dir.rstrip('/')}/worker.log"
        result = subprocess.run(
            [*self._ssh_base_command(profile), f"cat {shlex.quote(remote_path)}"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return "\n".join(run.logs)
        return result.stdout
