#!/usr/bin/env python3
"""Backfill missing submitting-author + title data on the audit raw cache.

The base pull (``audit_snapshot.py``) only gets author name/email/org/title from
``PaperMillAuthorMetaData`` / ``PaperMillMetaData``, which cover ~11% of recent
articles. The ground truth for the rest lives in ``ResourceVersion.ResourceModel``
JSON, but the model carries the full body text so anything that forces a full
parse (``OPENJSON`` over the authors array, transferring the whole blob) is
impractically slow (>19h for the set).

The cheap path, benchmarked at ~14-15 ms/row, is server-side **scalar**
``JSON_VALUE`` on fixed author indices. The submitting author is authors[0] ~61%
of the time, so we pull the first few indices and pick submitting >
corresponding > first-named in Python. Author IP is not present in the model
(only PaperMill has it), so it is left untouched.

Two-phase per the service-aira notes: find the latest ``ResourceVersion.Id`` via
the ``ResourceId`` index (no JSON), then extract JSON by PK for just those ids.

Usage:
  AUDIT_DB_CS='Server=...;Database=service-aira;User Id=...;Password=...' \
    .dbenv/bin/python enrich_authors_from_resourcemodel.py \
      --raw audit-pipeline/raw_snapshot.pkl \
      --out audit-pipeline/raw_snapshot_enriched.pkl
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent
RAW_DEFAULT = REPO / "audit-pipeline" / "raw_snapshot.pkl"
OUT_DEFAULT = REPO / "audit-pipeline" / "raw_snapshot_enriched.pkl"

# Author indices probed per article. Submitting author is almost always among the
# first few; anything beyond falls back to the first named author (still a real
# co-author, useful as a shared-value proxy).
AUTHOR_INDICES = 4
AUTHOR_FIELDS = ["fullName", "primaryEmail", "affiliations[0].name", "isSubmittingAuthor", "isCorrespondingAuthor"]
TITLE_MAX = 300  # titles are naturally short; guard against pathological blobs

PLACEHOLDERS = {"", "na", "n/a", "none", "nan", "null", "unknown", "-"}


def parse_cs(cs: str) -> dict:
    low = {k.strip().lower(): v.strip() for k, v in (x.split("=", 1) for x in cs.split(";") if "=" in x)}
    return {
        "server": low.get("server", low.get("data source", "")),
        "user": low.get("user id", low.get("uid", "")),
        "password": low.get("password", low.get("pwd", "")),
        "database": low.get("database", low.get("initial catalog", "service-aira")),
    }


def connect(cs: str):
    import pymssql

    cfg = parse_cs(cs)
    return pymssql.connect(cfg["server"], cfg["user"], cfg["password"], cfg["database"], timeout=600, login_timeout=30)


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in PLACEHOLDERS else s


def _empty(series: pd.Series) -> pd.Series:
    """True where a df cell is missing/blank/placeholder."""
    s = series.fillna("").astype(str).str.strip().str.lower()
    return s.isin(PLACEHOLDERS)


def _pick_author(cols: list[str | None]) -> tuple[str, str, str]:
    """cols is the flat JSON_VALUE row (title + AUTHOR_INDICES * AUTHOR_FIELDS)."""
    authors = []
    for i in range(AUTHOR_INDICES):
        base = 1 + i * len(AUTHOR_FIELDS)
        name = _clean(cols[base])
        email = _clean(cols[base + 1])
        org = _clean(cols[base + 2])
        is_sub = cols[base + 3] == "true"
        is_cor = cols[base + 4] == "true"
        if name or email:
            authors.append((is_sub, is_cor, name, email, org))
    if not authors:
        return "", "", ""
    # submitting > corresponding > first named
    authors.sort(key=lambda a: (0 if a[0] else 1 if a[1] else 2))
    _, _, name, email, org = authors[0]
    return name, email, org


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connection-string", default=os.environ.get("AUDIT_DB_CS"))
    ap.add_argument("--raw", default=str(RAW_DEFAULT))
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--days", type=int, default=90, help="recent window for the Resources ExternalId->Id map")
    ap.add_argument("--batch", type=int, default=1500, help="resource ids per DB round-trip")
    args = ap.parse_args()

    if not args.connection_string:
        sys.exit("Provide --connection-string or AUDIT_DB_CS env var")

    raw_path = Path(args.raw)
    if not raw_path.exists():
        sys.exit(f"No raw cache at {raw_path}")
    df = pickle.loads(raw_path.read_bytes())
    df["ArticleId"] = df["ArticleId"].astype("int64")
    print(f"[enrich] loaded {len(df):,} rows", file=sys.stderr)

    # target = rows missing any of the author bundle or the title
    need = (
        _empty(df.get("authorName", pd.Series("", index=df.index)))
        | _empty(df.get("authorEmail", pd.Series("", index=df.index)))
        | _empty(df.get("authorOrg", pd.Series("", index=df.index)))
        | _empty(df.get("ArticleTitle", pd.Series("", index=df.index)))
    )
    target_ids = df.loc[need, "ArticleId"].tolist()
    print(f"[enrich] {len(target_ids):,} articles need backfill", file=sys.stderr)

    conn = connect(args.connection_string)
    cur = conn.cursor()

    # ExternalId (=ArticleId) -> internal ResourceId, recent window (indexed, no JSON)
    t = time.time()
    cur.execute(
        f"""SELECT Id, ExternalId FROM Resources WITH (NOLOCK)
            WHERE ResourceTypeDefinitionId=1 AND Created >= DATEADD(day,-{args.days},GETUTCDATE())"""
    )
    ext_to_rid = {int(ext): int(rid) for rid, ext in cur.fetchall() if ext is not None}
    rid_to_ext = {v: k for k, v in ext_to_rid.items()}
    print(f"[enrich] resource map: {len(ext_to_rid):,} ({time.time()-t:.1f}s)", file=sys.stderr)

    res_ids = [ext_to_rid[a] for a in target_ids if a in ext_to_rid]
    print(f"[enrich] {len(res_ids):,} resolvable resource ids", file=sys.stderr)

    sel = ["rv.Id", "JSON_VALUE(rv.ResourceModel,'$.submission.manuscriptDetails.title')"]
    for i in range(AUTHOR_INDICES):
        for f in AUTHOR_FIELDS:
            sel.append(f"JSON_VALUE(rv.ResourceModel,'$.submission.authors[{i}].{f}')")
    sel_sql = ",".join(sel)

    # resumable checkpoint: filled dict + processed resource ids
    ckpt = Path(str(args.out) + ".ckpt")
    filled: dict[int, tuple[str, str, str, str]] = {}
    processed: set[int] = set()
    if ckpt.exists():
        state = pickle.loads(ckpt.read_bytes())
        filled = {int(k): tuple(v) for k, v in state["filled"].items()}
        processed = set(state["processed"])
        print(f"[enrich] resumed checkpoint: {len(processed):,} done, {len(filled):,} filled", file=sys.stderr)

    def reconnect():
        nonlocal conn, cur
        try:
            conn.close()
        except Exception:
            pass
        for attempt in range(5):
            try:
                conn = connect(args.connection_string)
                cur = conn.cursor()
                return
            except Exception as e:
                print(f"[enrich] reconnect attempt {attempt+1} failed: {e}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("could not reconnect")

    def run_batch(batch: list[int]) -> None:
        idcsv = ",".join(map(str, batch))
        cur.execute(
            f"""WITH ranked AS (
                    SELECT Id, ResourceId,
                           ROW_NUMBER() OVER (PARTITION BY ResourceId ORDER BY Version DESC, Id DESC) rn
                    FROM ResourceVersion WITH (NOLOCK) WHERE ResourceId IN ({idcsv}))
                SELECT ResourceId, Id FROM ranked WHERE rn=1"""
        )
        vid_to_rid = {int(vid): int(rid) for rid, vid in cur.fetchall()}
        vids = list(vid_to_rid)
        for vbatch in chunks(vids, args.batch):
            vcsv = ",".join(map(str, vbatch))
            cur.execute(f"SELECT {sel_sql} FROM ResourceVersion rv WITH (NOLOCK) WHERE rv.Id IN ({vcsv})")
            for row in cur.fetchall():
                vid = int(row[0])
                aid = rid_to_ext.get(vid_to_rid.get(vid))
                if aid is None:
                    continue
                title = _clean(row[1])[:TITLE_MAX]
                name, email, org = _pick_author(list(row))
                if name or email or org or title:
                    filled[aid] = (name, email, org, title)

    pending = [rid for rid in res_ids if rid not in processed]
    print(f"[enrich] {len(pending):,} resource ids pending this run", file=sys.stderr)
    t0 = time.time()
    done = 0
    for bi, batch in enumerate(chunks(pending, args.batch)):
        for attempt in range(4):
            try:
                run_batch(batch)
                break
            except Exception as e:
                print(f"[enrich] batch error ({e}); reconnecting (attempt {attempt+1})", file=sys.stderr)
                reconnect()
        else:
            raise RuntimeError("batch failed after retries")
        processed.update(batch)
        done += len(batch)
        if (bi + 1) % 5 == 0 or done >= len(pending):
            ckpt.write_bytes(pickle.dumps({"filled": filled, "processed": processed}))
        rate = done / max(time.time() - t0, 0.1)
        eta = (len(pending) - done) / max(rate, 0.1)
        print(
            f"[enrich] batch {bi+1}: {done:,}/{len(pending):,} · {len(filled):,} filled · "
            f"{rate:.0f}/s · eta {eta/60:.1f}m",
            file=sys.stderr,
        )

    ckpt.write_bytes(pickle.dumps({"filled": filled, "processed": processed}))
    try:
        conn.close()
    except Exception:
        pass

    # apply — only where the df cell is currently empty (precompute empty masks once)
    for col in ("authorName", "authorEmail", "authorOrg", "ArticleTitle"):
        if col not in df.columns:
            df[col] = None
    idx_by_aid = {aid: i for i, aid in zip(df.index, df["ArticleId"].tolist())}
    empty_ids = {
        col: set(df.loc[_empty(df[col]), "ArticleId"].tolist())
        for col in ("authorName", "authorEmail", "authorOrg", "ArticleTitle")
    }
    n_name = n_email = n_org = n_title = 0
    for aid, (name, email, org, title) in filled.items():
        i = idx_by_aid.get(aid)
        if i is None:
            continue
        if name and aid in empty_ids["authorName"]:
            df.at[i, "authorName"] = name; n_name += 1
        if email and aid in empty_ids["authorEmail"]:
            df.at[i, "authorEmail"] = email; n_email += 1
        if org and aid in empty_ids["authorOrg"]:
            df.at[i, "authorOrg"] = org; n_org += 1
        if title and aid in empty_ids["ArticleTitle"]:
            df.at[i, "ArticleTitle"] = title; n_title += 1

    print(
        f"[enrich] filled cells — name:{n_name:,} email:{n_email:,} org:{n_org:,} title:{n_title:,}",
        file=sys.stderr,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pickle.dumps(df))
    print(f"[enrich] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
