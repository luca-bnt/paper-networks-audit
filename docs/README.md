# Paper Networks Audit — product docs

This folder is the home for production planning and handover documents.

## Explorer product (Paper Networks Audit)

| Document | Status | Purpose |
|----------|--------|---------|
| [PRD.md](./PRD.md) | Planned | Product requirements for the Networks Audit explorer |
| [architecture.md](./architecture.md) | Planned | System design, data flow, hosting, auth |
| [data-model.md](./data-model.md) | Planned | Snapshot schema, flags store, tracking model |
| [ux-spec.md](./ux-spec.md) | Planned | Flows, states, and Brink/Lasagna UI requirements |
| [open-questions.md](./open-questions.md) | Planned | Decisions still needed before build |

## AIRA checks (in-review)

| Document | Status | Purpose |
|----------|--------|---------|
| [aira-checks/README.md](./aira-checks/README.md) | Active | Index: explorer vs AIRA-check docs |
| [aira-checks/cluster-analysis-prd-outline.md](./aira-checks/cluster-analysis-prd-outline.md) | Outline | Cluster Analysis check — UX skeleton + scoring decision checklist |

## Prototype reference (not production code)

- App: [`../audit-network/`](../audit-network/)
- Demo video: [`../audit-network-demo/`](../audit-network-demo/)
- Snapshot pipeline: [`../audit_snapshot.py`](../audit_snapshot.py)
