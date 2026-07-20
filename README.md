# Paper Networks Audit

Independent local repository for the **Paper Networks Audit** prototype, demo video,
snapshot pipeline, and production planning docs.

**Live prototype:** https://network-analysis.temporary-static-webapp.frontiersin.net/  
**GitHub:** https://github.com/luca-bnt/network-analysis  
**Local path:** `/Users/luca.bontempi/Documents/Code/paper-networks-audit`

## Repository layout

```
audit-network/          # static web app (deploy this folder)
audit-network-demo/     # HyperFrames product demo video
audit-pipeline/         # local pipeline cache (git-ignored dumps)
docs/                   # PRD and production planning (start here)
audit_snapshot.py       # service-aira → snapshot builder
*.py                    # pipeline helpers
```

Product docs for the production implementation live in [`docs/`](./docs/) — begin with [`docs/PRD.md`](./docs/PRD.md).

## What it does

Reviewers explore how papers are linked through shared, potentially suspicious
attributes, and drill down to validate them:

- **Author name ↔ email similarity** and **email pattern** classification
- **Same email** used by different submitting authors
- **Same IP address** used by different submitting authors
- **Same Word-doc properties** (author / last edited by / company) across manuscripts
- **Same device fingerprint, browser language and timezone** across submissions
- **AIRA papermill risk score** shown as reviewer context (not used for clustering)

### Visualisation model

- **Overview** — clusters (shared-value *hubs*) linked when they share papers.
- **Drill-down** — click a cluster to open a hub-and-spoke of its papers plus the
  neighbouring hubs that sub-cluster them; keep clicking to go deeper.
- **Click-to-highlight** a node to isolate its connections (avoids clique noise).
- **Compare** — a tabular modal of the papers in view, with shared values highlighted.

## Layout (detail)

```
docs/                   # PRD and production planning
audit-network/          # the static app (deploy this folder)
  index.html            #   single-file vanilla JS + Canvas UI
  data/snapshot.json.gz #   dictionary-encoded, columnar, gzipped snapshot
audit-network-demo/     # HyperFrames demo (narration.md = TTS script)
audit_snapshot.py       # pipeline: fetch from service-aira -> build snapshot
device_profile_id.py    # device fingerprint hashing (pipeline dep)
papermill_scoring.py    # name/email similarity + scoring helpers (pipeline dep)
requirements.txt
```

## Frontend

No build step. Serve `audit-network/` over HTTP (the gzipped snapshot needs
`DecompressionStream`, which does not work over `file://`):

```bash
cd audit-network && python3 -m http.server 8777
# open http://localhost:8777/
```

## Rebuilding the snapshot

Requires read access to the `service-aira` Azure SQL managed instance.

```bash
python3 -m venv .dbenv && .dbenv/bin/pip install -r requirements.txt

# first run / periodic full rebuild (pulls the whole 90-day window)
AUDIT_DB_CS='Server=...;Database=service-aira;User Id=...;Password=...' \
  .dbenv/bin/python audit_snapshot.py --days 90

# weekly refresh (cheap) — reuse cache, pull only the recent slice, drop aged-out
AUDIT_DB_CS='...' .dbenv/bin/python audit_snapshot.py --incremental --refresh-days 14

# re-encode from the cached raw pull only (no DB)
.dbenv/bin/python audit_snapshot.py --from-raw --cap 50
```

The raw DB pull is cached to `audit-pipeline/raw_snapshot.pkl` (git-ignored — large).

### Trailing-window refresh

The 90-day window slides forward. On a weekly cadence only ~1 week of articles
is new, but enrichment (fingerprints / indicators / author metadata) can land a
few days *after* an article's `Created` date. So `--incremental`:

1. Drops cached rows older than `--days` (aged out of the window).
2. Re-pulls only the last `--refresh-days` (default 14 = ~7d new + ~7d buffer for
   late enrichment) and splices them over the cached rows.
3. Reuses the untouched cached remainder.

Net effect: each weekly run queries ~15% of the data instead of 100%. Run a full
`--days 90` rebuild periodically (e.g. monthly) as a safety net.

Rows that age out of the window are appended to a **local-only archive**
(`--archive`, default `audit-pipeline/archive_snapshot.pkl`, git-ignored),
deduplicated by article id, so you can retrieve older data later. Use
`--no-archive` to skip it.

## Manufactured-article flags (papermill)

Reviewers can flag/unflag articles as manufactured. Because the app is static
(served from Azure blob storage), flags are stored in **Azure Table Storage** on
the same account and written directly from the browser via a SAS — no backend
compute required.

- **Storage:** table `pmflags`:
  - Active flags: `PartitionKey="flag"`, `RowKey=<articleId>`, `flaggedBy`, `flaggedUtc`, `comment`
  - Removals (for DB sync): `PartitionKey="unflag"`, same `RowKey`, plus `removedBy`, `removedUtc`, and copies of the flag metadata
- **CSV export:** **↓ CSV** downloads all rows from both partitions (paginated, all time — not limited to the 90-day snapshot). Columns: `articleId`, `status` (`active`|`removed`), `comment`, `flaggedAt`, `removedAt`, `flaggedBy`, `removedBy`, `inSnapshot`
- **Config:** the app reads `flags-config.js` (git-ignored) which sets
  `window.FLAGS_CONFIG = { account, table, sas }`. If absent, the flag UI is
  hidden and any baked flags show read-only. Regenerate the SAS periodically:

  ```bash
  az storage table generate-sas --name pmflags --permissions raud \
    --expiry <ISO8601> --https-only \
    --account-name staticsitesops10798 --account-key <key> -o tsv
  ```

  Table CORS must allow the site origin (set once with the account key via
  `az storage cors add --services t ...`).
- **Access model:** the site is IP-restricted, so the embedded write SAS is only
  reachable from allowed networks.
- **Baking into the snapshot:** set `AUDIT_TABLE_CONN` (a storage connection
  string) when running the pipeline to materialise flags into a `pmFlag` column
  so they persist in the versioned snapshot:

  ```bash
  AUDIT_DB_CS='...' AUDIT_TABLE_CONN='DefaultEndpointsProtocol=...' \
    python audit_snapshot.py --incremental
  ```

  Requires `azure-data-tables`. Use `--no-flags` to skip.

## Scheduled refresh (cron / GitHub Actions)

The app reads a pre-built `snapshot.json.gz`. Automate rebuild + deploy so reviewers
always see fresh data. The snapshot records `meta.builtUtc`; the UI shows it as
**“Data refreshed …”** in the header.

### Option A — GitHub Actions (recommended, runs even when your laptop is off)

Workflow: [`.github/workflows/refresh-snapshot.yml`](.github/workflows/refresh-snapshot.yml)
— Mondays 05:00 UTC, plus a manual **Run workflow** button.

Add these **repository secrets** (Settings → Secrets → Actions):

| Secret | How to get it |
| --- | --- |
| `KIOSK_BEARER_TOKEN` | [kiosk-ui.frontiersin.org](https://kiosk-ui.frontiersin.org) → DevTools → any API call → `Authorization: Bearer …` |
| `GCP_SA_KEY` | JSON key for a service account with BigQuery job user + read on `frontiers-ocean` (same access your `gcloud auth application-default login` uses) |
| `AZURE_CREDENTIALS` | JSON from `az ad sp create-for-rbac …` with **Storage Blob Data Contributor** on `staticsitesops10798` |

Your interactive `az login` / `gcloud` sessions are **not** enough for GitHub — the
workflow needs these stored credentials. If you can upload blobs today with
`az storage blob upload --auth-mode login`, you likely have permission to create
the service principal or ask IT for one scoped to `prototypes/network-analysis/*`.

The job also stores `audit-pipeline/raw_snapshot.pkl` in blob storage so incremental
runs stay fast (~2 min vs ~20 min full pull).

### Option B — Mac cron (works with your current login, machine must stay on)

```bash
cp .env.example .env          # add KIOSK_BEARER_TOKEN
cp ../frontiers-mcp/get_creds.py .   # optional helper (git-ignored)
python3 -m venv .dbenv && .dbenv/bin/pip install -r requirements.txt google-cloud-bigquery requests
az login && gcloud auth application-default login   # refresh when cron starts failing
chmod +x scripts/refresh_and_deploy.sh
crontab -e
# 0 6 * * 1  /Users/you/Code/network-analysis/scripts/refresh_and_deploy.sh >> /tmp/network-analysis-refresh.log 2>&1
```

`KIOSK_BEARER_TOKEN` must be renewed occasionally (copy a fresh bearer from Kiosk UI).
`az` / `gcloud` tokens also expire — re-login when the log shows auth errors.

## Deploying

Upload the `audit-network/` folder to the Frontiers static webapp storage under
the `network-analysis` slug (served at the URL above). Requires `az login`.
