import hashlib
import json
from json import JSONDecodeError
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from .models import Brief, GenerationArtifact, GenerationPreview, RemotePilotRun, ServerConnection, ServerProfile, utc_now


class SshGenerationServer:
    adapter = "ssh"
    worker_env_keys = (
        "AIKIDDO_TEXT_ENDPOINT",
        "AIKIDDO_TEXT_API_KEY",
        "AIKIDDO_TEXT_MODEL",
        "AIKIDDO_AUDIO_ENDPOINT",
        "AIKIDDO_AUDIO_API_KEY",
        "AIKIDDO_AUDIO_MODEL",
        "AIKIDDO_AUDIO_VOICE",
        "AIKIDDO_IMAGE_ENDPOINT",
        "AIKIDDO_IMAGE_API_KEY",
        "AIKIDDO_IMAGE_MODEL",
        "AIKIDDO_IMAGE_SIZE",
        "AIKIDDO_VIDEO_ENDPOINT",
        "AIKIDDO_VIDEO_MODEL",
        "AIKIDDO_MODEL_TIMEOUT_SEC",
        "AIKIDDO_WORKER_MODE",
    )

    def _worker_script_source(self) -> str:
        repo_root = Path(__file__).resolve().parents[3]
        return (repo_root / "scripts" / "aikiddo_worker.py").read_text(encoding="utf-8")

    def _worker_env_exports(self) -> str:
        exports = []
        for key in self.worker_env_keys:
            value = os.getenv(key)
            if value:
                exports.append(f"export {key}={shlex.quote(value)}")
        return "\n".join(exports)

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

    def _failed_remote_run(
        self,
        *,
        job_id: str,
        project_id: str,
        stage: str,
        remote_job_dir: str,
        job_manifest_path: str,
        output_manifest_path: str,
        created_at: str,
        message: str,
        logs: list[str] | None = None,
    ) -> RemotePilotRun:
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
            message=message,
            logs=logs or [message],
            created_at=created_at,
            updated_at=utc_now(),
        )

    def _validate_output_manifest(
        self,
        *,
        output: Any,
        job_id: str,
        project_id: str,
        stage: str,
    ) -> tuple[list[str], list[GenerationArtifact], GenerationPreview | None, list[str], str]:
        if not isinstance(output, dict):
            raise ValueError("Output manifest must be a JSON object.")
        expected_values = {
            "schema_version": "output.v1",
            "job_id": job_id,
            "project_id": project_id,
            "stage": stage,
            "adapter": self.adapter,
        }
        for field, expected in expected_values.items():
            if output.get(field) != expected:
                raise ValueError(f"Output manifest field {field} does not match this job.")
        if output.get("status") not in {"completed", "failed"}:
            raise ValueError("Output manifest status must be completed or failed.")
        if not isinstance(output.get("output_files"), list):
            raise ValueError("Output manifest output_files must be a list.")
        if not isinstance(output.get("artifacts"), list):
            raise ValueError("Output manifest artifacts must be a list.")

        output_files = [str(path) for path in output["output_files"]]
        artifacts = [GenerationArtifact.model_validate(artifact) for artifact in output["artifacts"]]
        preview = GenerationPreview.model_validate(output["preview"]) if output.get("preview") else None
        logs = [str(line) for line in output.get("logs", []) if str(line).strip()]
        message = str(output.get("message") or "")
        return output_files, artifacts, preview, logs, message

    def run_remote_job(
        self,
        project_id: str,
        brief: Brief,
        stage: str,
        profile: ServerProfile,
        job_id: str | None = None,
        pipeline_context: list[dict[str, Any]] | None = None,
    ) -> RemotePilotRun:
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
            "pipeline_context": pipeline_context or [],
            "brief": brief.model_dump(mode="json"),
            "created_at": now,
        }
        manifest_json = json.dumps(job_manifest, ensure_ascii=False, indent=2)
        worker_source = self._worker_script_source()
        worker_env_exports = self._worker_env_exports()
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
{worker_env_exports}
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
            return self._failed_remote_run(
                job_id=job_id,
                project_id=project_id,
                stage=stage,
                remote_job_dir=remote_job_dir,
                job_manifest_path=job_manifest_path,
                output_manifest_path=output_manifest_path,
                message=script_result.stderr.strip() or "Server worker failed",
                logs=[line for line in [script_result.stdout.strip(), script_result.stderr.strip()] if line],
                created_at=now,
            )

        output_result = subprocess.run(
            [*self._ssh_base_command(profile), f"cat {shlex.quote(output_manifest_path)}"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if output_result.returncode != 0:
            message = output_result.stderr.strip() or output_result.stdout.strip() or "Output manifest could not be read."
            return self._failed_remote_run(
                job_id=job_id,
                project_id=project_id,
                stage=stage,
                remote_job_dir=remote_job_dir,
                job_manifest_path=job_manifest_path,
                output_manifest_path=output_manifest_path,
                message="Output manifest could not be read.",
                logs=[line for line in [script_result.stdout.strip(), message] if line],
                created_at=now,
            )
        try:
            output = json.loads(output_result.stdout)
        except JSONDecodeError as exc:
            return self._failed_remote_run(
                job_id=job_id,
                project_id=project_id,
                stage=stage,
                remote_job_dir=remote_job_dir,
                job_manifest_path=job_manifest_path,
                output_manifest_path=output_manifest_path,
                message="Output manifest is not valid JSON.",
                logs=[line for line in [script_result.stdout.strip(), str(exc)] if line],
                created_at=now,
            )
        try:
            output_files, artifacts, preview, logs, worker_message = self._validate_output_manifest(
                output=output,
                job_id=job_id,
                project_id=project_id,
                stage=stage,
            )
        except (ValueError, TypeError, ValidationError) as exc:
            return self._failed_remote_run(
                job_id=job_id,
                project_id=project_id,
                stage=stage,
                remote_job_dir=remote_job_dir,
                job_manifest_path=job_manifest_path,
                output_manifest_path=output_manifest_path,
                message="Output manifest failed contract validation.",
                logs=[line for line in [script_result.stdout.strip(), str(exc)] if line],
                created_at=now,
            )

        status = output["status"]
        return RemotePilotRun(
            id=job_id,
            project_id=project_id,
            stage=stage,
            status=status,
            adapter="ssh",
            remote_job_dir=output.get("remote_job_dir", remote_job_dir),
            job_manifest_path=job_manifest_path,
            output_manifest_path=output_manifest_path,
            output_files=output_files,
            artifacts=artifacts,
            preview=preview,
            message=worker_message or ("Server worker reported failure." if status == "failed" else "Server generation completed."),
            logs=logs or [script_result.stdout.strip()],
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

    def fetch_artifact_range(
        self,
        profile: ServerProfile,
        run: RemotePilotRun,
        artifact: GenerationArtifact,
        *,
        start: int,
        length: int,
    ) -> bytes:
        if start < 0 or length < 1:
            raise ValueError(artifact.artifact_id)
        remote_path = f"{run.remote_job_dir.rstrip('/')}/{artifact.filename}"
        result = subprocess.run(
            [
                *self._ssh_base_command(profile),
                f"dd if={shlex.quote(remote_path)} bs=1M skip={start} count={length} iflag=skip_bytes,count_bytes status=none",
            ],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise FileNotFoundError(artifact.artifact_id)
        if len(result.stdout) != length:
            raise ValueError(artifact.artifact_id)
        return result.stdout

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
