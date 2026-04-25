# Ubuntu 24.04 Server Setup

This is the handoff for a fresh Ubuntu 24.04 machine reachable over Tailscale.

Target server seen from the Mac:

- Tailscale IP: `100.121.224.29`
- Tailscale name: `danielpc-1`
- SSH port: `22`
- App repo: `https://github.com/lorancdaniel/aikiddo.git`

The app starts with the mock pipeline only. Do not wire the real GPU worker yet.

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
sudo apt install -y git curl ca-certificates build-essential python3 python3-venv python3-pip
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

Frontend:

```bash
cd ~/aikiddo/app/web
npm install
npm run lint
npm run build
npm run test:e2e
```

## 5. Run Mock App

Terminal 1, backend:

```bash
cd ~/aikiddo/app/api
source .venv/bin/activate
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
- Use the mock server only.
- Do not wire real GPU yet.
- Do not rename technical stage_id values.

Stack:
- Backend: app/api, FastAPI, port 8000
- Frontend: app/web, Next.js, port 3010
- Current product modules: Series Bible, Episode Spec, Anti-Repetition v0, mock pipeline, artifact inventory, job history, approval history, next-action.
- Next product modules: Publish Package v2, then Manual Performance Ledger.

Do:
1. Inspect the repo and current git status.
2. Verify Ubuntu dependencies, Python venv, Node.js and npm.
3. Run backend tests: cd app/api && python3 -m pytest -q
4. Run frontend checks: cd app/web && npm run lint && npm run build && npm run test:e2e
5. Start backend on 0.0.0.0:8000 and frontend on 0.0.0.0:3010.
6. If asked to make services, create systemd units only after the app works manually.
7. Report exact commands, ports, and any blockers.
```
