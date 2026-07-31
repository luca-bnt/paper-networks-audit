# Cluster Analysis — AIRA in-review check

**Status:** Ready for implementation  
**Surface:** AIRA in-review check (replaces fingerprinting / metadata-analysis for this use case)  
**Outcomes:** `BLOCK` | `PASS`

Checks whether an incoming submission shares device, network or Word-file metadata with manuscripts already **flagged for integrity**. Raises BLOCK when it does, and lists the flagged matches as evidence.

Reference field math in this repo: [`device_profile_id.py`](../../device_profile_id.py), [`audit_snapshot.py`](../../audit_snapshot.py) (`build`, `parse_worddoc`, `GENERIC_WD`, caps).

---

## Goals

- For every incoming article, find prior **flagged** submissions that share its features.
- Explain each match with clear evidence chips (device, IP, doc props, etc.).
- **BLOCK** on a flagged match that meets the rules below; otherwise **PASS**.
- Keep Word-document property reuse as a first-class papermill signal (large shared hubs are intentional signal).

## Non-goals

- Replacing the network explorer UI (deep-link only).
- Using submitting email or author-declared IP as lookup tokens (display only).
- Treating the feature store as a rolling 90-day window that drops older rows.
- Surfacing clusters among **unflagged** submissions — that is the explorer's job, not this check's.

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
| Header | Outcome (`BLOCK`) when raised |
| Identity | Author, email, name/email similarity, WD author matches submitting author Y/N |
| File metadata | WD author, company, last modified by |
| Matches | Ranked **flagged** peers (see below): article id, date, status, affiliation, score, chips, tier |
| CTA | Open cluster explorer focused on this article (`?a=` + strongest hub) |

Every match on the card is a manuscript already flagged for integrity — the check does not retrieve unflagged peers.

**Chips:** Device · Network (IP) · Network proximity (subnet without same IP, when enabled) · Doc properties · Locale · Time proximity · Conflicting affiliations  

**Match tiers:** `block_evidence` (meets the B1 pattern) | `context` (flagged match that does not)

**Matches list behaviour**

| Field / behaviour | Spec |
|-------------------|------|
| `match_total` | Count of **all** flagged peers with score ≥ `T_retrieve` in the 90-day window (not capped). Show this total in the UI. |
| `block_matches` | Subset of those that meet the B1 pattern. Drives the B1 copy — see below. |
| Hydrated / listed peers | Top **`K`** by tier then score (full feature rows + chips). |
| Default visible | Top **5** of those `K`. |
| Show more | Remaining listed peers behind a control. Follow existing AIRA patterns (e.g. **Scope check**): “{N} more results” / show-more, not a bespoke control. |
| If `match_total` > `K` | Still only list top `K` details; the total label reflects the full count (e.g. showing `K` of {match_total}). |

### Short outcome description (card header copy)

One line under the outcome. `{X}` = **`block_matches`** (flagged papers meeting the B1 pattern; singular “paper” if `{X}=1`). Using `block_matches` rather than `match_total` keeps the sentence true: a flagged peer sharing only `locale` must not be counted as one that “shares device and file metadata”.

| Outcome | Template |
|---------|----------|
| **B1** | Shares {network_phrase} and {file_phrase} with {X} flagged paper(s) in the last 90 days |
| **B2** | Has file metadata that was previously flagged |

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

If both BLOCK reasons fire, primary copy order: **B1 > B2**.

---

## Outcomes

### BLOCK — either of

| Code | Rule |
|------|------|
| **B1** | Exists an **integrity-flagged** peer, submitted in the last 90 days, sharing `(ip ∨ device)` **and** `(wd_author ∨ wd_edited_by)` with the subject |
| **B2** | Word document properties check **C1G27I3** already returned BLOCK for this article |

`locale` and network-proximity tokens (`asn` / future `subnet`) never satisfy the network half of B1.

### PASS

Not B1 and not B2. A flagged match that does not meet the B1 pattern (e.g. shares only `device`) is still **listed on the card**, but does not by itself block.

Codes `B1` / `B2` keep their names for continuity with tickets and existing dev conversations; there is no longer a `B0`.

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

**Flagged-only retrieval:** the check only ever needs flagged peers, so lookups are restricted to articles where `is_flagged` is true. Flagged manuscripts are a small fraction of the corpus, which makes the candidate set orders of magnitude smaller than a full-corpus lookup. Keep the flag denormalised on `feature_lookup` (or hold a flagged-only subset) so this is a narrow index seek rather than a large join. Unflagged rows are still written — a paper flagged later must become retrievable without a rebuild.

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

**Caps:** If document frequency of `(type, value)` exceeds the cap, skip that token for lookup and scoring. Document frequency is counted across the **whole corpus**, not just flagged articles — a value is uninformative because it is everywhere, regardless of who carries it. With flagged-only retrieval the caps matter less for fanout and more as false-positive control: without them, one ubiquitous value shared with a single flagged paper could satisfy half of B1. Word-doc caps are intentionally high: shared Author / Company / Last-modified-by across many submissions is papermill signal, not noise.

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

Score now only **orders the matches list** — no outcome depends on a threshold. B1 is a structural rule, so a match either fits the pattern or it does not.

Sort matches by `block_evidence` tier first, then score descending, then more decision-token overlaps, then newer `created_utc`.

`T_retrieve` = **3** (minimum score for a flagged peer to be listed at all).  
`K` = max flagged peers to hydrate and list on the card (**15**, per QM-2278).  
UI default visible = **5**; remainder of the `K` list behind show-more (Scope-check pattern).

---

## Evaluator

```
inputs:  article A, feature store, flag store, C1G27I3 outcome(A)
output:  BLOCK | PASS, match_total, block_matches, top-K ranked matches,
         chips, short description, deep-link

1. Normalize A → token set T.
2. One batched lookup of all tokens in T, restricted to FLAGGED articles:
     keep only peers with created_utc within the last 90 days; skip over-cap values; exclude A.
3. Group hits by flagged article_id; score; keep score ≥ T_retrieve.
4. match_total = count of those flagged peers (full set — do not cap this number).
5. Mark each peer block_evidence if it shares (ip ∨ device) ∧ (wd_author ∨ wd_edited_by);
     block_matches = count of those.
6. BLOCK if block_matches ≥ 1 (B1) or C1G27I3(A) == BLOCK (B2). Else PASS.
7. Take top K by tier then score; load submission_features; apply time/affiliation; re-sort.
8. On BLOCK: short description ({X}=block_matches), chips, deep-link;
     card lists top K (UI shows 5 + “N more results”).
9. On PASS: attach matches if any were found, as context.
```

B2 no longer short-circuits the lookup: an article blocked by C1G27I3 should still show its flagged matches when it has them.

---

## Operations

| Topic | Expectation |
|-------|-------------|
| Freshness | Upsert on enrich; daily reconcile; expose `builtUtc` / lag for ops |
| Flag propagation | A newly flagged manuscript must become retrievable promptly; track lag from flag to first BLOCK it causes |
| Monitoring | Lookup latency, cap-skip rate, BLOCK/PASS rates, enrich lag, share of BLOCKs from B1 vs B2 |
| Offline eval | Replay against history: BLOCK rate, B1 precision (sample flagged matches for plausibility), and how many BLOCKs come from a single flagged peer |
| Network proximity | ASN off; prefer **subnet** hash once ingest exists (nested under IP for scoring) |
| Cutover | Feature-flag the check; shadow (log-only) then enable BLOCK |

---

## Decisions

| Topic | Decision |
|-------|----------|
| Severities | `BLOCK` / `PASS`. WARN removed — a score-based warning tier produced too many low-value hits to be actionable |
| B0 removed | Multi-signal clustering among unflagged papers no longer blocks; it stays an explorer/analytics concern |
| Attached filters removed | They existed to prove a hub was a real network before B0/WARN could fire. B1 is a direct match against an already-flagged paper, so hub credibility is not the question any more |
| Retrieval scope | **Flagged papers only** — the only outcome that depends on peers is B1 |
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

1. Feature store (`submission_features` + `feature_lookup`, **retain all history**) + upsert/reconcile + evaluator with **flagged-only, 90-day lookup** (BLOCK/PASS) + offline replay harness.  
2. In-review card, chips, deep-link, flags API → new flags table sync, feature-flagged cutover.

Because everything now depends on the flag store, the flags API and sync are a **prerequisite for slice 1 to be testable**, not just slice 2 — with no flags there are no matches and the check always passes.
