#!/usr/bin/env bash
# Mint a fresh Azure Table SAS from the *current* storage account key and deploy
# flags-config.js. Survives account-key rotations: Azure AD lists the live key,
# then HMAC-signs a new table SAS.
#
# The static app cannot mint a SAS itself (no account key in the browser). On
# HTTP 403 it reloads this file and retries; this script is what actually
# refreshes the token.
#
#   ./scripts/refresh_flags_sas.sh
#
# Recommended cron (hourly is cheap; also runs from kiosk_keepalive / snapshot deploy):
#   20 * * * *  /Users/YOU/Code/paper-networks-audit/scripts/refresh_flags_sas.sh >> /tmp/flags-sas-refresh.log 2>&1
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

AZ_ACCOUNT="staticsitesops10798"
AZ_CONTAINER='$web'
AZ_PREFIX="prototypes/network-analysis"
AZ_SUBSCRIPTION="f1df7182-0b90-4aa4-9f76-865b6aea7501"
TABLE="pmflags"
CFG="$ROOT/audit-network/flags-config.js"

az account set --subscription "$AZ_SUBSCRIPTION"

probe_sas() {
  local sas="$1"
  curl -sS -o /dev/null -w '%{http_code}' \
    "https://${AZ_ACCOUNT}.table.core.windows.net/${TABLE}()?%24top=1&${sas}" \
    -H 'Accept: application/json;odata=nometadata'
}

EXISTING_SAS=""
if [[ -f "$CFG" ]]; then
  EXISTING_SAS="$(python3 -c 'import re,sys; t=open(sys.argv[1]).read(); m=re.search(r"sas:\s*\"([^\"]+)\"",t); print(m.group(1) if m else "")' "$CFG" 2>/dev/null || true)"
fi

KEY="$(az storage account keys list --account-name "$AZ_ACCOUNT" --query '[0].value' -o tsv 2>/dev/null || true)"
if [[ -z "$KEY" ]]; then
  if [[ -n "$EXISTING_SAS" ]]; then
    PROBE="$(probe_sas "$EXISTING_SAS")"
    if [[ "$PROBE" == "200" ]]; then
      echo "[flags-sas] listKeys denied; existing SAS still valid (HTTP ${PROBE}) — not reminting"
      exit 0
    fi
  fi
  echo "[flags-sas] could not read storage account key (az login / RBAC?) and no working SAS" >&2
  exit 1
fi

# macOS date -v; GNU date -d
EXPIRY="$(date -u -v+1y +%Y-%m-%dT%H:%MZ 2>/dev/null || date -u -d '+1 year' +%Y-%m-%dT%H:%MZ)"
SAS="$(az storage table generate-sas --name "$TABLE" --permissions raud --expiry "$EXPIRY" --https-only \
  --account-name "$AZ_ACCOUNT" --account-key "$KEY" -o tsv)"
if [[ -z "$SAS" ]]; then
  echo "[flags-sas] generate-sas returned empty" >&2
  exit 1
fi

PROBE="$(curl -sS -o /dev/null -w '%{http_code}' \
  "https://${AZ_ACCOUNT}.table.core.windows.net/${TABLE}()?%24top=1&${SAS}" \
  -H 'Accept: application/json;odata=nometadata')"
if [[ "$PROBE" != "200" ]]; then
  echo "[flags-sas] new SAS probe failed HTTP ${PROBE} — not deploying" >&2
  exit 1
fi

cat > "$CFG" <<EOF
window.FLAGS_CONFIG = {
  account: "${AZ_ACCOUNT}",
  table: "${TABLE}",
  sas: "${SAS}"
};
EOF

OWNER="$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null || az account show --query user.name -o tsv || whoami)"
az storage blob upload \
  --account-name "$AZ_ACCOUNT" \
  --container-name "$AZ_CONTAINER" \
  --name "$AZ_PREFIX/flags-config.js" \
  --file "$CFG" \
  --auth-mode login \
  --overwrite true \
  --content-type "application/javascript" \
  --metadata "owner=$OWNER" >/dev/null

echo "[flags-sas] deployed flags-config.js (expiry ${EXPIRY}, probe HTTP ${PROBE})"
