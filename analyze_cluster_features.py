#!/usr/bin/env python3
"""Data-driven analysis of Cluster Analysis tokens, caps, weights, and score WARN.

Uses:
  - audit-network/data/snapshot.json.gz  (pair scores, outcome separation)
  - audit-pipeline/raw_snapshot.pkl      (uncapped value DF — if present)

Outputs JSON summary to stdout; optional --out report path.
"""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from device_profile_id import compute_device_profile_id  # noqa: E402
from simulate_cluster_check import (  # noqa: E402
    DECISION,
    DOC_ATTRS,
    HUB_MIN,
    NET_ATTRS,
    RANK_ATTRS,
    WEIGHTS,
    build_lookups,
    load_snapshot,
    parse_date,
    pool_str,
    score_pair,
)

SNAPSHOT = ROOT / "audit-network" / "data" / "snapshot.json.gz"
RAW = ROOT / "audit-pipeline" / "raw_snapshot.pkl"
from audit_snapshot import GENERIC_WD  # noqa: E402  — keep stoplist single-sourced
WD_AUTHOR_RE = re.compile(r"Author:\s*(.*?)\s*</li>", re.I | re.S)
WD_EDITED_RE = re.compile(r"Last modified by:\s*(.*?)\s*</li>", re.I | re.S)
WD_COMPANY_RE = re.compile(r"Company:\s*(.*?)\s*</li>", re.I | re.S)
PLACEHOLDERS = {"", "na", "n/a", "none", "nan", "null", "unknown", "-"}
PRD_CAPS = {
    "device": 120, "ip": 120, "asn": 80,
    "wdAuthor": 500, "wdEditedBy": 500, "wdCompany": 500, "locale": 25,
}


def pct(xs, p: float) -> float:
    if len(xs) == 0:
        return float("nan")
    return float(np.percentile(xs, p))


def clean(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in PLACEHOLDERS else s


def parse_wd(msg):
    if not isinstance(msg, str):
        return "", "", ""
    a = WD_AUTHOR_RE.search(msg)
    e = WD_EDITED_RE.search(msg)
    c = WD_COMPANY_RE.search(msg)
    return (
        clean(a.group(1) if a else ""),
        clean(e.group(1) if e else ""),
        clean(c.group(1) if c else ""),
    )


def df_stats(counter: Counter, cap: int) -> dict:
    sizes = sorted(counter.values())
    if not sizes:
        return {"n_values": 0}
    arr = np.array(sizes)
    over = int((arr > cap).sum())
    mass_over = int(arr[arr > cap].sum()) if over else 0
    total = int(arr.sum())
    return {
        "n_values": int(len(arr)),
        "n_articles_with_value": total,
        "size_p50": pct(arr, 50),
        "size_p90": pct(arr, 90),
        "size_p95": pct(arr, 95),
        "size_p99": pct(arr, 99),
        "size_max": int(arr.max()),
        "values_over_cap": over,
        "articles_in_over_cap_values": mass_over,
        "pct_articles_in_over_cap_values": round(mass_over / total, 4) if total else 0,
        "cap": cap,
        "singleton_values": int((arr == 1).sum()),
        "values_size_2_to_cap": int(((arr >= 2) & (arr <= cap)).sum()),
        "values_ge5_le_cap": int(((arr >= 5) & (arr <= cap)).sum()),
    }


def analyze_raw_caps(raw_path: Path) -> dict:
    print(f"loading raw {raw_path} …", file=sys.stderr)
    t0 = time.time()
    df = pickle.load(open(raw_path, "rb"))
    print(f"  {len(df):,} rows in {time.time()-t0:.1f}s", file=sys.stderr)

    counters = {k: Counter() for k in ("device", "ip", "asn", "locale", "wdAuthor", "wdEditedBy", "wdCompany")}
    for r in df.to_dict("records"):
        ip = clean(r.get("IpHash"))[:16]
        if ip:
            counters["ip"][ip] += 1
        asn = clean(r.get("AsnHash"))
        if asn:
            counters["asn"][asn] += 1
        langs = clean(r.get("Languages"))
        tz = clean(r.get("Timezone"))
        if langs and tz:
            counters["locale"][f"{langs}|{tz}"] += 1
        device = compute_device_profile_id(r) or ""
        if device and re.fullmatch(r"[a-f0-9]{64}", device):
            counters["device"][device[:16]] += 1
        wa, we, wc = parse_wd(r.get("wdMessage"))
        if wa and wa.lower() not in GENERIC_WD:
            counters["wdAuthor"][wa] += 1
        if we and we.lower() not in GENERIC_WD:
            counters["wdEditedBy"][we] += 1
        if wc and wc.lower() not in GENERIC_WD:
            counters["wdCompany"][wc] += 1

    out = {}
    for k, ctr in counters.items():
        out[k] = df_stats(ctr, PRD_CAPS[k])
        # top values (anonymized length + size only)
        top = ctr.most_common(5)
        out[k]["top5_sizes"] = [c for _, c in top]
    return out


def analyze_snapshot_scores(D: dict, *, sample_neg: int = 200_000) -> dict:
    """Pair-level score analysis + article max_score vs structural labels."""
    arts = D["articles"]
    n = D["meta"]["count"]
    caps = D["meta"].get("caps") or {}
    value_to_rows, hubs = build_lookups(D)

    row_hubs: dict[int, list] = defaultdict(list)
    for attr in DECISION:
        for ref, rows, n_authors, n_orgs in hubs[attr]:
            if not (HUB_MIN <= len(rows) <= caps.get(attr, 120)):
                continue
            if n_authors < 2 or n_orgs < 2:
                continue
            for i in rows:
                row_hubs[i].append((attr, rows, n_authors, n_orgs))

    dates = [parse_date(arts["date"][i]) for i in range(n)]
    orgs = [pool_str(D, "authorOrg", i) for i in range(n)]
    names = [pool_str(D, "authorName", i) for i in range(n)]

    def share(rows, subject):
        name = names[subject]
        if not name or not rows:
            return 0.0
        return sum(1 for j in rows if names[j] == name) / len(rows)

    # Sample matched pairs via hubs (positive-ish: share ≥1 token)
    matched_scores = []
    matched_types = Counter()  # frozenset of types → count
    type_marginal = Counter()  # how often each type appears in a scored pair
    combo_scores = defaultdict(list)  # pattern label → scores

    rng = np.random.default_rng(42)
    # Walk a sample of articles for tractability
    sample_rows = rng.choice(n, size=min(n, 15_000), replace=False)
    seen_pairs = set()

    for i in sample_rows:
        peer_matches: dict[int, set[str]] = defaultdict(set)
        for attr in RANK_ATTRS:
            ref = arts[attr][i]
            if ref is None or ref < 0:
                continue
            for j in value_to_rows[attr].get(ref, ()):
                if j != i:
                    peer_matches[j].add(attr)
        for j, matched in peer_matches.items():
            a, b = (i, j) if i < j else (j, i)
            if (a, b) in seen_pairs:
                continue
            seen_pairs.add((a, b))
            s = score_pair(
                matched,
                date_a=dates[i], date_b=dates[j],
                org_a=orgs[i], org_b=orgs[j],
            )
            matched_scores.append(s)
            key = frozenset(matched & set(WEIGHTS))
            # collapse network nesting for pattern label
            labs = set(matched)
            if "ip" in labs:
                labs.discard("ip")  # still note via pattern below
            pattern = "+".join(sorted(matched))
            combo_scores[pattern].append(s)
            for t in matched:
                type_marginal[t] += 1
            matched_types[pattern] += 1

    matched_scores = np.array(matched_scores, dtype=float)

    # Random non-matching pairs (negative): score should be 0
    # More useful: article-level max_score distribution by structural class
    article_max = np.zeros(n)
    article_n_peers = np.zeros(n, dtype=int)
    passing_sets = []

    for i in range(n):
        peer_matches = defaultdict(set)
        for attr in RANK_ATTRS:
            ref = arts[attr][i]
            if ref is None or ref < 0:
                continue
            for j in value_to_rows[attr].get(ref, ()):
                if j != i:
                    peer_matches[j].add(attr)
        scores = []
        for j, matched in peer_matches.items():
            scores.append(
                score_pair(
                    matched,
                    date_a=dates[i], date_b=dates[j],
                    org_a=orgs[i], org_b=orgs[j],
                )
            )
        article_n_peers[i] = len(scores)
        article_max[i] = max(scores) if scores else 0.0

        passing = set()
        for attr, rows, n_authors, n_orgs in row_hubs.get(i, ()):
            if share(rows, i) <= 0.5 and n_authors >= 2 and n_orgs >= 2:
                if HUB_MIN <= len(rows) <= caps.get(attr, 120):
                    passing.add(attr)
        passing_sets.append(passing)

    # Labels
    b0 = np.array([all(a in p for a in DECISION) for p in passing_sets])
    near_b0 = np.array([len(p) >= 3 for p in passing_sets])
    net_doc = np.array([
        bool(p & NET_ATTRS) and bool(p & DOC_ATTRS) for p in passing_sets
    ])
    structural_warn = near_b0 | net_doc
    wd_red = np.array([arts["wdStatus"][i] == 3 for i in range(n)])
    multi_org_hub = np.array([len(p) >= 1 for p in passing_sets])  # any filter-passing decision hub

    def dist(mask, name):
        xs = article_max[mask]
        if xs.size == 0:
            return {"n": 0}
        return {
            "n": int(xs.size),
            "max_score_p10": round(pct(xs, 10), 2),
            "max_score_p25": round(pct(xs, 25), 2),
            "max_score_p50": round(pct(xs, 50), 2),
            "max_score_p75": round(pct(xs, 75), 2),
            "max_score_p90": round(pct(xs, 90), 2),
            "max_score_p95": round(pct(xs, 95), 2),
            "max_score_mean": round(float(xs.mean()), 2),
        }

    # Threshold sweep for score-based WARN: rate + overlap with structural / B0 / wd_red
    thresholds = list(range(6, 37, 2))
    sweep = []
    for t in thresholds:
        pred = article_max >= t
        # exclude B0∪wd_red from WARN rate (those are BLOCK)
        blockish = b0 | wd_red
        warn_only = pred & ~blockish
        sweep.append({
            "T": t,
            "pct_max_score_ge_T": round(float(pred.mean()), 4),
            "pct_WARN_if_not_BLOCK": round(float(warn_only.mean()), 4),
            "recall_structural_warn": round(float((pred & structural_warn).sum() / structural_warn.sum()), 4)
            if structural_warn.any() else None,
            "precision_vs_structural": round(float((pred & structural_warn).sum() / pred.sum()), 4)
            if pred.any() else None,
            "recall_b0": round(float((pred & b0).sum() / b0.sum()), 4) if b0.any() else None,
            "recall_wd_red": round(float((pred & wd_red).sum() / wd_red.sum()), 4) if wd_red.any() else None,
            "mean_peers_when_ge_T": round(float(article_n_peers[pred].mean()), 1) if pred.any() else None,
        })

    # Weight / type lift: among pairs, P(multi-org conflicting | type) vs baseline
    # Use article-level: for articles whose best peer match includes type t, rate of structural_warn
    type_best = {t: [] for t in RANK_ATTRS}
    # subsample for type presence in best peer
    for i in sample_rows:
        peer_matches = defaultdict(set)
        for attr in RANK_ATTRS:
            ref = arts[attr][i]
            if ref is None or ref < 0:
                continue
            for j in value_to_rows[attr].get(ref, ()):
                if j != i:
                    peer_matches[j].add(attr)
        if not peer_matches:
            continue
        best_j, best_m, best_s = None, None, -1
        for j, matched in peer_matches.items():
            s = score_pair(
                matched,
                date_a=dates[i], date_b=dates[j],
                org_a=orgs[i], org_b=orgs[j],
            )
            if s > best_s:
                best_s, best_j, best_m = s, j, matched
        for t in best_m:
            type_best[t].append(1 if structural_warn[i] or b0[i] else 0)

    type_lift = {}
    base = float((structural_warn | b0).mean())
    for t, ys in type_best.items():
        if not ys:
            type_lift[t] = {"n": 0}
            continue
        rate = float(np.mean(ys))
        type_lift[t] = {
            "n": len(ys),
            "P_structural_or_B0_given_type_in_best_peer": round(rate, 4),
            "baseline": round(base, 4),
            "lift": round(rate / base, 3) if base else None,
            "prd_weight": WEIGHTS.get(t),
        }

    # Top score patterns
    top_patterns = sorted(matched_types.items(), key=lambda x: -x[1])[:25]
    pattern_summary = []
    for pat, cnt in top_patterns:
        sc = np.array(combo_scores[pat])
        pattern_summary.append({
            "pattern": pat,
            "n_pairs": cnt,
            "score_fixed": round(float(sc[0]), 2) if len(set(sc.round(2))) == 1 else None,
            "score_mean": round(float(sc.mean()), 2),
            "score_p50": round(pct(sc, 50), 2),
        })

    # Snapshot kept-bucket sizes vs caps (post-cap view)
    kept = {}
    for attr in RANK_ATTRS:
        sizes = [len(rows) for ref, rows, *_ in D["index"].get(attr) or []]
        if not sizes:
            kept[attr] = {}
            continue
        arr = np.array(sizes)
        kept[attr] = {
            "buckets": len(arr),
            "p50": pct(arr, 50),
            "p90": pct(arr, 90),
            "p99": pct(arr, 99),
            "max": int(arr.max()),
            "prd_cap": PRD_CAPS.get(attr),
            "pct_buckets_within_20pct_of_cap": round(
                float((arr >= 0.8 * PRD_CAPS.get(attr, 120)).mean()), 4
            ),
        }

    return {
        "pair_scores": {
            "n_unique_pairs_sampled": int(len(matched_scores)),
            "p10": round(pct(matched_scores, 10), 2),
            "p25": round(pct(matched_scores, 25), 2),
            "p50": round(pct(matched_scores, 50), 2),
            "p75": round(pct(matched_scores, 75), 2),
            "p90": round(pct(matched_scores, 90), 2),
            "p95": round(pct(matched_scores, 95), 2),
            "p99": round(pct(matched_scores, 99), 2),
            "mean": round(float(matched_scores.mean()), 2),
        },
        "article_max_score_by_label": {
            "all": dist(np.ones(n, dtype=bool), "all"),
            "B0_all4": dist(b0, "b0"),
            "near_B0_ge3": dist(near_b0 & ~b0, "near"),
            "network_and_doc_not_B0": dist(net_doc & ~b0, "netdoc"),
            "structural_warn_not_B0": dist(structural_warn & ~b0, "sw"),
            "any_passing_hub_only": dist(multi_org_hub & ~structural_warn & ~b0, "weak"),
            "no_passing_decision_hub": dist(~multi_org_hub, "none"),
            "wd_red": dist(wd_red, "red"),
        },
        "label_prevalence": {
            "B0": round(float(b0.mean()), 4),
            "near_B0": round(float(near_b0.mean()), 4),
            "network_and_doc": round(float(net_doc.mean()), 4),
            "structural_warn": round(float(structural_warn.mean()), 4),
            "wd_red": round(float(wd_red.mean()), 4),
            "any_passing_decision_hub": round(float(multi_org_hub.mean()), 4),
        },
        "score_warn_threshold_sweep": sweep,
        "type_lift_vs_structural": type_lift,
        "top_match_patterns": pattern_summary,
        "kept_bucket_sizes": kept,
        "single_feature_score_table": {
            t: (8 if t == "ip" else WEIGHTS[t])
            + (0)  # base without boosts
            for t in RANK_ATTRS
        },
    }


def recommend(report: dict) -> list[str]:
    recs = []
    caps = report.get("uncapped_df") or {}
    for attr, st in caps.items():
        if not st or st.get("n_values", 0) == 0:
            continue
        cap = st["cap"]
        p99 = st["size_p99"]
        mx = st["size_max"]
        over_pct = st["pct_articles_in_over_cap_values"]
        if mx <= cap:
            recs.append(f"CAP {attr}: max DF={mx} ≤ cap={cap} — cap never binds; could lower toward p99≈{p99:.0f} or keep headroom.")
        elif over_pct > 0.15:
            recs.append(
                f"CAP {attr}: {over_pct:.1%} of valued articles sit in over-cap values (max={mx}). "
                f"Cap={cap} is aggressive — consider raising toward p99≈{p99:.0f} if those are true hotspots to keep."
            )
        else:
            recs.append(
                f"CAP {attr}: max={mx}, p99≈{p99:.0f}, {over_pct:.1%} articles in over-cap values — "
                f"cap={cap} looks reasonable (drops fat head, keeps body)."
            )

    sweep = report["snapshot_scores"]["score_warn_threshold_sweep"]
    # Prefer T where WARN rate (not BLOCK) in 3–12% and precision vs structural ≥ 0.5 if possible
    candidates = [
        row for row in sweep
        if 0.03 <= row["pct_WARN_if_not_BLOCK"] <= 0.12
        and (row["precision_vs_structural"] or 0) >= 0.4
    ]
    if candidates:
        # pick highest precision then closest to 5–8% warn
        best = sorted(
            candidates,
            key=lambda r: (-(r["precision_vs_structural"] or 0), abs((r["pct_WARN_if_not_BLOCK"] or 0) - 0.06)),
        )[0]
        recs.append(
            f"SCORE WARN: data favors T_warn≈{best['T']} → "
            f"WARN rate {best['pct_WARN_if_not_BLOCK']:.1%} (excl. BLOCK), "
            f"precision vs structural {best['precision_vs_structural']:.2f}, "
            f"recall structural {best['recall_structural_warn']:.2f}."
        )
    else:
        # fallback: minimize |warn_rate - 0.07|
        best = min(sweep, key=lambda r: abs((r["pct_WARN_if_not_BLOCK"] or 0) - 0.07))
        recs.append(
            f"SCORE WARN: no T hit 3–12% with precision≥0.4; nearest to 7% is T={best['T']} "
            f"(WARN {best['pct_WARN_if_not_BLOCK']:.1%}, prec {best['precision_vs_structural']})."
        )

    lifts = report["snapshot_scores"]["type_lift_vs_structural"]
    ordered = sorted(
        ((t, v) for t, v in lifts.items() if v.get("n", 0) >= 100),
        key=lambda kv: -(kv[1].get("lift") or 0),
    )
    if ordered:
        line = ", ".join(f"{t}: lift={v['lift']:.2f} (w={v['prd_weight']})" for t, v in ordered)
        recs.append(f"WEIGHT lift order (P(structural|type in best peer) / baseline): {line}")
        # flag inversions vs PRD weight order
        prd_order = ["device", "ip", "wdAuthor", "wdEditedBy", "wdCompany", "locale"]
        lift_order = [t for t, _ in ordered]
        recs.append(f"PRD weight order: {prd_order}; empirical lift order: {lift_order}")

    labs = report["snapshot_scores"]["article_max_score_by_label"]
    if labs.get("B0_all4", {}).get("n"):
        recs.append(
            f"SCORE separation: B0 median max_score={labs['B0_all4']['max_score_p50']}, "
            f"structural WARN (not B0) median={labs.get('structural_warn_not_B0', {}).get('max_score_p50')}, "
            f"weak hub-only median={labs.get('any_passing_hub_only', {}).get('max_score_p50')}, "
            f"no passing hub median={labs.get('no_passing_decision_hub', {}).get('max_score_p50')}."
        )
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--skip-raw", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    report = {"prd_caps": PRD_CAPS, "prd_weights": WEIGHTS}

    print("analyzing snapshot scores …", file=sys.stderr)
    D = load_snapshot(args.snapshot)
    report["snapshot_meta"] = {
        "builtUtc": D["meta"].get("builtUtc"),
        "count": D["meta"]["count"],
        "windowDays": D["meta"].get("windowDays"),
    }
    t0 = time.time()
    report["snapshot_scores"] = analyze_snapshot_scores(D)
    print(f"  snapshot analysis {time.time()-t0:.1f}s", file=sys.stderr)

    if not args.skip_raw and args.raw.exists():
        report["uncapped_df"] = analyze_raw_caps(args.raw)
    else:
        report["uncapped_df"] = None
        report["uncapped_note"] = "raw pickle skipped or missing — cap analysis limited to kept snapshot buckets"

    report["recommendations"] = recommend(report)

    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)

    print("\n=== RECOMMENDATIONS ===", file=sys.stderr)
    for r in report["recommendations"]:
        print(f"• {r}", file=sys.stderr)


if __name__ == "__main__":
    main()
