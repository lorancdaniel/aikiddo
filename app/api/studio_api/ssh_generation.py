import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from uuid import uuid4

from .models import Brief, GenerationArtifact, GenerationPreview, RemotePilotRun, ServerConnection, ServerProfile, utc_now


class SshGenerationServer:
    adapter = "ssh"

    def _worker_script_source(self) -> str:
        repo_root = Path(__file__).resolve().parents[3]
        return (repo_root / "scripts" / "aikiddo_worker.py").read_text(encoding="utf-8")

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

    def run_remote_job(self, project_id: str, brief: Brief, stage: str, profile: ServerProfile, job_id: str | None = None) -> RemotePilotRun:
        now = utc_now()
        job_id = job_id or f"remote_{uuid4().hex[:12]}"
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
        worker_source = self._worker_script_source()
        remote_script = f"""set -euo pipefail
job_dir={shlex.quote(remote_job_dir)}
python3 - "$job_dir" <<'PY'
import json
import pathlib
import sys

job_dir = pathlib.Path(sys.argv[1])
job_dir.mkdir(parents=True, exist_ok=True)
(job_dir / "job_manifest.json").write_text({json.dumps(manifest_json)}, encoding="utf-8")
(job_dir / "aikiddo_worker.py").write_text({json.dumps(worker_source)}, encoding="utf-8")
PY
python3 "$job_dir/aikiddo_worker.py" "$job_dir"
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
                message=script_result.stderr.strip() or "Server worker failed",
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

    def run_remote_pilot(self, project_id: str, brief: Brief, stage: str, profile: ServerProfile, job_id: str | None = None) -> RemotePilotRun:
        return self.run_remote_job(project_id=project_id, brief=brief, stage=stage, profile=profile, job_id=job_id)

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
        digest = hashlib.sha256(result.stdout).hexdigest()
        if digest != artifact.sha256:
            raise ValueError(artifact_id)
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
