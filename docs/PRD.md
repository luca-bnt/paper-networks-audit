# Paper Networks Audit — Product Requirements Document

> Status: draft scaffold. Fill this in as the production brief.

## 1. Summary

**Product:** Paper Networks Audit  
**Problem:** Research-integrity reviewers need to find and investigate clusters of manuscripts that share suspicious connection attributes (IP, email, device, Word metadata, etc.).  
**Outcome:** A production-ready tool that replaces the current static prototype with supported auth, durable workflow state, and maintainable deployment.

## 2. Goals

- [ ] …
- [ ] …
- [ ] …

## 3. Non-goals

- …

## 4. Users & stakeholders

| Role | Needs |
|------|-------|
| Integrity reviewer | … |
| Manager / lead | … |
| Platform eng | … |

## 5. Current prototype (baseline)

- Live static app: https://network-analysis.temporary-static-webapp.frontiersin.net/
- Source: `audit-network/`
- Demo video composition: `audit-network-demo/`
- Data: gzipped snapshot from `service-aira` via `audit_snapshot.py`
- Collaboration state: Azure Table–backed flags / seen / checked / resolved (prototype)

## 6. Functional requirements

### 6.1 Discovery & clustering
…

### 6.2 Compare & investigation
…

### 6.3 Team tracking & flags
…

### 6.4 Export & audit trail
…

### 6.5 Shareable state
…

## 7. Non-functional requirements

| Area | Requirement |
|------|-------------|
| Auth | … |
| Performance | … |
| Privacy / retention | … |
| Accessibility | … |
| Observability | … |

## 8. Open questions

See [open-questions.md](./open-questions.md).

## 9. Success metrics

- …
