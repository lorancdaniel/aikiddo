import json
import shlex
import subprocess
from uuid import uuid4

from .models import Brief, RemotePilotRun, ServerConnection, ServerProfile, utc_now


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
        artifact_path = f"{remote_job_dir}/pilot-artifact.txt"
        job_manifest = {
            "schema_version": "job-contract-v1",
            "job_id": job_id,
            "project_id": project_id,
            "stage": stage,
            "adapter": self.adapter,
            "storage_policy": "server",
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
import pathlib
import socket
import sys
from datetime import datetime, timezone

job_dir = pathlib.Path(sys.argv[1])
manifest = json.loads((job_dir / "job_manifest.json").read_text(encoding="utf-8"))
artifact_path = job_dir / "pilot-artifact.txt"
artifact_path.write_text(
    "\\n".join([
        "project_id=" + manifest["project_id"],
        "stage=" + manifest["stage"],
        "title=" + manifest["brief"]["title"],
        "topic=" + manifest["brief"]["topic"],
        "host=" + socket.gethostname(),
    ]) + "\\n",
    encoding="utf-8",
)
output = {{
    "schema_version": "job-contract-v1",
    "job_id": manifest["job_id"],
    "project_id": manifest["project_id"],
    "stage": manifest["stage"],
    "status": "completed",
    "adapter": "ssh",
    "storage_policy": "server",
    "remote_job_dir": str(job_dir),
    "output_files": [str(artifact_path)],
    "logs": ["remote pilot wrote job_manifest.json", "remote pilot wrote pilot-artifact.txt"],
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
            output_files=output.get("output_files", [artifact_path]),
            message="Remote pilot completed on SSH worker.",
            logs=output.get("logs", [script_result.stdout.strip()]),
            created_at=now,
            updated_at=utc_now(),
        )
