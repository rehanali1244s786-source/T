#!/usr/bin/env bash
# One-command VPS setup + run:  bash vps/run.sh
set -e
cd "$(dirname "$0")/.."
command -v ffmpeg >/dev/null || echo "WARNING: ffmpeg not installed (sudo apt install -y ffmpeg)"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install -q -U pip
./venv/bin/pip install -q -U -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Edit .env (BOT_TOKEN, ADMIN_IDS) then run again."; exit 1; }
exec ./venv/bin/python main.py
