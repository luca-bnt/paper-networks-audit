#!/usr/bin/env python3
"""Backfill article context on the audit raw cache via BigQuery.

Fills status, journal, section, title, and submitting-author name/email/org from
``frontiers-ocean.dataset_frontiersgraph`` in one query (~25s for 90 days).
Replaces both ResourceModel JSON backfill and ``enrich_authors_from_resourcemodel.py``.

Usage:
  .dbenv/bin/python enrich_context_from_bigquery.py \
    --raw audit-pipeline/raw_snapshot_enriched.pkl \
    --days 90
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

from audit_snapshot import RAW_COLS, fetch_article_context_bq

REPO = Path(__file__).resolve().parent
RAW_DEFAULT = REPO / "audit-pipeline" / "raw_snapshot_enriched.pkl"

CONTEXT_COLS = [
    "stageId", "stageName", "journal", "section", "articleType",
    "ArticleTitle", "authorName", "authorEmail", "authorOrg",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(RAW_DEFAULT))
    ap.add_argument("--out", default=None, help="defaults to --raw (in-place)")
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    raw_path = Path(args.raw)
    if not raw_path.exists():
        sys.exit(f"No raw cache at {raw_path}")
    out_path = Path(args.out or args.raw)

    df = pickle.loads(raw_path.read_bytes())
    df["ArticleId"] = df["ArticleId"].astype("int64")
    print(f"[enrich] loaded {len(df):,} rows", file=sys.stderr)

    ctx = fetch_article_context_bq(args.days)
    if ctx.empty:
        sys.exit("BigQuery returned no article context — check BQ_PROJECT / ADC auth")

    keep_ip = df[["ArticleId", "authorIp"]] if "authorIp" in df.columns else None
    drop = [c for c in CONTEXT_COLS if c in df.columns]
    if drop:
        df = df.drop(columns=drop)
    df = df.merge(ctx, on="ArticleId", how="left")
    if keep_ip is not None:
        df = df.drop(columns=["authorIp"], errors="ignore").merge(keep_ip, on="ArticleId", how="left")

    matched = int(df["authorEmail"].fillna("").astype(str).str.strip().astype(bool).sum())
    rej = int((df["stageName"] == "Rejected").sum())
    print(
        f"[enrich] {matched:,}/{len(df):,} with author email · "
        f"{int(df['journal'].notna().sum()):,} journal · {rej:,} rejected",
        file=sys.stderr,
    )

    out_path.write_bytes(pickle.dumps(df.reindex(columns=RAW_COLS)))
    print(f"[enrich] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
