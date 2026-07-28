# Cluster Analysis — AIRA in-review check

**Status:** Ready for implementation  
**Surface:** AIRA in-review check (replaces fingerprinting / metadata-analysis for this use case)  
**Outcomes:** `BLOCK` | `WARN` | `PASS`

Finds prior submissions that share identity, network, or document-metadata features with the subject article; ranks them for the reviewer; raises BLOCK or WARN when evidence meets the rules below.

Reference field math in this repo: [`device_profile_id.py`](../../device_profile_id.py), [`audit_snapshot.py`](../../audit_snapshot.py) (`build`, `parse_worddoc`, `GENERIC_WD`, caps). Offline rate checks: [`simulate_cluster_check.py`](../../simulate_cluster_check.py).

---

## Goals

- Retrieve a small set of similar prior submissions for every incoming article.
- Explain matches with clear evidence chips (device, IP, doc props, etc.).
- **BLOCK** on strong multi-signal or flagged-peer patterns; **WARN** when similarity score is high but BLOCK rules are not met; otherwise **PASS**.
- Keep Word-document property reuse as a first-class papermill signal (large shared hubs are intentional signal).

## Non-goals

- Replacing the network explorer UI (deep-link only).
- Using submitting email or author-declared IP as lookup tokens (display only).
- Treating the feature store as a rolling 90-day window that drops older rows.

---

## Storage vs lookup window

| Layer | Policy |
|-------|--------|
| **Storage** | Keep **all** `submission_features` and `feature_lookup` rows indefinitely (for analytics and offline eval). Do **not** purge when data ages past 90 days. |
| **Check lookup** | Operational matching for this AIRA check uses only peers from the last **90 days (3 months)**, applied as a `created_utc` filter at query time. |

Analytics jobs may query beyond 90 days; the in-review evaluator must not.

## Reviewer UI

| Block | Content |
|-------|---------|
| Header | Outcome (`BLOCK` / `WARN`) when raised |
| Identity | Author, email, name/email similarity, WD author matches submitting author Y/N |
| File metadata | WD author, company, last modified by |
| Matches | Ranked peers: article id, date, status, affiliation, score, chips, tier |
| CTA | Open cluster explorer focused on this article (`?a=` + strongest hub) |

**Chips:** Device · Network (IP) · Network proximity (subnet without same IP, when enabled) · Doc properties · Locale · Time proximity · Conflicting affiliations  

**Match tiers:** `block_evidence` | `warn` | `context` (show `context` only when the article outcome is BLOCK or WARN)

### Short outcome description (card header copy)

One line under the outcome. `{X}` = distinct peers in the 90-day evidence set (singular “paper” if `{X}=1`).

| Outcome | Template |
|---------|----------|
| **B0** | Shares device, network and file metadata with {X} other paper(s) in the last 90 days |
| **B1** | Shares {network_phrase} and {file_phrase} with {X} flagged paper(s) in the last 90 days |
| **B2** | Has file metadata that was previously flagged |
| **WARN** | Shares {feature_list} with {X} other paper(s) in the last 90 days |

**B1 — `{network_phrase}`** (`device` / `ip` on flagged-peer evidence):

| Matched | Phrase |
|---------|--------|
| device only | device |
| ip only | network |
| both | device and network |

**B1 — `{file_phrase}`** (`wd_author` / `wd_edited_by`):

| Matched | Phrase |
|---------|--------|
| exactly one | some file metadata |
| both | file metadata |

**B1 combinations:**

1. device and some file metadata  
2. device and file metadata  
3. network and some file metadata  
4. network and file metadata  
5. device and network and some file metadata  
6. device and network and file metadata  

**WARN — `{feature_list}`:** matched labels among WARN peers, joined with commas and “and”:

| Signal | Label |
|--------|-------|
| device | device |
| ip | network |
| subnet (no same ip) | network proximity |
| exactly one of wd_author / wd_edited_by (or wd_company only) | some file metadata |
| both wd_author and wd_edited_by | file metadata |
| locale | locale |
| time proximity | time proximity |
| conflicting affiliations | conflicting affiliations |

If several BLOCK reasons fire, primary copy order: **B1 > B0 > B2**.

---

## Outcomes

### BLOCK — any of

| Code | Rule |
|------|------|
| **B0** | Subject shares **all four** decision tokens (`device` ∧ `ip` ∧ `wd_author` ∧ `wd_edited_by`), each in a peer set that passes [attached filters](#attached-filters-block-only) |
| **B1** | Exists an **integrity-flagged** peer that shares `(ip ∨ device)` **and** `(wd_author ∨ wd_edited_by)` on filter-passing evidence |
| **B2** | Word document properties check **C1G27I3** already returned BLOCK for this article |

### WARN

Not BLOCK, and max peer [score](#scoring) ≥ `T_warn` (**34**).

### PASS

Neither BLOCK nor WARN.

---

## Attached filters (BLOCK only)

A peer set (hub) for a decision token is usable for B0/B1 only if **all** hold:

| Filter | Rule |
|--------|------|
| Size | Between **5** and the token [cap](#feature-tokens) (inclusive) |
| Window | Members within the last **90 days (3 months)** |
| Authors | ≥ 2 distinct submitting authors |
| Organisations | ≥ 2 distinct organisations |
| Author dominance | Subject’s submitting author appears on ≤ **50%** of members |

`locale` and network-proximity tokens (`asn` / future `subnet`) never satisfy the network half of B1.

---

## Data plane

### `submission_features` — one row per article

| Column | Purpose |
|--------|---------|
| `article_id` | PK |
| `created_utc` | Windows, time boost, analytics |
| `author_name`, `author_email`, `author_org` | Filters, card, affiliation adjust |
| `status`, `journal`, `section`, `title` | Display (title may be truncated) |
| `ip_hash`, `device_profile_id`, `asn_hash`, `locale` | Connective values |
| `wd_author`, `wd_edited_by`, `wd_company`, `wd_match` | Doc props |
| `name_email_sim` | Display |
| `is_flagged`, `flagged_utc`, `flagged_by` | From the new flags table (see below); active only; cleared on unflag; drives B1 |
| `updated_utc` | Late fingerprint / indicator enrichment |

### `feature_lookup` — one row per searchable token

| Column | Purpose |
|--------|---------|
| `feature_type`, `feature_value` | Token key |
| `article_id`, `created_utc` | Match target + horizon filter at query time |

**Indexes:** `(feature_type, feature_value, created_utc)` including `article_id`; `(article_id)` for rebuild/delete.

**Retention / windows:** See [Storage vs lookup window](#storage-vs-lookup-window). Store forever; filter lookups to 90 days.

**Write path:** Upsert when fingerprints or WD indicators arrive; daily reconcile as correctness backstop (reconcile does **not** delete aged-out rows).

**Sources:** `DeviceFingerprints`; Indicator definition **75** / check **C1G27I3** (Word doc properties); article author/org/status/title from the warehouse.

**Flags:** New dedicated table (not the prototype Azure Table long-term). The standalone network UI will call an API to flag manuscripts; those flags sync into this table and populate `is_flagged` for B1.

---

## Feature tokens

| Type | Source | Role | Lookup window | Cap | Weight |
|------|--------|------|---------------|-----|--------|
| `device` | [Device profile id](#device-profile-id) | decision | 90d | 120 | 10 |
| `ip` | `IpHash` truncated to 16 hex | decision | 90d | 120 | 8 |
| `wd_author` | Indicator 75; drop `GENERIC_WD` | decision | 90d | 500 | 8 |
| `wd_edited_by` | Indicator 75; drop `GENERIC_WD` | decision | 90d | 500 | 8 |
| `wd_company` | Indicator 75; drop `GENERIC_WD` | rank | 90d | 500 | 6 |
| `locale` | `{Languages}\|{Timezone}` | rank | 90d | 25 | 1 |
| `asn` | — | **off** (data unusable today) | — | — | — |
| `subnet` | truncated-IP / subnet hash (future ingest) | rank (planned; replaces ASN) | TBD | TBD | TBD (nested under IP when live) |

**Not indexed** (store on `submission_features` for display only): submitting `email`, `authorIp`.

**Lookup window:** All tokens used by this check are matched against peers from the last **90 days (3 months)** only. Rows older than that remain in the tables for analytics.

**Caps:** If document frequency of `(type, value)` exceeds the cap, skip that token for lookup and scoring (fanout control). Word-doc caps are intentionally high: shared Author / Company / Last-modified-by across many submissions is papermill signal, not noise.

**`GENERIC_WD`:** Stoplist for OS and auto-tooling placeholders only (e.g. `administrator`, `microsoft office user`, `python-docx`, `un-named`). Do **not** stoplist publisher or organisation-like strings.

### Device profile id

From the latest `DeviceFingerprints` row (not bare `DeviceId`):

```
SHA-256(
  CanvasHash | WebglHash | HwIdHash | UaFamilyHash
  | Platform | {ScreenWidth}x{ScreenHeight} | DevicePixelRatio
)
```

Require a full 64-hex digest; discard empty or incomplete profiles. Store and match on the first **16** hex characters.

### Scoring

```
network = 8 if same ip else (proximity_weight if same subnet when enabled else 0)

score = network
      + Σ weight[t] for other matched types
      + time_boost          # +1 if |Δt| ≤ 7d; +0.5 if ≤ 30d; else 0
      + affiliation_adjust  # +2 if orgs differ and ≥1 decision token shared;
                            # −2 if same org and shared device or ip
      + 4 if (device ∨ ip) ∧ (wd_author ∨ wd_edited_by)
```

Sort matches by score descending, then more decision-token overlaps, then newer `created_utc`.

`T_retrieve` = **3** (minimum score to keep a peer).  
`T_warn` = **34**.  
`K` = **20** (peers to hydrate with full `submission_features` for the card; UI may show fewer).

---

## Evaluator

```
inputs:  article A, feature store, flag store, C1G27I3 outcome(A)
output:  BLOCK | WARN | PASS, ranked matches, chips, deep-link

1. Normalize A → token set T.
2. If C1G27I3(A) == BLOCK → article BLOCK (B2); still attach matches if any.
3. One batched lookup of all tokens in T:
     keep only peers with created_utc within the last 90 days; skip over-cap values; exclude A.
4. Group hits by prior article_id; score; keep score ≥ T_retrieve; take top K.
5. Load submission_features for top K; apply time/affiliation; re-sort.
6. BLOCK if B0, B1, or B2 (definitions above).
7. Else WARN if max peer score ≥ T_warn.
8. Else PASS.
9. On BLOCK/WARN: populate card; chips from matched tokens; deep-link to explorer.
```

---

## Operations

| Topic | Expectation |
|-------|-------------|
| Freshness | Upsert on enrich; daily reconcile; expose `builtUtc` / lag for ops |
| Monitoring | Lookup latency, fanout, cap-skip rate, BLOCK/WARN/PASS rates, enrich lag |
| Offline eval | Before tightening thresholds: BLOCK agreement vs prior hub logic; WARN false-positive sample; flagged-peer precision@K |
| Network proximity | ASN off; prefer **subnet** hash once ingest exists (nested under IP for scoring) |
| Cutover | Feature-flag the check; shadow (log-only) then enable WARN/BLOCK |

---

## Decisions

| Topic | Decision |
|-------|----------|
| Severities | `BLOCK` / `WARN` / `PASS` confirmed supported on the target platform |
| Check registration & result contract | Confirmed |
| Flags | **New table.** Network UI flags manuscripts via an API; sync into that table → `is_flagged` for B1 |
| B2 | Word document properties check **C1G27I3** |
| Storage vs lookup | **Store all history** (no 90-day purge). **Lookup = last 90 days (3 months)** for the in-review check |
| ASN | Useless with current data; do not enable. Prefer **subnet** later |
| Deep-link URL (`?a=`, hub focus) | **TBD** |
| Production table/column names | **TBD** (logical names in this PRD stand until then) |
| Subnet token (horizon, cap, weight) | **TBD** when ingest is designed |

---

## Delivery slices (suggested)

1. Feature store (`submission_features` + `feature_lookup`, **retain all history**) + upsert/reconcile + evaluator with **90-day lookup filter** (BLOCK/WARN/PASS) + offline simulation harness.  
2. In-review card, chips, deep-link, flags API → new flags table sync, feature-flagged cutover.
