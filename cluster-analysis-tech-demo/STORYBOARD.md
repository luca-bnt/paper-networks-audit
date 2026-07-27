---
format: 1920x1080
message: "Papermills scale by repeating themselves — Cluster Analysis turns that repetition into the thing that catches them, at the cost of a single-paper check"
arc: Hook → Wrong model → The trick → Fingerprint → Keys → Ceiling → Shortlist → Math → Measured → Judgement → Block → Warn → Close → Outro
audience: integrity specialists and engineers — technical, but nobody should feel locked out
mode: collaborative
runtime: 205s · 14 frames · narrated (Kokoro af_heart 0.6 / af_nicole 0.4) over a music bed
---

## Layout system

Content sits on the background. A panel is an exception that has to earn itself, not the default
container — the title slide is the only frame that keeps its original treatment.

- **Structure comes from type scale and hairlines**, not borders. Vertical rules run to 62% height so
  they separate content instead of outlining empty space.
- **Type scale:** `.title` 68 · `.md` 64 · `.sm` 40 · `.lead` 26 · `.note` 18 · `.eyebrow` 14 (uppercase, tracked).
  Hero numbers use `.lg` 128 and `.xl` 176, pushed to 210 where a number is the entire point (frame 5).
- **One hero per frame.** Everything else steps down hard — a 176px number next to 18px support copy
  reads instantly; two 60px elements fight.
- **Negative space is deliberate**, roughly a third of the frame, held below the content band so the
  eye lands on the headline first.
- Accents stay rationed: cyan `#7ee8ff` for the answer, coral `#ff7b9c` for the expensive alternative,
  mint `#9dffb8` for a measured win, violet `#c4b5ff` for warn.

## Voice

Tight, concrete, a little dry. Every technical term gets one plain sentence before it's used
again. Humour is deadpan and never at a person's expense — the joke is always about scale or
about how obvious the trick is in hindsight. Numbers are the argument; adjectives are not.
Never say clever, breakthrough, revolutionary, leap, or game-changer.

Full narration reads as one continuous script — see `voiceover` per frame, in order.

## Frame 0 — Title

- status: animated
- src: compositions/frames/00-title.html
- duration: 15.4s (starts 0s)
- poster: 0.5s
- transition_in: cut
- scene: Cluster Analysis — title
- voiceover: Hi. [[0.85]] Let's take a look at how AIRA's Cluster Analysis works. [[0.70]] Papermills don't submit one paper. They submit hundreds, often from the same laptop. This is the check that notices.
- narrativeRole: open
- blueprint: kinetic-title

Locked — do not restyle. The title and outro carry the Frontiers lockup inside the slide;
the **Frontiers logo | AIRA · Cluster Analysis** bar rides the twelve interior frames only,
so the two bookends never show two logos at once.

The greeting is deliberately broken into three spoken segments with silence held between
them: **"Hi."** — 0.85s — **"Let's take a look at how AIRA's Cluster Analysis works."** —
0.70s — then the papermill lines. Punctuation alone will not buy this; Kokoro gives a period
about 0.2s, which reads as ordinary sentence rhythm rather than an intentional beat, so the
segments are synthesised separately, trimmed to their speech, and joined with explicit
silence.

The first pause is placed to coincide with the title words landing (~1.1-2.4s), so the beat
is filled with movement rather than reading as dead air. The reveal finishes around 3.6s and
then holds. The slot is sized to the narration, not the animation — K was left as authored,
since a longer pause should not slow the reveal down.

**Animation:** title settles, thesis line wipes in beneath it. Nothing fancy — the next frame does the work.

## Frame 1 — The obvious approach

- status: animated
- src: compositions/frames/01-wrong-model.html
- duration: 17.5s (starts 10.6s)
- transition_in: crossfade
- scene: Compare everything with everything — 2 billion comparisons, 23 days per submission
- voiceover: The obvious approach is to compare every new paper with every paper before it — rebuilding the whole grid each time. That's two billion comparisons. Even at a thousand a second, each new submission would take twenty-three days.
- narrativeRole: hook
- blueprint: big-number-hit

Hook is a joke about scale, not a lecture about complexity. Three beats only:
the idea, the number, the punchline.

- Left: a grid of papers where every cell connects to every other — it keeps filling until it's unreadable
- Right hero: counter running to **2,034,677,736**, labelled *comparisons, per submission*
- Punch stamp: **23 days** — at a thousand comparisons a second, per new paper

The rate has to survive a sceptic. A thousand per second is a rate nobody will argue with — and it still
takes twenty-three days for a single new paper. Frame 7 reuses the same rate so the two figures
are directly comparable.

Kill from the old version: the brute-force-cracking aside, the O(N) notation. Notation arrives in Frame 7, earned.

**Animation:** grid cells connect faster and faster until the panel is solid; counter races and lands; "64 years" stamps in late with a small overshoot, then everything freezes.

## Frame 2 — Weighted hashing, reverse indexing

- status: animated
- src: compositions/frames/02-thesis.html
- duration: 15s (starts 30.9s)
- transition_in: crossfade
- scene: The two ideas we picked, and the one we turned down
- voiceover: The tempting answer was embeddings. Turn every paper into a vector, and measure the distance. We found a way to reach the same verdicts for a fraction of the cost: weighted hashing, and a reverse index.
- narrativeRole: value claim
- blueprint: kinetic-title

This frame names the approach and sets up the two terms the rest of the video explains in
practical terms. Earlier drafts framed it as "search engines already solved this" with a
Google analogy — that was cut deliberately. It made a deliberate engineering choice sound
like borrowed prior art, when the actual decision was to reject embeddings (expensive,
still touches everything) in favour of weighted hashing plus a reverse index, which reach
the same verdicts far cheaper. Keep the framing on the choice, not on the precedent.

The whole method in four words: **Hash → Look up → Shortlist → Decide.**

One line under the strip: *nothing here is a search — every step is a lookup against keys
indexed in advance.*

**Animation:** the four steps slide in on a beat each and stay as a spine the later frames call back to.

## Frame 3 — The fingerprint

- status: animated
- src: compositions/frames/03-device-hash.html
- duration: 16s (starts 36.5s)
- transition_in: crossfade
- scene: Seven signals → one 16-character code
- voiceover: Seven signals from the browser and graphics card squeeze into one sixteen-character code. Same machine, same code. You can change your name and change your email. Most people don't change their laptop.
- narrativeRole: mechanism evidence
- blueprint: diagram-build

Seven input chips (`Canvas` · `WebGL` · `HwId` · `UA` · `Platform` · `Screen` · `DPR`) collapse
into `a3f91c02e8b74d15`.

Right panel is now **one** idea, not three: change the name, change the email, keep the laptop.
Hash explained in half a sentence on screen: *same input in, same code out — and the code can't be read backwards.*

Footnote, small: incomplete profiles are thrown away, so blank fingerprints never match each other.

**Animation:** seven chips fly into a funnel, scramble, resolve character-by-character into the hex code; then the author name and email above it swap twice while the code sits perfectly still.

## Frame 4 — The four keys

- status: animated
- src: compositions/frames/04-tokens.html
- duration: 14.6s (starts 52s)
- transition_in: crossfade
- scene: The machine · the network · two document properties
- voiceover: Four keys do the deciding. The machine. The network. And two identity fields a manuscript file carries in its own properties. Share any one of them, and two papers land in the same lookup.
- narrativeRole: mechanism evidence
- blueprint: card-stagger

Human label first, field name second. Weights are deliberately absent — a bare number
next to a key reads as precision the viewer can't interpret, and the ranking maths isn't
the point of this frame.

| On screen | Field |
| --- | --- |
| The machine | device |
| The network | ip |
| The document | wd_* |
| The document, again | wd_* |

The two document rows stay generic on purpose. Naming which property tends to survive a
clean-up is the one detail that would let someone defeat the check, so the frame discloses
that manuscript files carry identity fields and stops there.

Dimmed row underneath: language and company help with ranking but never decide alone.
Struck through: email — too many people share a mail provider for it to mean anything.

**Animation:** four rows deal in like playing cards between hairline rules.

## Frame 5 — The ceiling

- status: animated
- src: compositions/frames/05-caps.html
- duration: 17.2s (starts 66.1s)
- transition_in: crossfade
- scene: Popular values get ignored — same machine vs same internet
- voiceover: Some values are just popular. One campus network can cover a hundred honest papers, so every key has a ceiling. Above it, we ignore the value completely. Same machine is a signal. Same internet is not.
- narrativeRole: proof
- blueprint: big-number-hit

Two numbers, one point:
- **120** — device and network. Above this, the value is a crowd, not a clue.
- **500** — the Word-file names. Deliberately generous: one name on hundreds of manuscripts is the whole point.

Closing line on screen: *same machine is a signal — same internet is not.*

**Animation:** a shared-value cluster grows past 120, greys out and drops away; the Word-name cluster keeps growing past it and stays lit.

## Frame 6 — Twenty on the card

- status: animated
- src: compositions/frames/06-shortlist.html
- duration: 15.6s (starts 82.8s)
- transition_in: crossfade
- scene: One lookup → score → top 20
- voiceover: One lookup pulls back every paper that shares a key. Each one gets a score, and below three we call it coincidence and drop it. The top twenty reach the reviewer's card, with the evidence attached.
- narrativeRole: mechanism climax
- blueprint: pipeline-flow

Five steps, human labels on top, the jargon small underneath:

1. **Its keys** — the fingerprints on this submission
2. **One lookup** — a single database round-trip, not one per key
3. **Skip the crowds** — over-popular values ignored
4. **Score each match** — below 3 is coincidence
5. **Top 20** — what actually reaches the reviewer

Footer: *a shortlist, not a hairball.*

**Animation:** thousands of dots enter left, thin out at each stage, and land as twenty tidy rows — the funnel is the whole story, so let it play.

## Frame 7 — Squared, or straight

- status: animated
- src: compositions/frames/07-efficiency.html
- duration: 17.9s (starts 97.9s)
- transition_in: crossfade
- scene: O(N²) vs O(N · t · c) — 2.03B vs 778k, gap widens with the corpus
- voiceover: Here's the trade in one line. Compare every pair, and the work grows with the square of the archive. Look up shared keys, and it grows in a straight line. Two and a half thousand times less work today. And doubling the archive doubles the gap.
- narrativeRole: efficiency proof — the math
- blueprint: big-number-hit

Notation appears here for the first time, immediately translated. Each symbol gets four words, no more.

| | Compare every pair | Look up shared keys |
| --- | --- | --- |
| Notation | **O(N²)** — *grows with the square* | **O(N · t · c)** — *grows in a straight line* |
| Comparisons | **2,034,677,736** | **778,262** |
| At 1,000/sec | **23 days** | **13 minutes** |

The two clock figures assume the same rate, so they're a fair comparison — and they say the same thing
as the ratio without anyone having to trust the notation.

Centre gauge: **2,614× less work** — tagged *measured*, not modelled.

Decoder, three chips: **N** papers in the window (63,792) · **t** keys per paper (up to 6) · **c** ceiling per key (120).

Growth strip, three columns only — the point is the gap widening, not the table:
**today 2,614×** → **double the archive 5,229×** → **ten times 26,144×**

**Animation:** two curves race on the same axes — the quadratic leaves the top of the frame, the straight line barely lifts. The ratio counter climbs as the x-axis extends. This is the frame that most rewards a real chart.

## Frame 8 — What it actually costs

- status: animated
- src: compositions/frames/08-budget.html
- duration: 21.1s (starts 115.3s)
- transition_in: crossfade
- scene: Measured — 13 candidates, 2.9s a quarter, 20 rows, 6.4% reach a human
- voiceover: In practice it's smaller still. The typical submission has thirteen candidates worth scoring, out of sixty-three thousand. The whole quarter scores in under three seconds. And ninety-four percent of papers pass without anyone being interrupted, which is the real budget we're protecting.
- narrativeRole: efficiency proof — what it buys
- blueprint: big-number-hit

Every number measured on a 63,792-paper snapshot. Four stats, nothing else competing:

| Value | Label |
| --- | --- |
| **13** | candidates worth scoring — out of 63,791 |
| **2.9s** | to score the entire quarter |
| **20** | rows on the reviewer's card |
| **6.4%** | ever reach a human — 3.7% warn, 2.7% block |

One comparison strip, three short lines — no paragraphs:
*Word-file check reads 1 file · brute-force hunt reads 63,792 · Cluster Analysis indexes 63,792 and touches 13.*

**Animation:** four counters land on a beat each; the distribution bar draws left to right and stops well short of the ceiling — the empty space to the right is the point.

### Provenance (not on screen)
- `simulate_cluster_check.py` over `audit-network/data/snapshot.json.gz` — 63,792 articles, 90d, built 2026-07-23
- Outcome rates from 20,000 articles; denominator is hub-connected articles, not all submissions
- Snapshot caps device/IP 120, Word props 40 (PRD sets 500 — fanout rises, ceiling logic unchanged)
- Pairwise baseline N(N−1)/2; lookup baseline mean fanout 24.4 ÷ 2
- Clock figures assume 1,000 comparisons/sec for both sides: 2.03B ⇒ 23.5 days, 778k ⇒ 13.0 min
  (the measured 2.9s runtime is a separate, real figure — don't mix the two on one frame)

## Frame 9 — Telling colleagues from collusion

- status: animated
- src: compositions/frames/09-score.html
- duration: 17.2s (starts 135.9s)
- transition_in: crossfade
- scene: The score exists to avoid the obvious wrong answer
- voiceover: The score's whole job is avoiding the obvious wrong answer. Two colleagues sharing an office network? That's a Tuesday. The same machine turning up at two unrelated institutions? That's a Tuesday worth investigating.
- narrativeRole: accuracy proof
- blueprint: formula-reveal

Drop the formula as hero. Lead with the two cases side by side, and let the score move.

- **Same lab, shared network** → −2, stays quiet — *colleagues share offices; that isn't news*
- **Same machine, different institutions** → +2, climbs — *that's harder to explain*
- **Recent beats old** — reuse last week outranks an overlap from March
- **Two channels agree** → +4 — *one coincidence is cheap; two at once is expensive*

Formula stays, small, at the bottom for the people who want it.

**Animation:** one score bar, two runs. Run one adds the same-lab penalty and stalls below the line; run two adds the cross-institution bonus and the combo bonus and crosses it. Same mechanism, opposite verdicts.

## Frame 10 — What it takes to block

- status: animated
- src: compositions/frames/10-block.html
- duration: 16s (starts 152.6s)
- transition_in: crossfade
- scene: Three routes to BLOCK, plus the filters every cluster must clear
- voiceover: Blocking needs more than a hunch. Either all four keys line up at once, or a peer we've already flagged shares both a network and a document trail, or the Word-file check has already said no on its own.
- narrativeRole: decision proof
- blueprint: decision-tree

Human titles first, rule codes demoted to chips:

1. **All four keys align** — machine, network, and both Word names *(B0)*
2. **A known-bad neighbour** — an already-flagged peer sharing network *and* document evidence *(B1)*
3. **Document check failed** — the Word-file check blocked it independently *(B2)*

Filter strip, one line: a cluster only counts if it looks like a group — **2+ authors, 2+ institutions, no single name owning half of it.**

**Animation:** three routes light up in turn and converge on one BLOCK stamp; the filter strip slides under as a gate the evidence passes through.

## Frame 11 — The near-miss lane

- status: animated
- src: compositions/frames/11-warn.html
- duration: 11.3s (starts 168.1s)
- transition_in: crossfade
- scene: PASS → WARN → BLOCK, and what warn actually means
- voiceover: Everything strong but incomplete gets a warning instead. Not an accusation, an invitation to look. Same evidence, softer verdict.
- narrativeRole: decision proof
- blueprint: decision-tree

Three-stop strip: **PASS** (quiet) → **WARN** (amber) → **BLOCK** (hard stop), with warn clearly the middle lane rather than a weak block.

Two short cards only:
- **Same evidence, less of it** — the pattern is real but doesn't clear a block rule
- **The reviewer decides** — shortlist and evidence chips either way

No threshold number on this frame. It isn't the story.

**Animation:** a marker slides along the strip and settles on WARN with a soft pulse; the two cards fade up behind it.

## Frame 12 — Close

- status: animated
- src: compositions/frames/12-close.html
- duration: 9.2s (starts 181.7s)
- transition_in: crossfade
- scene: Repetition is how they scale — and how they're caught
- voiceover: Index once. Ignore the crowds. Hand the reviewer twenty scored peers instead of two billion comparisons.
- narrativeRole: close
- blueprint: kinetic-title

Three outcomes, four words each: **bounded review load · evidence you can check · action only when the rules fire.**

The last line is the whole pitch and should be the last thing on screen:
*Papermills scale by repeating themselves.*

**Animation:** the three outcome cards settle, then everything else recedes and the closing line holds alone over the brand lockup.

## Frame 13 — Outro

- status: animated
- src: compositions/frames/13-outro.html
- duration: 8.5s (starts 190.4s)
- transition_in: crossfade
- scene: Papermills scale by repeating themselves
- voiceover: Papermills scale by repeating themselves, which is exactly how they get caught.
- narrativeRole: close
- blueprint: kinetic-title

Same treatment as the title slide — centered, intro-style. The thesis line gets the whole frame so we don't end staring at the bottom of the impact slide.
