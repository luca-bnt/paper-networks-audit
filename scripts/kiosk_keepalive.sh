#!/usr/bin/env bash
# Rotate the Kiosk SPA refresh token headlessly so daily refresh stays unattended.
# Recommended cron (every 6 hours):
#   15 */6 * * *  /Users/luca.bontempi/Documents/Code/paper-networks-audit/scripts/kiosk_keepalive.sh >> /tmp/kiosk-keepalive.log 2>&1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-/Users/luca.bontempi/Documents/Code/frontiers-mcp/.dbenv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi
echo "[keepalive] $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$PY" "$ROOT/get_creds.py" --keepalive

# Remint flags table SAS from the live account key (survives key rotations).
if [[ -x "$ROOT/scripts/refresh_flags_sas.sh" ]]; then
  "$ROOT/scripts/refresh_flags_sas.sh" || echo "[keepalive] flags SAS refresh failed" >&2
fi
