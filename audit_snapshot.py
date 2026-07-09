#!/usr/bin/env python3
"""Build the audit-network snapshot from service-aira (last N days).

Two phases:
  1. FETCH  - pull a 90-day snapshot of per-article attributes and cache raw.
  2. BUILD  - derive connective attributes, apply the common-value cap, run
              union-find, drop singletons, and write a compact gzipped snapshot.

Data sources (see repo notes):
  - DeviceFingerprints            -> ip / asn / device profile / locale (full)
  - Indicators def 75 (Message)   -> Word-doc author / last-modified-by / company
  - Indicators def 80 (Message)   -> AIRA papermill risk score (%)
  - PaperMillAuthorMetaData       -> submitting/corresponding author name/email/org (subset)
  - PaperMillMetaData             -> article title (subset)

ResourceModel is intentionally NOT read (avg ~145 KB/row -> ~11 GB for 76k).

Usage:
  # first run / periodic full rebuild (pulls the whole 90-day window):
  AUDIT_DB_CS='Server=...;Database=service-aira;User Id=...;Password=...' \
    .dbenv/bin/python audit_snapshot.py --days 90
  # weekly refresh (cheap): reuse cache, pull only the recent slice, drop aged-out:
  AUDIT_DB_CS='...' .dbenv/bin/python audit_snapshot.py --incremental --refresh-days 14
  # rebuild encoding only, no DB:
  .dbenv/bin/python audit_snapshot.py --from-raw --cap 50

Trailing-window refresh:
  The 90-day window slides forward. On a weekly cadence only ~1 week of
  articles is new, but enrichment (fingerprints / indicators / author metadata)
  can land a few days after Created, so --incremental re-pulls the last
  --refresh-days (default 14 = 7d new + 7d buffer) and reuses the cached
  remainder, discarding rows older than --days. This queries ~15% of the data
  per run instead of 100%.

  Rows that age out of the window are appended to a local-only archive
  (--archive, default audit-pipeline/archive_snapshot.pkl, git-ignored) so they
  can be retrieved later; use --no-archive to skip.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import pickle
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from device_profile_id import compute_device_profile_id
from papermill_scoring import author_display_name, email_similarity_score

REPO = Path(__file__).resolve().parent
OUT_DEFAULT = REPO / "audit-network" / "data" / "snapshot.json.gz"
RAW_DEFAULT = REPO / "audit-pipeline" / "raw_snapshot.pkl"
# Local-only append archive of rows aged out of the trailing window (never shipped).
ARCHIVE_DEFAULT = REPO / "audit-pipeline" / "archive_snapshot.pkl"

WORDDOC_INDICATOR = 75
PAPERMILL_INDICATOR = 80
STATUS_NAME = {1: "green", 2: "yellow", 3: "red", 4: "n/a", 7: "gold", 9: "unchecked"}

PLACEHOLDERS = {"", "na", "n/a", "none", "nan", "null", "unknown", "-"}

# Titles are display-only (never connective). A short preview keeps the gzipped
# snapshot under the 8 MB budget once author/email/org are backfilled for the
# full set (full titles alone add ~3 MB gz).
TITLE_MAX = 60

# Canonical raw-cache schema. fetch() always returns exactly these columns so
# incremental slices and the cached remainder concat without misalignment.
RAW_COLS = [
    "ArticleId", "Created",
    "IpHash", "AsnHash", "DeviceId", "CanvasHash", "WebglHash", "HwIdHash", "UaFamilyHash",
    "Platform", "ScreenWidth", "ScreenHeight", "DevicePixelRatio", "Languages", "Timezone", "UaFamily",
    "wdStatus", "wdMessage", "pmStatus", "pmMessage",
    "authorName", "authorEmail", "authorOrg", "authorIp", "ArticleTitle",
]

# ---------------------------------------------------------------------------
# connection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# phase 1: fetch
# ---------------------------------------------------------------------------

def fetch(cs: str, days: int) -> pd.DataFrame:
    conn = connect(cs)

    def q(sql):
        return pd.read_sql(sql, conn)

    t = time.time()
    res = q(
        f"""SELECT Id AS ResourceId, ExternalId AS ArticleId, Created
            FROM Resources WITH (NOLOCK)
            WHERE ResourceTypeDefinitionId=1 AND Created >= DATEADD(day,-{days},GETUTCDATE())"""
    )
    res["ArticleId"] = res["ArticleId"].astype("int64")
    print(f"[fetch] recent articles: {len(res):,} ({time.time()-t:.1f}s)", file=sys.stderr)

    art_ids = res["ArticleId"].tolist()
    res_ids = res["ResourceId"].tolist()
    rid_to_aid = dict(zip(res["ResourceId"], res["ArticleId"]))

    # device fingerprints (latest per article), bounded to recent window
    t = time.time()
    fp = q(
        f"""WITH ranked AS (
                SELECT df.ArticleId, df.IpHash, df.AsnHash, df.DeviceId,
                       df.CanvasHash, df.WebglHash, df.HwIdHash, df.UaFamilyHash,
                       df.Platform, df.ScreenWidth, df.ScreenHeight, df.DevicePixelRatio,
                       df.Languages, df.Timezone, df.UaFamily,
                       ROW_NUMBER() OVER (PARTITION BY df.ArticleId
                           ORDER BY df.LastEnrichUtc DESC, df.Id DESC) rn
                FROM DeviceFingerprints df WITH (NOLOCK)
                JOIN Resources r WITH (NOLOCK) ON r.ExternalId = df.ArticleId
                WHERE r.Created >= DATEADD(day,-{days},GETUTCDATE()))
            SELECT ArticleId, IpHash, AsnHash, DeviceId, CanvasHash, WebglHash, HwIdHash,
                   UaFamilyHash, Platform, ScreenWidth, ScreenHeight, DevicePixelRatio,
                   Languages, Timezone, UaFamily
            FROM ranked WHERE rn=1"""
    )
    fp["ArticleId"] = fp["ArticleId"].astype("int64")
    print(f"[fetch] device fingerprints: {len(fp):,} ({time.time()-t:.1f}s)", file=sys.stderr)

    # indicators 75 (word doc) + 80 (papermill) latest per resource
    t = time.time()
    frames = []
    for i, batch in enumerate(chunks(res_ids, 2000)):
        idcsv = ",".join(map(str, batch))
        frames.append(
            q(
                f"""SELECT ResourceId, IndicatorDefinitionId, Created, Status, Message
                    FROM Indicators WITH (NOLOCK)
                    WHERE IndicatorDefinitionId IN ({WORDDOC_INDICATOR},{PAPERMILL_INDICATOR})
                      AND ResourceId IN ({idcsv})"""
            )
        )
        if (i + 1) % 10 == 0:
            print(f"[fetch]   indicators batch {i+1}", file=sys.stderr)
    ind = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not ind.empty:
        ind = (
            ind.sort_values("Created")
            .groupby(["ResourceId", "IndicatorDefinitionId"], as_index=False)
            .last()
        )
        ind["ArticleId"] = ind["ResourceId"].map(rid_to_aid)
    print(f"[fetch] indicator rows (latest): {len(ind):,} ({time.time()-t:.1f}s)", file=sys.stderr)

    wd = ind[ind.IndicatorDefinitionId == WORDDOC_INDICATOR][["ArticleId", "Status", "Message"]].copy()
    wd.columns = ["ArticleId", "wdStatus", "wdMessage"]
    pm = ind[ind.IndicatorDefinitionId == PAPERMILL_INDICATOR][["ArticleId", "Status", "Message"]].copy()
    pm.columns = ["ArticleId", "pmStatus", "pmMessage"]

    # author metadata (subset) - prefer submitting > corresponding > any
    t = time.time()
    frames = []
    for batch in chunks(art_ids, 2000):
        idcsv = ",".join(map(str, batch))
        frames.append(
            q(
                f"""SELECT ArticleId, FirstName, MiddleName, LastName, Email, Organisation, Role, IpAddress
                    FROM PaperMillAuthorMetaData WITH (NOLOCK) WHERE ArticleId IN ({idcsv})"""
            )
        )
    amd = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    author = _pick_author(amd)
    print(f"[fetch] author metadata: {len(author):,} of {len(art_ids):,} ({time.time()-t:.1f}s)", file=sys.stderr)

    # title (subset)
    t = time.time()
    frames = []
    for batch in chunks(art_ids, 2000):
        idcsv = ",".join(map(str, batch))
        frames.append(
            q(f"SELECT ArticleID AS ArticleId, ArticleTitle FROM PaperMillMetaData WITH (NOLOCK) WHERE ArticleID IN ({idcsv})")
        )
    tt = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not tt.empty:
        tt["ArticleId"] = tt["ArticleId"].astype("int64")
        tt = tt.dropna(subset=["ArticleTitle"]).groupby("ArticleId", as_index=False).first()
    print(f"[fetch] titles: {len(tt):,} ({time.time()-t:.1f}s)", file=sys.stderr)

    conn.close()

    df = res[["ArticleId", "Created"]].merge(fp, on="ArticleId", how="left")
    for extra in (wd, pm, author, tt):
        if not extra.empty:
            df = df.merge(extra, on="ArticleId", how="left")
    return df.reindex(columns=RAW_COLS)


def _created_naive(df: pd.DataFrame) -> pd.Series:
    """Article Created as tz-naive UTC (DB uses GETUTCDATE())."""
    created = pd.to_datetime(df["Created"], errors="coerce")
    if getattr(created.dt, "tz", None) is not None:
        created = created.dt.tz_convert("UTC").dt.tz_localize(None)
    return created


def _within_window(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """Keep only rows whose article Created is within the trailing `days` window."""
    now = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
    cutoff = now - pd.Timedelta(days=days)
    return df[_created_naive(df) >= cutoff].copy()


def fetch_incremental(cs: str, window_days: int, refresh_days: int, cache: pd.DataFrame) -> pd.DataFrame:
    """Reuse the cached in-window rows; re-pull only the recent `refresh_days` slice.

    The recent slice covers brand-new articles plus a buffer for late-arriving
    enrichment (fingerprints / indicators / author metadata land after Created).
    Rows older than the trailing window are discarded.
    """
    cache = cache.reindex(columns=RAW_COLS)
    created = _created_naive(cache)
    cutoff = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None)) - pd.Timedelta(days=window_days)
    in_win = created >= cutoff
    kept, aged = cache[in_win].copy(), cache[~in_win].copy()

    fresh = fetch(cs, refresh_days)
    fresh_ids = set(fresh["ArticleId"].tolist())

    # Drop refreshed articles from the cached remainder, then splice the fresh slice in.
    remainder = kept[~kept["ArticleId"].isin(fresh_ids)]
    merged = pd.concat([fresh, remainder], ignore_index=True)
    merged = merged.drop_duplicates("ArticleId", keep="first")
    merged = _within_window(merged, window_days)

    print(
        f"[incremental] reused {len(remainder):,} cached · refreshed/added {len(fresh):,} "
        f"(last {refresh_days}d) · aged out {len(aged):,} · total {len(merged):,}",
        file=sys.stderr,
    )
    return merged, aged


def _archive_rows(aged: pd.DataFrame, archive_path: Path) -> None:
    """Append rows that aged out of the window to a local-only archive (dedup by ArticleId)."""
    if aged is None or aged.empty:
        return
    aged = aged.reindex(columns=RAW_COLS)
    if archive_path.exists():
        try:
            prev = pickle.loads(archive_path.read_bytes()).reindex(columns=RAW_COLS)
            combined = pd.concat([prev, aged], ignore_index=True)
        except Exception as e:
            print(f"[archive] could not read existing archive ({e}); starting fresh", file=sys.stderr)
            combined = aged
    else:
        combined = aged
    combined = combined.drop_duplicates("ArticleId", keep="last")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(pickle.dumps(combined))
    print(f"[archive] +{len(aged):,} aged-out rows -> {archive_path} ({len(combined):,} total retained)", file=sys.stderr)


def _pick_author(amd: pd.DataFrame) -> pd.DataFrame:
    if amd.empty:
        return pd.DataFrame(columns=["ArticleId", "authorName", "authorEmail", "authorOrg", "authorIp"])
    amd = amd.copy()
    amd["ArticleId"] = amd["ArticleId"].astype("int64")
    rank = {"submitting author": 0, "corresponding author": 1}
    amd["rank"] = amd["Role"].fillna("").str.lower().map(rank).fillna(2)
    amd = amd.sort_values(["ArticleId", "rank"])
    picked = amd.groupby("ArticleId", as_index=False).first()
    out = pd.DataFrame({"ArticleId": picked["ArticleId"]})
    out["authorName"] = [
        author_display_name(f, m, l, None)
        for f, m, l in zip(picked.FirstName, picked.MiddleName, picked.LastName)
    ]
    out["authorEmail"] = picked["Email"].fillna("").str.strip()
    out["authorOrg"] = picked["Organisation"].fillna("").str.strip()
    out["authorIp"] = picked["IpAddress"].fillna("").str.strip()
    return out


# ---------------------------------------------------------------------------
# phase 2: derive + encode
# ---------------------------------------------------------------------------

def clean(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in PLACEHOLDERS else s


RISK_RE = re.compile(r"risk:\s*([\d.]+)\s*%", re.I)
BAND_RE = re.compile(r"(low|medium|high)\s+risk", re.I)
WD_AUTHOR_RE = re.compile(r"Author:\s*(.*?)\s*</li>", re.I | re.S)
WD_EDITED_RE = re.compile(r"Last modified by:\s*(.*?)\s*</li>", re.I | re.S)
WD_COMPANY_RE = re.compile(r"Company:\s*(.*?)\s*</li>", re.I | re.S)


def parse_papermill(msg) -> tuple[float | None, str]:
    if not isinstance(msg, str):
        return None, ""
    m = RISK_RE.search(msg)
    band = BAND_RE.search(msg)
    return (float(m.group(1)) if m else None), (band.group(1).lower() if band else "")


def parse_worddoc(msg):
    if not isinstance(msg, str):
        return "", "", "", None
    a = WD_AUTHOR_RE.search(msg)
    e = WD_EDITED_RE.search(msg)
    c = WD_COMPANY_RE.search(msg)
    match = None
    if "does not match" in msg.lower():
        match = False
    elif "matches the author" in msg.lower():
        match = True
    return (
        clean(a.group(1) if a else ""),
        clean(e.group(1) if e else ""),
        clean(c.group(1) if c else ""),
        match,
    )


def email_pattern(email: str) -> str:
    if not email or "@" not in email:
        return ""
    local = email.split("@", 1)[0].lower()
    if not local:
        return ""
    if local.isdigit():
        return "all-digits"
    if re.fullmatch(r"[a-z]+\.[a-z]+", local):
        return "name.surname"
    if re.fullmatch(r"[a-z]+", local):
        return "all-alpha"
    if re.search(r"[a-z]", local) and re.search(r"\d", local):
        return "alpha+digits"
    return "other"


# All indexed attributes (drive edges/weight/filters in the UI).
ATTRS = ["email", "ip", "device", "locale", "wdAuthor", "wdEditedBy", "wdCompany", "authorIp"]
# Strong attributes that decide connectivity (keep an article in the snapshot).
# Weak ones (locale) are indexed for weight + filtering but never keep an article
# on their own, otherwise generic language/timezone overlaps dominate.
COMPONENT_ATTRS = ["email", "ip", "device", "wdAuthor", "wdEditedBy", "wdCompany", "authorIp"]

# Per-attribute common-value cap. Identity attrs keep large (suspicious) rings;
# word-doc + weak attrs are capped low because their generic values are noise.
DEFAULT_CAPS = {
    "email": 120, "ip": 120, "device": 120, "authorIp": 120,
    "wdAuthor": 40, "wdEditedBy": 40, "wdCompany": 40,
    "locale": 25,
}
# Pool name per attribute (shared with the columnar string dictionaries).
ATTR_POOL = {
    "email": "emails", "ip": "ips", "device": "devices",
    "locale": "locales", "wdAuthor": "wdAuthors", "wdEditedBy": "wdEditedBys",
    "wdCompany": "wdCompanies", "authorIp": "authorIps",
}
# Generic Word-doc author/company values that must never link manuscripts.
GENERIC_WD = {
    "administrator", "admin", "windows user", "user", "microsoft", "microsoft office user",
    "microsoft office", "dell", "hp", "lenovo", "acer", "asus", "pc", "author", "default",
    "guest", "owner", "windows", "toshiba", "samsung", "office", "hpuser", "administrateur",
    "usuario", "utente", "windows 用户", "用户", "administrator1", "1", "123",
}


def fetch_flags(conn_str: str, table: str = "pmflags") -> set:
    """Read manufactured-article flags from Azure Table Storage (RowKey = articleId)."""
    try:
        from azure.data.tables import TableClient
    except ImportError:
        print("[flags] azure-data-tables not installed; skipping bake (pip install azure-data-tables)", file=sys.stderr)
        return set()
    try:
        tc = TableClient.from_connection_string(conn_str, table_name=table)
        ids = set()
        for e in tc.list_entities(select=["RowKey"]):
            try:
                ids.add(int(e["RowKey"]))
            except (ValueError, TypeError):
                pass
        print(f"[flags] baked {len(ids):,} manufactured flags from table '{table}'", file=sys.stderr)
        return ids
    except Exception as ex:
        print(f"[flags] could not read table: {ex}", file=sys.stderr)
        return set()


def build(df: pd.DataFrame, cap: int, days: int, flag_ids: set | None = None) -> dict:
    flag_ids = flag_ids or set()
    n = len(df)
    rows = df.to_dict("records")

    # per-article derived values
    recs = []
    for r in rows:
        email = clean(r.get("authorEmail")).lower()
        name = clean(r.get("authorName"))
        pm_score, pm_band = parse_papermill(r.get("pmMessage"))
        wd_a, wd_e, wd_c, wd_match = parse_worddoc(r.get("wdMessage"))
        # word-doc props: prefer indicator-75 parse (broad)
        langs = clean(r.get("Languages"))
        tz = clean(r.get("Timezone"))
        device = compute_device_profile_id(r) or ""
        if device and not re.fullmatch(r"[a-f0-9]{64}", device):
            device = ""  # only trust full hardware profile hashes
        device = device[:16]  # truncate opaque hash (64-bit is collision-safe at this scale)
        rec = {
            "id": int(r["ArticleId"]),
            "date": _date(r.get("Created")),
            "title": clean(r.get("ArticleTitle"))[:TITLE_MAX],
            "authorName": name,
            "authorEmail": email,
            "authorOrg": clean(r.get("authorOrg")),
            "platform": clean(r.get("Platform")),
            "uaFamily": clean(r.get("UaFamily")),
            "pmScore": pm_score,
            "pmBand": pm_band,
            "wdStatus": STATUS_NAME.get(int(r["wdStatus"]), "") if pd.notna(r.get("wdStatus")) else "",
            "wdMatch": wd_match,
            "nameEmailSim": round(email_similarity_score(name, email), 1) if (name and email) else None,
            "emailPattern": email_pattern(email),
            # connective attribute values (empty -> no edge)
            "email": email,
            "ip": clean(r.get("IpHash"))[:16],
            "device": device,
            "locale": f"{langs}|{tz}" if (langs and tz) else "",
            "wdAuthor": wd_a,
            "wdEditedBy": wd_e,
            "wdCompany": wd_c,
            "authorIp": clean(r.get("authorIp")),
        }
        recs.append(rec)

    # inverted index per attribute with per-attribute common-value cap + stoplist
    caps = DEFAULT_CAPS if cap is None else {a: cap for a in ATTRS}
    is_wd = {"wdAuthor", "wdEditedBy", "wdCompany"}
    raw_index: dict[str, dict[str, list[int]]] = {a: {} for a in ATTRS}
    for i, rec in enumerate(recs):
        for a in ATTRS:
            v = rec[a]
            if not v:
                continue
            if a in is_wd and v.lower() in GENERIC_WD:
                continue
            raw_index[a].setdefault(v, []).append(i)
    kept_index = {
        a: {v: idxs for v, idxs in buckets.items() if 2 <= len(idxs) <= caps[a]}
        for a, buckets in raw_index.items()
    }

    # "connected" = appears in a kept bucket of a STRONG attribute (locale/asn are
    # weak enrichment: indexed for weight/filter but never keep an article on their own).
    connected: set[int] = set()
    for attr in COMPONENT_ATTRS:
        for idxs in kept_index.get(attr, {}).values():
            connected.update(idxs)
    keep = sorted(connected)
    old_to_new = {old: new for new, old in enumerate(keep)}

    n_buckets = sum(len(b) for b in kept_index.values())
    print(
        f"[build] connected articles: {len(keep):,} of {n:,} "
        f"(dropped {n-len(keep):,} singletons) · {n_buckets:,} shared-value buckets",
        file=sys.stderr,
    )
    return _encode(recs, keep, old_to_new, kept_index, caps, days, flag_ids)


def _date(v) -> str:
    if isinstance(v, str):
        return v[:10]
    try:
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _encode(recs, keep, old_to_new, kept_index, caps, days, flag_ids=None) -> dict:
    flag_ids = flag_ids or set()
    # string dictionaries (dedupe repeated values, reference by int; -1 = none)
    pools: dict[str, list[str]] = {}
    pool_idx: dict[str, dict[str, int]] = {}

    def ref(pool: str, value: str) -> int:
        if not value:
            return -1
        p = pool_idx.setdefault(pool, {})
        if value not in p:
            p[value] = len(p)
            pools.setdefault(pool, []).append(value)
        return p[value]

    STR_COLS = {
        "title": "titles",
        "authorName": "names",
        "authorEmail": "emails",
        "authorOrg": "orgs",
        "platform": "platforms",
        "uaFamily": "uaFamilies",
        "ip": "ips",
        "device": "devices",
        "locale": "locales",
        "wdAuthor": "wdAuthors",
        "wdEditedBy": "wdEditedBys",
        "wdCompany": "wdCompanies",
        "authorIp": "authorIps",
    }
    BAND = {"": 0, "low": 1, "medium": 2, "high": 3}
    STATUS = {"": 0, "green": 1, "yellow": 2, "red": 3, "gold": 4, "n/a": 5, "unchecked": 6}
    PATTERN = {"": 0, "all-digits": 1, "name.surname": 2, "all-alpha": 3, "alpha+digits": 4, "other": 5}

    cols: dict[str, list] = {k: [] for k in (
        "id", "date", *STR_COLS.keys(), "pmScore", "pmBand", "wdStatus", "wdMatch",
        "nameEmailSim", "emailPattern", "pmFlag",
    )}
    for old in keep:
        r = recs[old]
        cols["id"].append(r["id"])
        cols["date"].append(r["date"])  # kept as short strings; gzip handles repetition
        for field, pool in STR_COLS.items():
            cols[field].append(ref(pool, r[field]))
        cols["pmScore"].append(None if r["pmScore"] is None else round(r["pmScore"], 2))
        cols["pmBand"].append(BAND.get(r["pmBand"], 0))
        cols["wdStatus"].append(STATUS.get(r["wdStatus"], 0))
        cols["wdMatch"].append(-1 if r["wdMatch"] is None else (1 if r["wdMatch"] else 0))
        cols["nameEmailSim"].append(r["nameEmailSim"])
        cols["emailPattern"].append(PATTERN.get(r["emailPattern"], 0))
        cols["pmFlag"].append(1 if r["id"] in flag_ids else 0)

    # inverted index remapped to kept rows.
    # entry = [valueRef(into ATTR_POOL[attr]), [rowIdxs], nDistinctAuthors, nDistinctOrgs]
    index_out: dict[str, list] = {}
    for attr, buckets in kept_index.items():
        pool = ATTR_POOL[attr]
        entries = []
        for value, idxs in buckets.items():
            kept_old = [i for i in idxs if i in old_to_new]
            if len(kept_old) < 2:
                continue
            new_idxs = [old_to_new[i] for i in kept_old]
            names = {recs[i]["authorName"] for i in kept_old}
            names.discard("")
            orgs = {recs[i]["authorOrg"] for i in kept_old}
            orgs.discard("")
            entries.append([ref(pool, value), new_idxs, len(names), len(orgs)])
        if entries:
            index_out[attr] = entries

    return {
        "meta": {
            "builtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "windowDays": days,
            "caps": caps,
            "count": len(keep),
            "buckets": sum(len(v) for v in index_out.values()),
            "attributes": ATTRS,
            "attrPool": ATTR_POOL,
            "enums": {"band": BAND, "status": STATUS, "pattern": PATTERN},
        },
        "dict": pools,
        "articles": cols,
        "index": index_out,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--connection-string", default=os.environ.get("AUDIT_DB_CS"))
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--cap", type=int, default=None,
                    help="uniform common-value cap override; default uses per-attribute DEFAULT_CAPS")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--raw", default=str(RAW_DEFAULT))
    ap.add_argument("--from-raw", action="store_true", help="skip DB, rebuild encoding from cached raw pull")
    ap.add_argument("--incremental", action="store_true",
                    help="weekly refresh: reuse cache, pull only the recent --refresh-days slice, drop aged-out rows")
    ap.add_argument("--refresh-days", type=int, default=14,
                    help="recent slice re-pulled in --incremental mode (new articles + buffer for late enrichment)")
    ap.add_argument("--full", action="store_true", help="force a complete --days pull even if a cache exists")
    ap.add_argument("--archive", default=str(ARCHIVE_DEFAULT),
                    help="local-only file where rows aged out of the window are appended for later retrieval")
    ap.add_argument("--no-archive", action="store_true", help="do not archive aged-out rows during --incremental")
    ap.add_argument("--flags-table", default="pmflags", help="Azure Table with manufactured flags to bake into the snapshot")
    ap.add_argument("--no-flags", action="store_true", help="do not bake manufactured flags (set AUDIT_TABLE_CONN to enable)")
    args = ap.parse_args()

    raw_path = Path(args.raw)
    if args.from_raw:
        if not raw_path.exists():
            sys.exit(f"No raw cache at {raw_path}; run once without --from-raw")
        df = _within_window(pickle.loads(raw_path.read_bytes()), args.days)
        print(f"[raw] loaded {len(df):,} in-window rows from cache", file=sys.stderr)
    else:
        if not args.connection_string:
            sys.exit("Provide --connection-string or AUDIT_DB_CS env var")
        if args.incremental and not args.full and raw_path.exists():
            cache = pickle.loads(raw_path.read_bytes())
            df, aged = fetch_incremental(args.connection_string, args.days, args.refresh_days, cache)
            if not args.no_archive:
                _archive_rows(aged, Path(args.archive))
        else:
            if args.incremental and not raw_path.exists():
                print("[incremental] no cache found -> full pull this run", file=sys.stderr)
            df = fetch(args.connection_string, args.days)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(pickle.dumps(df))
        print(f"[raw] cached {len(df):,} rows -> {raw_path}", file=sys.stderr)

    flag_ids = set()
    table_conn = os.environ.get("AUDIT_TABLE_CONN")
    if table_conn and not args.no_flags:
        flag_ids = fetch_flags(table_conn, args.flags_table)

    snapshot = build(df, cap=args.cap, days=args.days, flag_ids=flag_ids)
    snapshot["meta"]["flags"] = len(flag_ids)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
    with gzip.open(out, "wb", compresslevel=9) as fh:
        fh.write(payload)
    size = out.stat().st_size
    m = snapshot["meta"]
    print(
        f"[write] {out}  {size/1e6:.2f} MB gz  ({len(payload)/1e6:.1f} MB raw)\n"
        f"        {m['count']:,} articles · {m['buckets']:,} shared-value buckets",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
