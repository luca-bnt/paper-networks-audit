#!/usr/bin/env bash
# Incremental snapshot refresh + deploy to temporary-static-webapp.
#
# Prerequisites (interactive setup once):
#   - Python venv with requirements.txt (python3 -m venv .dbenv && .dbenv/bin/pip install -r requirements.txt google-cloud-bigquery)
#   - az login (luca.bontempi@frontiersin.net) with access to staticsitesops10798
#   - gcloud auth application-default login (BigQuery article context)
#   - Either AUDIT_DB_CS in .env, or KIOSK_BEARER_TOKEN in .env + get_creds.py (git-ignored copy)
#
# Local cron example (Mon 06:00):
#   crontab -e
#   0 6 * * 1  /Users/you/Code/network-analysis/scripts/refresh_and_deploy.sh >> /tmp/network-analysis-refresh.log 2>&1
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.dbenv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi

# Optional secrets file (never commit)
if [[ -f "$ROOT/.env" ]]; then set -a; source "$ROOT/.env"; set +a; fi

AZ_ACCOUNT="staticsitesops10798"
AZ_CONTAINER='$web'
AZ_PREFIX="prototypes/network-analysis"
AZ_SUBSCRIPTION="f1df7182-0b90-4aa4-9f76-865b6aea7501"

mkdir -p audit-pipeline

# Optional: restore incremental cache from blob (same path as GitHub Actions)
if [[ "${SYNC_CACHE:-1}" == "1" ]]; then
  az account set --subscription "$AZ_SUBSCRIPTION" 2>/dev/null || true
  if az storage blob download \
    --account-name "$AZ_ACCOUNT" \
    --container-name "$AZ_CONTAINER" \
    --name "$AZ_PREFIX/pipeline/raw_snapshot.pkl" \
    --file audit-pipeline/raw_snapshot.pkl \
    --auth-mode login 2>/dev/null; then
    echo "[cache] restored raw_snapshot.pkl from blob"
  fi
fi

# Kiosk temp SQL passwords expire ~24h — fetch fresh if bearer token is configured
if [[ -z "${AUDIT_DB_CS:-}" && -n "${KIOSK_BEARER_TOKEN:-}" && -f "$ROOT/get_creds.py" ]]; then
  export AUDIT_DB_CS="$("$PY" "$ROOT/get_creds.py" 2>/dev/null | awk -F': ' '/^Connection string:/{print $2}')"
fi

if [[ -z "${AUDIT_DB_CS:-}" ]]; then
  echo "Set AUDIT_DB_CS in .env or provide KIOSK_BEARER_TOKEN + get_creds.py" >&2
  exit 1
fi

echo "[refresh] incremental pull ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
"$PY" -u audit_snapshot.py --incremental --refresh-days 14 --days 90

echo "[deploy] uploading snapshot"
az account set --subscription "$AZ_SUBSCRIPTION"
OWNER="$(az account show --query user.name -o tsv)"
az storage blob upload \
  --account-name "$AZ_ACCOUNT" \
  --container-name "$AZ_CONTAINER" \
  --name "$AZ_PREFIX/data/snapshot.json.gz" \
  --file audit-network/data/snapshot.json.gz \
  --auth-mode login \
  --overwrite true \
  --content-type "application/gzip" \
  --metadata "owner=$OWNER"

if [[ "${SYNC_CACHE:-1}" == "1" && -f audit-pipeline/raw_snapshot.pkl ]]; then
  az storage blob upload \
    --account-name "$AZ_ACCOUNT" \
    --container-name "$AZ_CONTAINER" \
    --name "$AZ_PREFIX/pipeline/raw_snapshot.pkl" \
    --file audit-pipeline/raw_snapshot.pkl \
    --auth-mode login \
    --overwrite true \
    --content-type application/octet-stream
  echo "[cache] uploaded raw_snapshot.pkl to blob"
fi

echo "[done] https://network-analysis.temporary-static-webapp.frontiersin.net/"
