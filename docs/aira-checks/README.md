# AIRA checks

| Doc | Surface |
|-----|---------|
| [`cluster-analysis.yaml`](./cluster-analysis.yaml) | **Cluster Analysis** — spec (source of truth) |
| [`cluster-analysis-prd.md`](./cluster-analysis-prd.md) | Cluster Analysis — stakeholder PRD (do not implement from this) |
| [`../spec.schema.json`](../spec.schema.json) | Shared spec field schema |

## Local tooling (this repo)

```bash
python3 simulate_cluster_check.py
python3 analyze_cluster_features.py --out /tmp/cluster_feature_analysis.json
```

> Both scripts still implement the superseded rule set (B0, WARN thresholds, attached filters) and have not been updated for flagged-only retrieval. Their output does not describe the current check.
