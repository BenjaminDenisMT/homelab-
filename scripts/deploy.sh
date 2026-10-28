#!/usr/bin/env bash
# deploy.sh – sync the homelab Python project to the Raspberry Pi
# Usage:  ./scripts/deploy.sh [pi-host]
# Default host: ben@192.168.1.23

set -euo pipefail

PI_HOST="${1:-ben@192.168.1.23}"
REMOTE_DIR="/home/ben/homelab"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "▶ Deploying to ${PI_HOST}:${REMOTE_DIR} …"

# ── 1. Sync project files (exclude venv, __pycache__, .git) ──────────────────
rsync -avz --delete \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='venv/' \
  --exclude='.venv/' \
  --exclude='*.egg-info' \
  "${LOCAL_DIR}/" "${PI_HOST}:${REMOTE_DIR}/"

# ── 2. Install / upgrade the package on the Pi ───────────────────────────────
ssh "${PI_HOST}" bash <<'REMOTE'
set -euo pipefail
cd /home/ben/homelab

# Create venv if it doesn't exist
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "✓ Created virtualenv"
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -e ".[dev]"
echo "✓ homelab package installed"

# Symlink rtlamr config
if [ ! -f /home/ben/rtlamr/config.yml ] && [ -f config/rtlamr.yml ]; then
    mkdir -p /home/ben/rtlamr
    ln -sf /home/ben/homelab/config/rtlamr.yml /home/ben/rtlamr/config.yml
    echo "✓ Symlinked config/rtlamr.yml → /home/ben/rtlamr/config.yml"
fi
REMOTE

echo "▶ Done!  Run:  ssh ${PI_HOST} 'cd homelab && source .venv/bin/activate && homelab status'"
