#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/lorancdaniel/aikiddo.git}"
APP_DIR="${APP_DIR:-$HOME/aikiddo}"
SERVER_IP="${SERVER_IP:-100.121.224.29}"
MAC_PUBLIC_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJlSRasQdCxb7ML6Cdijytf/3rV6UAUYls6yjlwRO9GK lorancdan@gmail.com"

echo "==> Preparing SSH authorized_keys"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
if ! grep -qxF "$MAC_PUBLIC_KEY" "$HOME/.ssh/authorized_keys"; then
  echo "$MAC_PUBLIC_KEY" >> "$HOME/.ssh/authorized_keys"
fi
if command -v sudo >/dev/null 2>&1; then
  sudo chown -R "$(id -un):$(id -gn)" "$HOME/.ssh"
fi

echo "==> Installing system dependencies"
sudo apt update
sudo apt install -y git curl ca-certificates build-essential python3 python3-venv python3-pip

if ! command -v node >/dev/null 2>&1; then
  echo "==> Installing Node.js LTS"
  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
  sudo apt install -y nodejs
else
  echo "==> Node.js already installed: $(node -v)"
fi

echo "==> Node: $(node -v)"
echo "==> npm: $(npm -v)"
echo "==> Python: $(python3 --version)"

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Cloning repo into $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
else
  echo "==> Repo already exists, pulling latest"
  git -C "$APP_DIR" pull --ff-only
fi

echo "==> Backend setup"
cd "$APP_DIR/app/api"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest -q

if [ ! -f .env.ops ]; then
  echo "==> Creating backend ops token"
  umask 077
  if command -v openssl >/dev/null 2>&1; then
    {
      printf 'export STUDIO_ADMIN_TOKEN=%s\n' "$(openssl rand -hex 32)"
      printf '# export OPENAI_API_KEY=your_real_key_here\n'
      printf 'export AIKIDDO_OPENAI_TEXT_MODEL=gpt-5\n'
      printf 'export AIKIDDO_OPENAI_TTS_MODEL=gpt-4o-mini-tts\n'
      printf 'export AIKIDDO_OPENAI_TTS_VOICE=coral\n'
    } > .env.ops
  else
    python3 - <<'PY' > .env.ops
import secrets
print(f"export STUDIO_ADMIN_TOKEN={secrets.token_hex(32)}")
print("# export OPENAI_API_KEY=your_real_key_here")
print("export AIKIDDO_OPENAI_TEXT_MODEL=gpt-5")
print("export AIKIDDO_OPENAI_TTS_MODEL=gpt-4o-mini-tts")
print("export AIKIDDO_OPENAI_TTS_VOICE=coral")
PY
  fi
else
  echo "==> Backend ops token already exists"
fi

echo "==> Frontend setup"
cd "$APP_DIR/app/web"
npm install
npm run lint
npm run build

echo "==> Setup complete"
cat <<EOF

Run backend:
  cd $APP_DIR/app/api
  source .venv/bin/activate
  source .env.ops
  python3 -m uvicorn studio_api.main:app --host 0.0.0.0 --port 8000

Run frontend in a second terminal:
  cd $APP_DIR/app/web
  NEXT_PUBLIC_API_URL=http://$SERVER_IP:8000 npm run dev -- --host 0.0.0.0 --port 3010

Open:
  http://$SERVER_IP:3010

SSH test from Mac:
  ssh $(whoami)@$SERVER_IP 'hostname && whoami'

EOF
