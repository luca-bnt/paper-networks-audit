# Paper Networks Audit — product docs

This folder is the home for production planning and handover documents.

## AIRA checks (in-review)

| Document | Status | Purpose |
|----------|--------|---------|
| [aira-checks/README.md](./aira-checks/README.md) | Active | Index of AIRA-check docs |
| [aira-checks/cluster-analysis-prd.md](./aira-checks/cluster-analysis-prd.md) | Ready for implementation | Cluster Analysis in-review check (BLOCK / WARN / PASS) |

## Explorer (prototype notes)

| Document | Status | Purpose |
|----------|--------|---------|
| [architecture.md](./architecture.md) | Planned | System design, data flow, hosting, auth |

Planned-but-absent stubs (`data-model.md`, `ux-spec.md`) are not linked until they exist. Open decisions for Cluster Analysis live in the PRD.

## Prototype reference (not production code)

- App: [`../audit-network/`](../audit-network/)
- Demo video: [`../audit-network-demo/`](../audit-network-demo/)
- Snapshot pipeline: [`../audit_snapshot.py`](../audit_snapshot.py)
