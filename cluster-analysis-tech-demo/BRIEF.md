---
workflow: general-video
flow: companion
storyboard: yes
message: "Cluster Analysis indexes identity, caps fanout, and shortlists the few peers that earn a BLOCK or WARN — so reviewers don't scan a hairball"
destination: embed
aspect: 1920x1080
language: en
audience: technical reviewers and integrity engineers
length: ~148s
angle: mechanism pitch
---

## Intent

A technical pitch for the AIRA Cluster Analysis check. Same glass/blue visual system as
the Paper Networks Audit product demo, but no mock UI tour — numbers, hashes, pipeline
diagrams, and decision thresholds. Voice: nerdy, precise, impact-first — never self-praise
(“clever”); imply the engineering quality through metaphors and accuracy jobs.
Longer than the product demo (~90s). No TTS required for the storyboard pass; optional
later if we want narration.

## Assets

- assets/frontiers.png — Frontiers wordmark (same as product demo)

## Customizations

- Count-up / big-number treatments on thresholds (16 hex, caps 120/500, K=20, T_warn=34, T_retrieve=3)
- Infographic pipeline: hash → capped lookup → scored shortlist → BLOCK/WARN/PASS
- Two efficiency frames, both on measured data: O(N²) 2.03B pairs vs O(N·t·c) 778k (2,614×, widening
  to 26,144× at 10× corpus); then median 13 candidates touched, 2.9s per window, 20 rows on the card,
  6.4% reaching a human — Cluster Analysis costs what a single-file check costs
- Visual style locked to sibling `audit-network-demo` (deep blue glass, Inter, cyan accent)
- Never say breakthrough / leap / clever — let the ratios imply the step-change

## Notes

- Source of truth for thresholds/rules: `docs/aira-checks/cluster-analysis-prd.md`
- Source of truth for measured stats: `simulate_cluster_check.py` over
  `audit-network/data/snapshot.json.gz` (63,792 articles, 90d, built 2026-07-23)
- Completely separate project from `audit-network-demo/`
- Companion + storyboard: plan → sketches → build together
