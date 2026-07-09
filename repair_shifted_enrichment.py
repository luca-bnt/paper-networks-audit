#!/usr/bin/env python3
"""Repair off-by-one enrichment bug (Id column shifted name/email/org).

Symptom: authorName=title, authorEmail=name, authorOrg=email after ResourceModel
backfill. Rotates name/email back, then re-fetches organisation from DB.
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

from enrich_authors_from_resourcemodel import (
    AUTHOR_FIELDS,
    AUTHOR_INDICES,
    _clean,
    _empty,
    _pick_author,
    chunks,
    connect,
    parse_cs,
)

REPO = Path(__file__).resolve().parent
DEFAULT_IN = REPO / "audit-pipeline" / "raw_snapshot_enriched.pkl"


def _shifted_mask(df: pd.DataFrame) -> pd.Series:
    org = df.get("authorOrg", pd.Series("", index=df.index)).fillna("").astype(str)
    em = df.get("authorEmail", pd.Series("", index=df.index)).fillna("").astype(str)
    return org.str.contains("@", regex=False) & ~em.str.contains("@", regex=False)


def rotate_shifted(df: pd.DataFrame) -> int:
    m = _shifted_mask(df)
    n = int(m.sum())
    if not n:
        return 0
    df.loc[m, "authorName"] = df.loc[m, "authorEmail"].values
    df.loc[m, "authorEmail"] = df.loc[m, "authorOrg"].values
    df.loc[m, "authorOrg"] = ""
    return n


def fetch_orgs(cs: str, article_ids: list[int], days: int, batch: int) -> dict[int, str]:
    if not article_ids:
        return {}
    conn = connect(cs)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT Id, ExternalId FROM Resources WITH (NOLOCK)
            WHERE ResourceTypeDefinitionId=1 AND Created >= DATEADD(day,-{days},GETUTCDATE())"""
    )
    ext_to_rid = {int(ext): int(rid) for rid, ext in cur.fetchall() if ext is not None}
    rid_to_ext = {v: k for k, v in ext_to_rid.items()}
    res_ids = [ext_to_rid[a] for a in article_ids if a in ext_to_rid]

    sel = ["rv.Id", "JSON_VALUE(rv.ResourceModel,'$.submission.manuscriptDetails.title')"]
    for i in range(AUTHOR_INDICES):
        for f in AUTHOR_FIELDS:
            sel.append(f"JSON_VALUE(rv.ResourceModel,'$.submission.authors[{i}].{f}')")
    sel_sql = ",".join(sel)

    out: dict[int, str] = {}
    t0 = time.time()
    for bi, batch in enumerate(chunks(res_ids, batch)):
        idcsv = ",".join(map(str, batch))
        cur.execute(
            f"""WITH ranked AS (
                    SELECT Id, ResourceId,
                           ROW_NUMBER() OVER (PARTITION BY ResourceId ORDER BY Version DESC, Id DESC) rn
                    FROM ResourceVersion WITH (NOLOCK) WHERE ResourceId IN ({idcsv}))
                SELECT ResourceId, Id FROM ranked WHERE rn=1"""
        )
        vid_to_rid = {int(vid): int(rid) for rid, vid in cur.fetchall()}
        vcsv = ",".join(map(str, vid_to_rid))
        if not vcsv:
            continue
        cur.execute(f"SELECT {sel_sql} FROM ResourceVersion rv WITH (NOLOCK) WHERE rv.Id IN ({vcsv})")
        for row in cur.fetchall():
            aid = rid_to_ext.get(vid_to_rid.get(int(row[0])))
            if aid is None:
                continue
            _, _, org = _pick_author(list(row)[1:])
            if org:
                out[aid] = org
        if (bi + 1) % 10 == 0:
            print(f"[repair] org fetch batch {bi+1} · {len(out):,} orgs ({time.time()-t0:.0f}s)", file=sys.stderr)
    conn.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--connection-string", default=os.environ.get("AUDIT_DB_CS"))
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_IN))
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--batch", type=int, default=1500)
    ap.add_argument("--skip-org-fetch", action="store_true")
    args = ap.parse_args()

    path = Path(args.inp)
    df = pickle.loads(path.read_bytes())
    df["ArticleId"] = df["ArticleId"].astype("int64")
    n_rot = rotate_shifted(df)
    print(f"[repair] rotated {n_rot:,} shifted rows (name/email)", file=sys.stderr)

    if not args.skip_org_fetch:
        if not args.connection_string:
            sys.exit("Provide --connection-string or AUDIT_DB_CS for org backfill")
        need_org = df.loc[_empty(df["authorOrg"]) & df["authorEmail"].fillna("").astype(str).str.contains("@"), "ArticleId"].tolist()
        print(f"[repair] fetching org for {len(need_org):,} articles", file=sys.stderr)
        orgs = fetch_orgs(args.connection_string, need_org, args.days, args.batch)
        idx = {aid: i for i, aid in zip(df.index, df["ArticleId"])}
        n_org = 0
        for aid, org in orgs.items():
            i = idx.get(aid)
            if i is not None and _empty(pd.Series([df.at[i, "authorOrg"]])).iloc[0]:
                df.at[i, "authorOrg"] = org
                n_org += 1
        print(f"[repair] applied org to {n_org:,} rows", file=sys.stderr)

    out = Path(args.out)
    out.write_bytes(pickle.dumps(df))
    print(f"[repair] wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
