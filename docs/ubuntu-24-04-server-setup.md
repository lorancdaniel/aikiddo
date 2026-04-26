# Ubuntu 24.04 Server Setup

This is the handoff for a fresh Ubuntu 24.04 machine reachable over Tailscale.

Target server seen from the Mac:

- Tailscale IP: `100.121.224.29`
- Tailscale name: `danielpc-1`
- SSH port: `22`
- App repo: `https://github.com/lorancdaniel/aikiddo.git`

The app now runs server-owned SSH generation by default. Without an SSH server profile, generation fails closed instead of creating local fallback artifacts. The old mock path is only available for explicit local development with `STUDIO_ALLOW_LOCAL_MOCK=1`; do not enable it on the Ubuntu production server.

SSH generation now uses the versioned, stage-aware worker script at `scripts/aikiddo_worker.py`. The FastAPI adapter sends that script and `job_manifest.json` to the server job directory, including upstream pipeline context for previous stages. The server then writes `output_manifest.json`, `worker.log`, and all artifacts under `<remote_root>/jobs/<job_id>/`.

## 1. Add Mac SSH Key To The Server

Run this on the Ubuntu server as the user that should accept SSH logins.

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
grep -qxF 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJlSRasQdCxb7ML6Cdijytf/3rV6UAUYls6yjlwRO9GK lorancdan@gmail.com' ~/.ssh/authorized_keys 2>/dev/null || echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJlSRasQdCxb7ML6Cdijytf/3rV6UAUYls6yjlwRO9GK lorancdan@gmail.com' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
whoami
hostname
```

Then from the Mac, test:

```bash
ssh <ubuntu-user>@100.121.224.29 'hostname && whoami'
```

Replace `<ubuntu-user>` with the value printed by `whoami` on the server.

## 2. Current SSH Fix For User `daniel`

Codex can currently reach the server over Tailscale, and SSH port `22` is open, but login is rejected with:

```text
Permission denied (publickey,password)
```

Run this on the Ubuntu server to explicitly authorize the Mac key for user `daniel`:

```bash
sudo mkdir -p /home/daniel/.ssh
sudo touch /home/daniel/.ssh/authorized_keys
grep -qxF 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJlSRasQdCxb7ML6Cdijytf/3rV6UAUYls6yjlwRO9GK lorancdan@gmail.com' /home/daniel/.ssh/authorized_keys || echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJlSRasQdCxb7ML6Cdijytf/3rV6UAUYls6yjlwRO9GK lorancdan@gmail.com' | sudo tee -a /home/daniel/.ssh/authorized_keys
sudo chown -R daniel:daniel /home/daniel/.ssh
sudo chmod 700 /home/daniel/.ssh
sudo chmod 600 /home/daniel/.ssh/authorized_keys
sudo systemctl status ssh --no-pager
```

Verify locally on Ubuntu:

```bash
whoami
grep 'lorancdan@gmail.com' /home/daniel/.ssh/authorized_keys
ls -la /home/daniel/.ssh
```

Then ask Codex to retry:

```bash
ssh daniel@100.121.224.29 'whoami && hostname && pwd'
```

## 3. One-Shot Bootstrap

On Ubuntu:

```bash
curl -fsSL https://raw.githubusercontent.com/lorancdaniel/aikiddo/main/scripts/bootstrap_ubuntu_24_04.sh -o bootstrap_ubuntu_24_04.sh
chmod +x bootstrap_ubuntu_24_04.sh
./bootstrap_ubuntu_24_04.sh
```

If the repo is private and the `curl` command cannot fetch the script, clone the repo first and run:

```bash
git clone https://github.com/lorancdaniel/aikiddo.git
cd aikiddo
chmod +x scripts/bootstrap_ubuntu_24_04.sh
./scripts/bootstrap_ubuntu_24_04.sh
```

## 4. Manual Commands If Needed

Install system dependencies:

```bash
sudo apt update
sudo apt install -y git curl ca-certificates build-essential ffmpeg python3 python3-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
```

Clone repo:

```bash
git clone https://github.com/lorancdaniel/aikiddo.git ~/aikiddo
cd ~/aikiddo
```

Backend:

```bash
cd ~/aikiddo/app/api
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest -q
```

Create the backend admin token used by SSH worker control endpoints:

```bash
cd ~/aikiddo/app/api
umask 077
{
  printf 'export STUDIO_ADMIN_TOKEN=%s\n' "$(openssl rand -hex 32)"
  printf '# export AIKIDDO_TEXT_ENDPOINT=http://127.0.0.1:8001/v1/chat/completions\n'
  printf '# export AIKIDDO_AUDIO_ENDPOINT=http://127.0.0.1:8002/v1/audio/speech\n'
  printf '# export AIKIDDO_IMAGE_ENDPOINT=http://127.0.0.1:8188/v1/images/generations\n'
  printf '# export AIKIDDO_VIDEO_ENDPOINT=http://127.0.0.1:8188/aikiddo/video\n'
  printf 'export AIKIDDO_TEXT_MODEL=Qwen/Qwen3.6-27B\n'
  printf 'export AIKIDDO_AUDIO_MODEL=YuE-s1-7B\n'
  printf 'export AIKIDDO_AUDIO_VOICE=local-child-safe-guide\n'
  printf 'export AIKIDDO_IMAGE_MODEL=FLUX.1-dev\n'
  printf 'export AIKIDDO_IMAGE_SIZE=1536x1024\n'
  printf 'export AIKIDDO_VIDEO_MODEL=Wan2.2-I2V-A14B\n'
} > .env.ops
```

The token is required for:

- `POST /api/jobs/dispatch-next`
- `POST /api/jobs/locks/heartbeat`
- `POST /api/jobs/locks/recover-stale`

If `STUDIO_ADMIN_TOKEN` is missing, these endpoints fail closed with `503`.

For production generation stages, the server must use local model endpoints only. The backend passes only the allowlisted local variables (`AIKIDDO_TEXT_ENDPOINT`, `AIKIDDO_TEXT_API_KEY`, `AIKIDDO_TEXT_MODEL`, `AIKIDDO_AUDIO_ENDPOINT`, `AIKIDDO_AUDIO_API_KEY`, `AIKIDDO_AUDIO_MODEL`, `AIKIDDO_AUDIO_VOICE`, `AIKIDDO_IMAGE_ENDPOINT`, `AIKIDDO_IMAGE_API_KEY`, `AIKIDDO_IMAGE_MODEL`, `AIKIDDO_IMAGE_SIZE`, `AIKIDDO_VIDEO_ENDPOINT`, `AIKIDDO_VIDEO_MODEL`, `AIKIDDO_MODEL_TIMEOUT_SEC`, `AIKIDDO_WORKER_MODE`) into the SSH worker command. Without `AIKIDDO_TEXT_ENDPOINT`, production text/planning generation fails closed and does not write a success manifest.

Recommended local model baseline for this machine:

- text/planning: `Qwen/Qwen3.6-27B` behind an OpenAI-compatible `/v1/chat/completions` endpoint;
- audio/music draft: `YuE-s1-7B` or the newest local lyrics-to-song model exposed through `AIKIDDO_AUDIO_ENDPOINT`;
- image/keyframes: `FLUX.1-dev` or newer local image model exposed through `AIKIDDO_IMAGE_ENDPOINT`;
- video: `Wan2.2-I2V-A14B` or newer local image-to-video model, preferably through ComfyUI or a thin local HTTP wrapper exposed through `AIKIDDO_VIDEO_ENDPOINT`.

The bootstrap script installs `ffmpeg`. The current `render.full_episode` stage writes server-owned `full_episode.json`, `render_plan.json`, `ffmpeg_commands.txt`, per-scene MP4 files, and `renders/<episode_slug>/full-episode.mp4` from the approved keyframe PNG files. The `render.reels` stage then crops vertical 9:16 reel MP4 files from that full episode using the planned scene offsets.

The `publish.prepare_package` stage does not upload anything. It copies the final episode MP4 and reel MP4 files into `publish/<episode_slug>/`, writes `publish_assets_manifest.json`, and creates `publish/<episode_slug>.zip` for manual operator review.

Do not set `STUDIO_ALLOW_LOCAL_MOCK` on the Ubuntu server. The default production behavior requires a saved SSH profile before any generation job can start. This prevents accidental local/mock artifacts from being treated as server-owned generation output.

Do not set `AIKIDDO_WORKER_MODE=deterministic` on the Ubuntu server unless you are deliberately doing a local development smoke test. That mode writes deterministic scaffolding instead of real provider output.

Before enabling local model endpoints, you can verify the remote worker contract without generation costs:

```bash
python3 scripts/aikiddo_worker_smoke.py --root /tmp/aikiddo-worker-smoke
```

Expected output includes `aikiddo_worker_smoke=ok` and `final_stage=publish.prepare_package`.

Do not use the old `/api/projects/{project_id}/remote-pilot` path for production work. It is retired and returns `410 Gone`; the app should create generation work through `POST /api/projects/{project_id}/jobs/{stage}` and read progress through job detail, events, logs, and artifacts.

The current server worker is:

- source-controlled at `scripts/aikiddo_worker.py`;
- copied into each remote job directory as `aikiddo_worker.py`;
- invoked as `python3 "$job_dir/aikiddo_worker.py" "$job_dir"`;
- responsible for producing stage-specific artifacts, optional `input_context.json`, `output_manifest.json`, and `worker.log`.

Frontend:

```bash
cd ~/aikiddo/app/web
npm install
npm run lint
npm run build
npm run test:e2e
```

## 5. Run Server-Owned App

Terminal 1, backend:

```bash
cd ~/aikiddo/app/api
source .venv/bin/activate
source .env.ops
python3 -m uvicorn studio_api.main:app --host 0.0.0.0 --port 8000
```

Terminal 2, frontend:

```bash
cd ~/aikiddo/app/web
NEXT_PUBLIC_API_URL=http://100.121.224.29:8000 npm run dev -- --host 0.0.0.0 --port 3010
```

Open from another machine on the Tailnet:

```text
http://100.121.224.29:3010
```

## 6. Codex Handoff Prompt

After installing Codex on Ubuntu, run `codex` in `~/aikiddo` and paste:

```text
You are Codex on a fresh Ubuntu 24.04 server for AI Kids Music Studio.

Goal:
- Configure and verify the existing Next.js + FastAPI app from this repository.
- Use the SSH/server-owned generation path.
- Keep mock generation disabled on Ubuntu. It is only available for local development when `STUDIO_ALLOW_LOCAL_MOCK=1` is set deliberately.
- Do not revive the retired /api/projects/{project_id}/remote-pilot flow.
- Do not rename technical stage_id values.

Stack:
- Backend: app/api, FastAPI, port 8000
- Frontend: app/web, Next.js, port 3010
- Current product modules: Series Bible, Episode Spec, Anti-Repetition v0, SSH generation queue, server artifact inventory, job history, approval history, next-action.
- Current worker contract: scripts/aikiddo_worker.py receives job_manifest.json with upstream pipeline context and writes stage-specific output_manifest.json plus server artifacts.
- Worker smoke test: python3 scripts/aikiddo_worker_smoke.py --root /tmp/aikiddo-worker-smoke validates deterministic end-to-end artifact threading before enabling local model endpoints.
- Current local provider path: lyrics.generate, characters.import_or_approve, storyboard.generate, render.reels, quality.compliance_report, and publish.prepare_package use local text/planning JSON through `AIKIDDO_TEXT_ENDPOINT`; keyframes.generate writes PNG keyframes through `AIKIDDO_IMAGE_ENDPOINT`; video.scenes.generate plans scene motion through `AIKIDDO_TEXT_ENDPOINT`, renders server-owned scene MP4 files through `AIKIDDO_VIDEO_ENDPOINT`, and records those scene files in video_scenes.json; render.full_episode writes full_episode.json, render_plan.json, ffmpeg_commands.txt, and assembles the full-episode MP4 from generated scene MP4s when present, with keyframe-to-FFmpeg scene rendering kept as a fallback path; render.reels writes reels.json plus vertical reel MP4 artifacts from the full episode; publish.prepare_package copies the episode/reel MP4s into a server-side publish package with publish_assets_manifest.json and a ZIP archive; audio.generate_or_import uses `AIKIDDO_AUDIO_ENDPOINT`; deterministic worker mode is dev-only.
- Runtime health: `GET /api/server/local-models` reports local-only adapter readiness for text, audio, image, and video. It returns model names and env variable names only; endpoint URL values and API keys are intentionally never exposed in the API or UI.
- Next product modules: add provider-specific video endpoint adapters/probes, then Publish Package v2 and Manual Performance Ledger.

Do:
1. Inspect the repo and current git status.
2. Verify Ubuntu dependencies, Python venv, Node.js and npm.
3. Run worker smoke test: python3 scripts/aikiddo_worker_smoke.py --root /tmp/aikiddo-worker-smoke
4. Run backend tests: cd app/api && python3 -m pytest -q
5. Run frontend checks: cd app/web && npm run lint && npm run build && npm run test:e2e
6. Create app/api/.env.ops with export STUDIO_ADMIN_TOKEN=<random-hex-token>, export AIKIDDO_TEXT_ENDPOINT=http://127.0.0.1:8001/v1/chat/completions, export AIKIDDO_TEXT_MODEL=Qwen/Qwen3.6-27B, export AIKIDDO_AUDIO_ENDPOINT=<local-audio-endpoint>, export AIKIDDO_AUDIO_MODEL=YuE-s1-7B, export AIKIDDO_IMAGE_ENDPOINT=<local-image-endpoint>, export AIKIDDO_IMAGE_MODEL=FLUX.1-dev, export AIKIDDO_VIDEO_ENDPOINT=<local-video-endpoint>, and export AIKIDDO_VIDEO_MODEL=Wan2.2-I2V-A14B; do not add STUDIO_ALLOW_LOCAL_MOCK or AIKIDDO_WORKER_MODE=deterministic.
7. Start backend on 0.0.0.0:8000 with source .env.ops and frontend on 0.0.0.0:3010.
8. If asked to make services, create systemd units only after the app works manually.
9. Report exact commands, ports, and any blockers.
```
