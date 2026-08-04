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

## Storage and lookup scope

| Layer | Policy |
|-------|--------|
| **Storage** | Keep **all** `submission_features` and `feature_lookup` rows indefinitely (for analytics and offline eval). Never purge on age. |
| **Check lookup** | Matches against **flagged articles only**, with **no recency window**. A flagged manuscript is surfaced however long ago it was submitted. |

There is deliberately no time limit on flagged matches: an integrity flag does not expire, and a papermill network that resurfaces after a year is exactly what this check exists to catch. Age is used for ranking (time proximity) and display, never to exclude.

## Reviewer UI

| Block | Content |
|-------|---------|
| Header | Outcome (`BLOCK`) when raised |
| Identity | Author, email, name/email similarity, WD author matches submitting author Y/N |
| File metadata | WD author, company, last modified by |
| Flagged Article Matches | Ranked **B1 matches** (see below): article id, date, status, affiliation, score, chips |
| CTA | Open cluster explorer focused on this article (`?a=` + strongest hub) |

Section heading in the card: **Flagged Article Matches** (no sub-caption — the heading carries the meaning). Every row is a manuscript that is **flagged for integrity** *and* meets the [B1 pattern](#outcomes), from any submission date. Flagged papers matching only weakly (e.g. `locale` alone) are not listed, and unflagged peers are never retrieved. The section is therefore empty whenever the article is not a B1 — including a B2-only BLOCK. No per-row “flagged” marker is needed, since every row is flagged by definition.

**Chips:** Device · Network (IP) · Network proximity (subnet without same IP, when enabled) · Doc properties · Locale · Time proximity · Conflicting affiliations  

**Matches list behaviour**

| Field / behaviour | Spec |
|-------------------|------|
| `match_total` | Count of **all** B1 matches, any submission date (not capped). Show this total in the UI. |
| Hydrated / listed peers | Top **`K`** by score (full feature rows + chips). |
| Default visible | Top **5** of those `K`. |
| Show more | Remaining listed peers behind a control. Follow existing AIRA patterns (e.g. **Scope check**): “{N} more results” / show-more, not a bespoke control. |
| If `match_total` > `K` | Still only list top `K` details; the total label reflects the full count (e.g. showing `K` of {match_total}). |

### Short outcome description (card header copy)

One line under the outcome. `{X}` = **`match_total`** (singular “paper” if `{X}=1`). Since the list only ever holds B1 matches, the sentence and the list always agree on the same number. No time qualifier in the copy — the match set is not bounded by one.

| Outcome | Template |
|---------|----------|
| **B1** | This manuscript shares {network_phrase} and {file_phrase} with {X} flagged paper(s) |
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
| **B1** | Exists an **integrity-flagged** peer — of any age — sharing `(ip ∨ device)` **and** `(wd_author ∨ wd_edited_by)` with the subject |
| **B2** | Word document properties check **C1G27I3** already returned BLOCK for this article |

`locale` and network-proximity tokens (`asn` / future `subnet`) never satisfy the network half of B1.

### PASS

Not B1 and not B2. A flagged paper that matches only weakly (e.g. shares only `device`) neither blocks nor appears on the card.

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
| `is_flagged`, `flagged_utc`, `flagged_by` | From the new flags table (see below); active flags only; cleared on unflag; drives B1. `flagged_utc` is for display and audit — it never limits matching |
| `updated_utc` | Late fingerprint / indicator enrichment |

### `feature_lookup` — one row per searchable token

| Column | Purpose |
|--------|---------|
| `feature_type`, `feature_value` | Token key |
| `article_id`, `created_utc` | Match target + horizon filter at query time |

**Indexes:** `(feature_type, feature_value, created_utc)` including `article_id`; `(article_id)` for rebuild/delete.

**Flagged-only retrieval:** the check only ever needs flagged peers, so lookups are restricted to articles where `is_flagged` is true. Flagged manuscripts are a small fraction of the corpus, which is what makes an unbounded time range affordable — the candidate set stays orders of magnitude smaller than a full-corpus lookup even with no date filter. Keep the flag denormalised on `feature_lookup` (or hold a flagged-only subset) so this is a narrow index seek rather than a large join. Unflagged rows are still written — a paper flagged later must become retrievable without a rebuild.

**Retention / windows:** See [Storage and lookup scope](#storage-and-lookup-scope). Store forever; lookups filter on flag status only, never on age.

**Write path:** Upsert when fingerprints or WD indicators arrive; daily reconcile as correctness backstop (reconcile does **not** delete aged-out rows).

**Sources:** `DeviceFingerprints`; Indicator definition **75** / check **C1G27I3** (Word doc properties); article author/org/status/title from the warehouse.

**Flags:** New dedicated table (not the prototype Azure Table long-term). The standalone network UI calls an API to flag and unflag manuscripts; those flags sync into this table and populate `is_flagged`. Requirements:

- Only **active** flags count. Unflagging must stop the paper matching, and must clear any BLOCK it was solely responsible for on re-evaluation.
- Flagging or unflagging must take effect without a rebuild or backfill of the feature tables.
- A flag applies regardless of when the paper was submitted or when the flag was raised.
- Flag identity (`flagged_by`, `flagged_utc`) is carried for display and audit only.

---

## Feature tokens

| Type | Source | Role | Cap | Weight |
|------|--------|------|-----|--------|
| `device` | [Device profile id](#device-profile-id) | decision | 120 | 10 |
| `ip` | `IpHash` truncated to 16 hex | decision | 120 | 8 |
| `wd_author` | Indicator 75; drop `GENERIC_WD` | decision | 500 | 8 |
| `wd_edited_by` | Indicator 75; drop `GENERIC_WD` | decision | 500 | 8 |
| `wd_company` | Indicator 75; drop `GENERIC_WD` | rank | 500 | 6 |
| `locale` | `{Languages}\|{Timezone}` | rank | 25 | 1 |
| `asn` | — | **off** (data unusable today) | — | — |
| `subnet` | truncated-IP / subnet hash (future ingest) | rank (planned; replaces ASN) | TBD | TBD (nested under IP when live) |

**Not indexed** (store on `submission_features` for display only): submitting `email`, `authorIp`.

**No lookup window:** every token matches flagged peers of any age. The old per-token 90-day horizon is gone.

**Caps:** If document frequency of `(type, value)` exceeds the cap, skip that token for lookup and scoring. Document frequency is counted across the **whole corpus**, not just flagged articles — a value is uninformative because it is everywhere, regardless of who carries it. Caps are now the main false-positive control: without them, one ubiquitous value shared with a single flagged paper could satisfy half of B1, and with no date filter that exposure only grows as the flag set accumulates. Word-doc caps are intentionally high: shared Author / Company / Last-modified-by across many submissions is papermill signal, not noise.

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

Score now only **orders the matches list** — no outcome or membership depends on a threshold. B1 is a structural rule: a flagged peer either fits the pattern (and is listed) or it does not (and is invisible to the check).

Sort matches by score descending, then more decision-token overlaps, then newer `created_utc`.

No `T_retrieve`: any B1 match already scores at least 20 (weakest case: `ip` 8 + `wd_edited_by` 8 + the 4-point network×doc bonus), so a retrieval floor would never exclude anything.  
`K` = max B1 matches to hydrate and list on the card (**15**, per QM-2278).  
UI default visible = **5**; remainder of the `K` list behind show-more (Scope-check pattern).

---

## Evaluator

```
inputs:  article A, feature store, flag store, C1G27I3 outcome(A)
output:  BLOCK | PASS, match_total, top-K ranked matches,
         chips, short description, deep-link

1. Normalize A → token set T.
2. One batched lookup of all tokens in T, restricted to FLAGGED articles:
     no date filter — flagged peers of any age qualify; skip over-cap values; exclude A.
3. Group hits by flagged article_id.
4. Keep only peers sharing (ip ∨ device) ∧ (wd_author ∨ wd_edited_by)  → the B1 matches.
     Discard the rest: they neither block nor display.
5. match_total = count of B1 matches (full set — do not cap this number).
6. BLOCK if match_total ≥ 1 (B1) or C1G27I3(A) == BLOCK (B2). Else PASS.
7. Take top K by score; load submission_features; apply time/affiliation; re-sort.
8. On BLOCK: short description ({X}=match_total), chips, deep-link;
     card lists top K (UI shows 5 + “N more results”).
```

A B2-only BLOCK has no B1 matches by definition, so its Matches section is empty — the card must read sensibly in that state.

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
| Storage vs lookup | **Store all history.** Lookup is filtered by **flag status only — no recency window**; flags do not expire, so an old flagged paper must still surface |
| ASN | Useless with current data; do not enable. Prefer **subnet** later |
| Deep-link URL (`?a=`, hub focus) | **TBD** |
| Production table/column names | **TBD** (logical names in this PRD stand until then) |
| Subnet token (horizon, cap, weight) | **TBD** when ingest is designed |

---

## Delivery slices (suggested)

1. Feature store (`submission_features` + `feature_lookup`, **retain all history**) + upsert/reconcile + evaluator with **flagged-only lookup, no recency window** (BLOCK/PASS) + offline replay harness.  
2. In-review card, chips, deep-link, flags API → new flags table sync, feature-flagged cutover.

Because everything now depends on the flag store, the flags API and sync are a **prerequisite for slice 1 to be testable**, not just slice 2 — with no flags there are no matches and the check always passes.
