# Network Analysis — Paper Connection Audit

A standalone, zero-build web app for auditing hidden connections between manuscripts,
plus the Python pipeline that produces its data snapshot from `service-aira`.

**Live:** https://network-analysis.temporary-static-webapp.frontiersin.net/

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

## Layout

```
audit-network/          # the static app (deploy this folder)
  index.html            #   single-file vanilla JS + Canvas UI
  data/snapshot.json.gz #   dictionary-encoded, columnar, gzipped snapshot
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

## Deploying

Upload the `audit-network/` folder to the Frontiers static webapp storage under
the `network-analysis` slug (served at the URL above). Requires `az login`.
