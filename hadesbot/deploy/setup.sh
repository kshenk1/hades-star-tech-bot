#!/usr/bin/env bash
#
# One-time provisioning script for Amazon Linux 2023 (t3.micro or bigger).
# Run this ONCE as ec2-user (with sudo) after cloning/copying the repo to the box.
#
# Usage (from the repo root, e.g. ~/hades-star-tech-bot/hadesbot):
#   sudo bash deploy/setup.sh
#
# What it does:
#   1. Installs Python + git
#   2. Creates a dedicated, unprivileged "hadesbot" system user
#   3. Copies the project to /opt/hadesbot (owned by that user)
#   4. Creates a venv and installs requirements
#   5. Installs the systemd unit and enables (but does not start) the service
#
# After running this, you still need to:
#   - Put your real token in /opt/hadesbot/.env
#   - sudo systemctl start hadesbot
set -euo pipefail

APP_DIR="/opt/hadesbot"
SERVICE_USER="hadesbot"
REPO_SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"  # the hadesbot/ dir this script lives in

if [[ $EUID -ne 0 ]]; then
  echo "Run this with sudo: sudo bash deploy/setup.sh" >&2
  exit 1
fi

echo "==> Installing Python 3.11, git, and rsync"
dnf install -y python3.11 python3.11-pip git rsync

echo "==> Creating system user '${SERVICE_USER}' (no shell login, no home dir needed)"
if ! id "${SERVICE_USER}" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

echo "==> Copying project to ${APP_DIR}"
mkdir -p "${APP_DIR}"
# rsync keeps this idempotent for re-runs (e.g. after a git pull) without clobbering the venv or .env
rsync -a --delete \
  --exclude 'venv' \
  --exclude '.env' \
  --exclude '*.db' \
  --exclude '__pycache__' \
  --exclude '.git' \
  "${REPO_SOURCE_DIR}/" "${APP_DIR}/"

echo "==> Creating virtualenv and installing requirements"
python3.11 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip -q
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo "==> Creating .env from template — YOU MUST EDIT THIS with your real token"
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

echo "==> Setting ownership to ${SERVICE_USER}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"   # token file: owner-read/write only

echo "==> Installing systemd unit"
cp "${APP_DIR}/deploy/hadesbot.service" /etc/systemd/system/hadesbot.service
systemctl daemon-reload
systemctl enable hadesbot

echo ""
echo "Setup complete. Next steps:"
echo "  1. sudo nano ${APP_DIR}/.env         # paste your real DISCORD_TOKEN"
echo "  2. sudo systemctl start hadesbot"
echo "  3. sudo journalctl -u hadesbot -f    # watch logs / confirm it connected"
