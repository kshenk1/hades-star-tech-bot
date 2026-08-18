#!/usr/bin/env bash
#
# Redeploy an updated version of the bot after setup.sh has already been run once.
# Run from the repo root on the EC2 box after a `git pull` (or after re-uploading
# updated files), e.g.:
#   sudo bash deploy/redeploy.sh
#
# This re-syncs code (without touching .env, the venv, or the sqlite db),
# reinstalls requirements in case they changed, and restarts the service.
set -euo pipefail

APP_DIR="/opt/hadesbot"
SERVICE_USER="hadesbot"
REPO_SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run this with sudo: sudo bash deploy/redeploy.sh" >&2
  exit 1
fi

echo "==> Syncing updated code to ${APP_DIR}"
rsync -a --delete \
  --exclude 'venv' \
  --exclude '.env' \
  --exclude '*.db' \
  --exclude '__pycache__' \
  --exclude '.git' \
  "${REPO_SOURCE_DIR}/" "${APP_DIR}/"

echo "==> Reinstalling requirements (in case they changed)"
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

echo "==> Fixing ownership"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

echo "==> Restarting service"
systemctl restart hadesbot
sleep 2
systemctl status hadesbot --no-pager -l | head -20

echo ""
echo "Done. Tail logs with: sudo journalctl -u hadesbot -f"
