# AIRA checks

| Doc | Surface |
|-----|---------|
| [`cluster-analysis-prd.md`](./cluster-analysis-prd.md) | **Cluster Analysis** — in-review check (BLOCK / PASS) |

## Local tooling (this repo)

```bash
python3 simulate_cluster_check.py
python3 analyze_cluster_features.py --out /tmp/cluster_feature_analysis.json
```

> Both scripts still implement the superseded rule set (B0, WARN thresholds, attached filters) and have not been updated for flagged-only retrieval. Their output does not describe the current check.
