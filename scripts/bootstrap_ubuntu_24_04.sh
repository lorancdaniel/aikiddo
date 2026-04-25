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
  python3 -m uvicorn studio_api.main:app --host 0.0.0.0 --port 8000

Run frontend in a second terminal:
  cd $APP_DIR/app/web
  NEXT_PUBLIC_API_URL=http://$SERVER_IP:8000 npm run dev -- --host 0.0.0.0 --port 3010

Open:
  http://$SERVER_IP:3010

SSH test from Mac:
  ssh $(whoami)@$SERVER_IP 'hostname && whoami'

EOF
