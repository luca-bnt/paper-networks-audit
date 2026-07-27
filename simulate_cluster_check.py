#!/usr/bin/env python3
"""Local Cluster Analysis simulation — BLOCK / WARN / PASS rates from snapshot.

Reads audit-network/data/snapshot.json.gz (no DB, no pandas). Implements the
evaluator in docs/aira-checks/cluster-analysis-prd.md as closely as
the snapshot allows.

Limitations vs full PRD:
  - No ASN in snapshot → network proximity weight unused
  - B2 approximated as wdStatus == red (indicator 75)
  - B1 needs pmFlag > 0 (bake flags when rebuilding snapshot)
  - Only articles present in the snapshot (connected hubs, 90d window)

Usage:
  python3 simulate_cluster_check.py
  python3 simulate_cluster_check.py --limit 5000
  python3 simulate_cluster_check.py --csv /tmp/cluster_sim.csv
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SNAPSHOT = ROOT / "audit-network" / "data" / "snapshot.json.gz"

# PRD weights / thresholds
WEIGHTS = {
    "device": 10,
    "ip": 8,
    "wdAuthor": 8,
    "wdEditedBy": 8,
    "wdCompany": 6,  # papermill template / org fingerprint
    "locale": 1,
}
DECISION = ("device", "ip", "wdAuthor", "wdEditedBy")
RANK_ATTRS = ("device", "ip", "wdAuthor", "wdEditedBy", "wdCompany", "locale")
ATTR_POOL = {
    "ip": "ips",
    "device": "devices",
    "locale": "locales",
    "wdAuthor": "wdAuthors",
    "wdEditedBy": "wdEditedBys",
    "wdCompany": "wdCompanies",
}
T_RETRIEVE = 3  # peer enters ranked match list
T_WARN = 34  # max peer score; prefer low WARN rate (see analyze sweep)
HUB_MIN = 5
WD_RED = 3  # meta.enums.status["red"]
NET_ATTRS = frozenset({"ip", "device"})
DOC_ATTRS = frozenset({"wdAuthor", "wdEditedBy"})


def load_snapshot(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def pool_str(D: dict, field: str, row: int) -> str:
    ref = D["articles"][field][row]
    if ref is None or ref < 0:
        return ""
    pool = ATTR_POOL.get(field) or {
        "authorName": "names",
        "authorOrg": "orgs",
    }.get(field)
    if not pool:
        return ""
    vals = D["dict"].get(pool) or []
    return vals[ref] if 0 <= ref < len(vals) else ""


def parse_date(s: str) -> date | None:
    if not s or len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def time_boost(a: date | None, b: date | None) -> float:
    if not a or not b:
        return 0.0
    days = abs((a - b).days)
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.5
    return 0.0


def score_pair(
    matched: set[str],
    *,
    date_a: date | None,
    date_b: date | None,
    org_a: str,
    org_b: str,
) -> float:
    ip = "ip" in matched
    network = 8.0 if ip else 0.0  # ASN not in snapshot
    total = network
    for t, w in WEIGHTS.items():
        if t == "ip":
            continue
        if t in matched:
            total += w
    total += time_boost(date_a, date_b)
    decision_hit = bool(matched & set(DECISION))
    if org_a and org_b and decision_hit:
        if org_a != org_b:
            total += 2.0
        elif ip or "device" in matched:
            total -= 2.0
    if (ip or "device" in matched) and ("wdAuthor" in matched or "wdEditedBy" in matched):
        total += 4.0
    return total


def build_lookups(D: dict) -> tuple[dict[str, dict[int, list[int]]], dict[str, list[tuple]]]:
    """value_to_rows[attr][ref] = rows; hubs[attr] = list of (ref, rows, nAuthors, nOrgs)."""
    value_to_rows: dict[str, dict[int, list[int]]] = {a: {} for a in RANK_ATTRS}
    hubs: dict[str, list[tuple]] = {a: [] for a in DECISION}
    for attr in RANK_ATTRS:
        for ref, rows, n_authors, n_orgs in D["index"].get(attr) or []:
            value_to_rows[attr][ref] = rows
            if attr in DECISION:
                hubs[attr].append((ref, rows, n_authors, n_orgs))
    return value_to_rows, hubs


def simulate(D: dict, *, limit: int | None = None) -> tuple[list[dict], dict]:
    arts = D["articles"]
    n = D["meta"]["count"]
    caps = D["meta"].get("caps") or {}
    value_to_rows, hubs = build_lookups(D)

    # row → decision hub membership that already pass size/authors/orgs (share checked per subject)
    row_hubs: dict[int, list[tuple[str, list[int], int, int]]] = defaultdict(list)
    for attr in DECISION:
        cap = caps.get(attr, 120)
        for ref, rows, n_authors, n_orgs in hubs[attr]:
            if len(rows) < HUB_MIN or len(rows) > cap:
                continue
            if n_authors < 2 or n_orgs < 2:
                continue
            for i in rows:
                row_hubs[i].append((attr, rows, n_authors, n_orgs))

    dates = [parse_date(arts["date"][i]) for i in range(n)]
    orgs = [pool_str(D, "authorOrg", i) for i in range(n)]
    names = [pool_str(D, "authorName", i) for i in range(n)]
    flagged = set(i for i in range(n) if arts["pmFlag"][i])

    def share(rows: list[int], subject: int) -> float:
        name = names[subject]
        if not name or not rows:
            return 0.0
        same = sum(1 for j in rows if names[j] == name)
        return same / len(rows)

    results: list[dict] = []
    reasons = Counter()
    outcomes = Counter()
    end = n if limit is None else min(n, limit)
    t0 = time.time()

    for i in range(end):
        # B2
        b2 = arts["wdStatus"][i] == WD_RED

        # Collect peers via token lookup
        peer_matches: dict[int, set[str]] = defaultdict(set)
        for attr in RANK_ATTRS:
            ref = arts[attr][i]
            if ref is None or ref < 0:
                continue
            for j in value_to_rows[attr].get(ref, ()):
                if j != i:
                    peer_matches[j].add(attr)

        scores: list[tuple[float, int, set[str]]] = []
        for j, matched in peer_matches.items():
            s = score_pair(
                matched,
                date_a=dates[i],
                date_b=dates[j],
                org_a=orgs[i],
                org_b=orgs[j],
            )
            if s >= T_RETRIEVE:
                scores.append((s, j, matched))
        scores.sort(reverse=True, key=lambda x: x[0])
        max_score = scores[0][0] if scores else 0.0

        def hub_ok(rows: list[int], n_authors: int, n_orgs: int, cap: int) -> bool:
            size = len(rows)
            if size < HUB_MIN or size > cap or n_authors < 2 or n_orgs < 2:
                return False
            return share(rows, i) <= 0.5

        # Filter-passing decision hubs for this subject
        passing_decision: set[str] = set()
        for attr, rows, n_authors, n_orgs in row_hubs.get(i, ()):
            if hub_ok(rows, n_authors, n_orgs, caps.get(attr, 120)):
                passing_decision.add(attr)

        # B0: all four decision attrs
        b0 = all(a in passing_decision for a in DECISION)

        # B1: flagged peer with (ip|device) ∧ (wd*) on filter-passing shared evidence
        b1 = False
        if flagged:
            for _s, j, matched in scores:
                if j not in flagged:
                    continue
                net = bool(matched & NET_ATTRS)
                doc = bool(matched & DOC_ATTRS)
                if not (net and doc):
                    continue
                for attr, rows, n_authors, n_orgs in row_hubs.get(i, ()):
                    if attr not in matched:
                        continue
                    if j in rows and hub_ok(rows, n_authors, n_orgs, caps.get(attr, 120)):
                        b1 = True
                        break
                if b1:
                    break

        if b2 or b0 or b1:
            outcome = "BLOCK"
            if b2:
                reasons["B2"] += 1
            if b0:
                reasons["B0"] += 1
            if b1:
                reasons["B1"] += 1
        elif max_score >= T_WARN:
            outcome = "WARN"
            reasons["WARN"] += 1
        else:
            outcome = "PASS"
            reasons["PASS"] += 1

        outcomes[outcome] += 1
        results.append(
            {
                "article_id": arts["id"][i],
                "outcome": outcome,
                "max_score": round(max_score, 2),
                "n_peers": len(scores),
                "b0": int(b0),
                "b1": int(b1),
                "b2": int(b2),
                "pm_flag": int(arts["pmFlag"][i]),
            }
        )

        if (i + 1) % 10000 == 0:
            print(f"  … {i+1:,}/{end:,}", file=sys.stderr)

    summary = {
        "articles": end,
        "elapsed_sec": round(time.time() - t0, 1),
        "outcomes": dict(outcomes),
        "rates": {k: round(v / end, 4) for k, v in outcomes.items()},
        "block_reasons": {k: reasons[k] for k in ("B0", "B1", "B2") if reasons[k]},
        "warn_pass": {k: reasons[k] for k in ("WARN", "PASS") if reasons[k]},
        "flagged_in_snapshot": len(flagged),
        "thresholds": {
            "T_retrieve": T_RETRIEVE,
            "T_warn": T_WARN,
            "hub_min": HUB_MIN,
        },
        "limitations": [
            "Denominator = snapshot articles only (already hub-connected, not all submissions)",
            "ASN not in snapshot — proximity weight unused",
            "B2 = wdStatus red",
            "B1 needs baked pmFlag (currently often 0)",
        ],
    }
    return results, summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument("--limit", type=int, default=None, help="Only first N articles (smoke test)")
    ap.add_argument("--csv", type=Path, default=None, help="Write per-article outcomes CSV")
    args = ap.parse_args()

    if not args.snapshot.exists():
        sys.exit(f"snapshot not found: {args.snapshot}")

    print(f"loading {args.snapshot} …", file=sys.stderr)
    D = load_snapshot(args.snapshot)
    print(
        f"snapshot {D['meta'].get('builtUtc')} · {D['meta']['count']:,} articles · "
        f"{D['meta'].get('windowDays')}d",
        file=sys.stderr,
    )
    print("simulating …", file=sys.stderr)
    results, summary = simulate(D, limit=args.limit)

    print(json.dumps(summary, indent=2))

    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
        print(f"wrote {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
