# Open questions

## Paper Networks Audit (explorer)

1. Auth model (Frontiers SSO / MyFrontiers / role gates)?
2. Who owns the production service vs the snapshot pipeline?
3. Retention policy for flags, comments, and seen/checked history?
4. Is the gzipped snapshot still the right serving model, or do we need live queries?
5. Brink / Lasagna UI migration scope for v1?
6. Manager reporting: in-app only, CSV, or both?

## Cluster Analysis (AIRA check)

Source of truth: [`aira-checks/cluster-analysis-prd.md`](./aira-checks/cluster-analysis-prd.md).

Still open there:

1. Deep-link URL contract with the explorer (`?a=`, hub focus).
2. Final production table/column names.
3. Subnet token design (ingest, horizon, cap, weight) when replacing ASN.
