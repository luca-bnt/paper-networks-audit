#!/usr/bin/env python3
"""Backfill article status / journal / section on the audit raw cache via BigQuery.

Deprecated: use enrich_context_from_bigquery.py which also fills title and authors.

Usage:
  .dbenv/bin/python enrich_status_journal_from_bigquery.py \
    --raw audit-pipeline/raw_snapshot_enriched.pkl \
    --out audit-pipeline/raw_snapshot_enriched.pkl \
    --days 90
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd

from audit_snapshot import RAW_COLS, fetch_article_context_bq

REPO = Path(__file__).resolve().parent
RAW_DEFAULT = REPO / "audit-pipeline" / "raw_snapshot_enriched.pkl"


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

    meta = fetch_article_context_bq(args.days)[["ArticleId", "stageId", "stageName", "journal", "section"]]
    if meta.empty:
        sys.exit("BigQuery returned no article metadata — check BQ_PROJECT / ADC auth")

    for c in ("stageId", "stageName", "journal", "section"):
        if c in df.columns:
            df = df.drop(columns=[c])
    df = df.merge(meta, on="ArticleId", how="left")
    matched = int(df["stageName"].notna().sum())

    rej = int((df["stageName"] == "Rejected").sum())
    jn = int(df["journal"].notna().sum())
    print(
        f"[enrich] matched {matched:,}/{len(df):,} snapshot rows · "
        f"{jn:,} journal · {rej:,} rejected",
        file=sys.stderr,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pickle.dumps(df.reindex(columns=RAW_COLS)))
    print(f"[enrich] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
