# Cluster Analysis (AIRA check)

In-review check. Replaces fingerprinting / metadata-analysis.  
Outcomes: **BLOCK** or **PASS** (AIRA standard — no soft severities).

## UI


| Block         | Content                                                                            |
| ------------- | ---------------------------------------------------------------------------------- |
| Header        | BLOCK when raised                                                                  |
| Identity      | Author, email, name/email similarity, matches WD author Y/N                        |
| File metadata | WD author, company, last modified by, editing time / revisions                     |
| Matches (90d) | Article id · date · status, affiliation, match chips, locale                       |
| CTA           | Open cluster investigation for this article (deep-link with article + hub context) |


**Match chips**


| Chip           | Field                           |
| -------------- | ------------------------------- |
| Network        | `ip`                            |
| Device         | `device` (see definition below) |
| Doc properties | `wdAuthor`, `wdEditedBy`        |
| Locale         | `locale`                        |


Affiliation is display-only (not a connective field).

---



## Connective fields (90-day window)

Only these fields form hubs for this check: `ip`, `device`, `locale`, `wdAuthor`, `wdEditedBy`.  
Do **not** use `email`, `wdCompany`, or `authorIp`.


| Field                    | Source / derivation                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ip`                     | Latest `DeviceFingerprints.IpHash`, truncated to 16 hex                                                                                                                                                                                                                                                                                                                                                          |
| `device`                 | **Device profile id** (not legacy `DeviceId` alone). SHA-256 of pipe-joined: `CanvasHash | WebglHash | HwIdHash | UaFamilyHash | Platform | {ScreenWidth}x{ScreenHeight} | DevicePixelRatio`. Digest truncated to 16 hex for the hub key. All components come from the latest `DeviceFingerprints` row. Empty / non-64-hex profiles are discarded (no fallback to bare `DeviceId`). Spec: `device_profile_id.py` |
| `locale`                 | `{Languages}|{Timezone}` from the same fingerprint row                                                                                                                                                                                                                                                                                                                                                           |
| `wdAuthor`, `wdEditedBy` | Parsed from indicator definition **75** (Word doc properties). Generic values dropped via `GENERIC_WD` stoplist                                                                                                                                                                                                                                                                                                  |


A **hub** = articles sharing the same non-empty value for one field, size between 5 and the field cap (`ip`/`device`: 120; `wd*`: 40; `locale`: 25).

---

## Attached filters (fixed preset)

Same meaning as the explorer filters below. A hub is **kept** for the subject only if **all** hold; otherwise the subject is **excluded** from that hub for this check.

**Connection types in scope:** `ip`, `device`, `locale`, `wdAuthor`, `wdEditedBy` (not `email`, not `wdCompany`).

| Filter | Rule |
| ------ | ---- |
| Different submitting authors | Hub has ≥ 2 distinct submitting authors |
| Different organisations | Hub has ≥ 2 distinct organisations |
| Author dominance | Subject’s submitting author appears on **≤ 50%** of hub members. If share **> 50%**, discard the hub for this subject |
| Window / size | 90-day window; hub size within field min…cap |

`locale` hubs may appear on the card (chips / matches) but **do not** satisfy the network/device half of B1.

---

## Outcomes

### BLOCK — any of the following

**B0 — Not excluded by attached filters**  
Subject belongs to **at least one** hub that passes the attached filters above (including author share ≤ 50%).  
If every candidate hub is discarded by those filters, B0 does not fire.

**B1 — Flagged peer**  
Exists peer `P` that is **integrity-flagged**, and subject shares with `P`:

- `(ip OR device)` **and** `(wdAuthor OR wdEditedBy)`  

on hubs that pass the attached filters.

**B2 — Word document properties**  
The existing standalone Word-document-properties check already returned **BLOCK** for this article.

### PASS

None of B0, B1, B2.

---

## Evaluator

```
inputs:  article A, hub store S (90d), flag set F, wdPropsOutcome(A)
output:  BLOCK | PASS, card payload, deep-link

1. If no record for A → PASS (or N/A per platform convention).
2. If wdPropsOutcome(A) == BLOCK → BLOCK (B2).
3. Collect hubs for A on {ip, device, locale, wdAuthor, wdEditedBy}.
4. Keep only hubs that pass attached filters
   (nAuthors≥2, nOrgs≥2, authorShare(A)≤0.5, size/caps/window).
5. If any hub remains → BLOCK (B0).
6. For each flagged peer P in remaining hubs:
     if shares(A,P,{ip,device}) and shares(A,P,{wdAuthor,wdEditedBy}) → BLOCK (B1).
7. Else if not already BLOCK → PASS.
8. On BLOCK: card fields above; chips = shared fields with each listed peer;
   deep-link focuses A and the strongest evidence hub
   (prefer larger hub; then device > ip > wdAuthor > wdEditedBy > locale).
```

---



## Data plane

### Refresh

- **Cadence:** daily (full rebuild of the trailing **90-day** window).
- Fingerprints and WD indicators often arrive after article `Created` — daily rebuild re-derives fields for recent articles, not only newly created ones.
- Persist `builtUtc` on each run; evaluator/ops can detect stale data if lag &gt; 24h.

### What to store

Three logical datasets (SQL or equivalent). Only articles that appear in at least one kept hub need to be queryable for clustering; card display fields should still be available for the subject article when the check runs.

**1. `cluster_articles`** — one row per article in the window (or at least every connected article)

| Column | Purpose |
| ------ | ------- |
| `article_id` | PK |
| `created_date` | Window / display |
| `author_name`, `author_email`, `author_org` | Hub filters, card Identity, author-share |
| `status`, `journal`, `section` | Card Matches |
| `ip`, `device`, `locale`, `wd_author`, `wd_edited_by` | Connective values (empty = absent) |
| `wd_company`, `wd_match`, `name_email_sim` | Card File metadata / Identity (not hubs) |
| `title` (optional, truncated) | Display |

**2. `cluster_hubs`** — one row per kept `(field, value)` bucket

| Column | Purpose |
| ------ | ------- |
| `field` | One of `ip`, `device`, `locale`, `wdAuthor`, `wdEditedBy` |
| `value` | Exact connective string (or stable hash of it if values are large) |
| `article_ids` | Member list (array / join table) |
| `n_authors`, `n_orgs` | Precomputed distinct counts for hub filters |
| `size` | Member count (must respect min size + field cap) |

Unique on `(field, value)`. Drop hubs outside `min_size…cap` at build time so the evaluator does not re-apply caps.

**3. `cluster_flags`** — active integrity flags for B1

| Column | Purpose |
| ------ | ------- |
| `article_id` | PK of flagged article |
| `flagged_utc`, `flagged_by` (optional) | Audit |

Only **active** flags; removals delete or tombstone so B1 no longer sees them.

### How to store / access

- Prefer **relational tables** (or Cosmos/SQL equivalent) owned by the AIRA data plane — not a static file scrape.
- **Indexes:** `cluster_articles(article_id)`; for each connective column a secondary index or inverted access via `cluster_hubs(field, value)`; `cluster_hubs` member lookup by `article_id` (join table `cluster_hub_members(hub_id, article_id)` is fine if arrays are awkward).
- **Build job (daily):** pull sources → derive fields (`device_profile_id`, WD parse, caps, `GENERIC_WD`) → replace `cluster_articles` + `cluster_hubs` for the window (transactional swap or versioned `snapshot_id`) → refresh `cluster_flags` from the flag store → set `builtUtc`.
- **Check read path:** load article row by id → resolve hubs via member index → apply hub filters + B1/B2. O(hubs for A), not a full scan.
- **Sources:** `DeviceFingerprints`; Indicator **75** (WD props); article author/org/status/title from warehouse. Reference field math: `device_profile_id.py`, `audit_snapshot.py` (`build` / `parse_worddoc` / caps).

---

## Delivery

Thin Jira trackers (QM): [QM-2480](https://jira.frontiersin.net/browse/QM-2480) — this PRD is the source of truth. Two vertical slices (tests/rollout folded in):

1. `[Cluster Analysis] Daily hub store + BLOCK/PASS engine` — [QM-2481](https://jira.frontiersin.net/browse/QM-2481)  
2. `[Cluster Analysis] In-review card, deep-link, and cutover` — [QM-2482](https://jira.frontiersin.net/browse/QM-2482)

