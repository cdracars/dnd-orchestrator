#!/usr/bin/env bash
# One-command launcher: venv + deps + server on your LAN.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
if [ -f .env ]; then set -a; source .env; set +a; fi
python server.py
