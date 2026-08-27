#!/usr/bin/env bash
# One-time: sign in to Kiosk in Chromium; profile is reused headlessly by get_creds.py / cron.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.dbenv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi

"$PY" -m pip install -q -r "$ROOT/requirements-browser.txt"
"$PY" -m playwright install chromium

echo "A browser window will open. Sign in with your Frontiers account if asked."
"$PY" "$ROOT/get_creds.py" --browser-login
