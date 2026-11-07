# Design

## Context

Rounds 1–2 of `fix-chapter-evidence-fidelity` made the live document
tree-driven and verified it (replay #3: 21/21 chapters, clean titles). The
legacy fallback kept its accepted limitation (D6-r4): page-granular ranges
cannot represent same-page chapter starts. This change designs against the
captured ground truth, not a model of it:

**Claim geometry (fixture diagnosis, all verified):**

| ch | claim position | half | live page-owner split |
|----|----------------|------|----------------------|
| 1  | pg2.p0 @0/506  | 1st  | — |
| 2  | pg3.p1 @247/508 | 1st | — |
| 3  | pg4.p0 @0/508  | 1st  | p4.p0–2 → ch3 |
| 4  | pg4.p2 @259/493 (rejected today) | 2nd | p4.p3–5 → ch4 |
| 5  | pg5.p0 @0/509  | 1st  | p5.p0–3 → ch5 |
| 6  | pg5.p4 @55/336 | 1st  | p5.p4, p6.p0–1 → ch6 |
| 7  | pg6.p3 @38/507 | 1st  | p6.p2–6 → ch7 (see divergence) |
| 9  | pg10.p0 @70/496 | 1st | p10.p0–4 → ch9 |
| 10 | pg10.p5 @179/510 | 1st | p10.p5–6, p11.p0–1 → ch10 |
| 11 | pg11.p2 @418/504 | 2nd | p11.p2–6 → ch11 |
| 12 | pg12.p1 @132/504 | 1st | p12.p0?–p12.p1–4 → ch12 (p12.p0 = ch11 tail) |
| 13 | pg12.p5 @172/505 | 1st | p12.p5, p13.p0 → ch13 |
| 14 | pg13.p1 @181/511 | 1st | p13.p1–3 → ch14 |
| 15 | pg13.p3 @389/510 | 2nd | p13.p4–5 → ch15 |
| 16 | pg14.p0 @376/511 | 2nd | p14.p0–4 → ch16 |

Live oracle: post-refresh annotations on the host store, pulled for pages
4, 5, 6, 10, 11, 12, 13, 14 during diagnosis. The rule the oracle dictates:
a second-half heading keeps its boundary chunk with the previous chapter
only while the previous chapter's span still contains the page (p4.p2 →
ch3, p13.p3 → ch14); when the previous chapter's span has ended
(p11.p2 → ch11, p14.p0 → ch16, p20.p4 → ch19), the chunk goes to the
heading's chapter.

**Why ch1–4 vanish today:** ch4's claim dies in the D6-r3 carve-out
(`_structure_mixin.py:1371-1376` — `fw == "the"` requires the dot shape AND
a colon; "The Four Phases of HCD Work" has no colon). The run filter
(`_structure_mixin.py:1540-1552`) then keeps only the longest consecutive
run {5..21}. Chapters 1–3 had claimed fine (pg2.p0, pg3.p1, pg4.p0) but die
with ch4's gap; and no pin tier can pin them anyway
(`_detect_chapter_openings` skips page < 20 at
`_structure_mixin.py:958`; the loose-digit rescue floors at page ≥ 10 at
`_pipeline.py:1338`; no `N.M` header appears in their chunks' first 150
chars; no "Chapter N" text exists).

**Why the four sentinels exist:** monotone selection
(`_structure_mixin.py:2134`) rejects any pin whose page is ≥ the previous
chapter's pin, so same-page pairs {5,6}@5, {9,10}@10, {12,13}@12,
{14,15}@13 lose the later chapter; `_pipeline.py:1548-1550` gives the
roster chapter a `(0, -1)` sentinel range whose bucket stays empty except
for the marker guard's heading-bearing chunks.

## Decisions

### D1 — Claim channel (separate from the page-pin machinery)

`_derive_chapter_numbers` pass 2 records, at claim time, the chunk's
(page_number, page_pos), the match offset, and the half. The function
returns a fourth element: `claims: dict[int, tuple[int, int, int, bool]]`
keyed by chapter number for the claimed source (first claim wins, matching
`seen`). Pass-1 (`chapter_n_re`) claims record positions the same way.
Call sites to update: `_pipeline.py:526-528` and
`scripts/audit_chapter_summaries.py`. The monotone machinery
(`_select_monotone_pins`, `_pin_fits_window`) is untouched — same-page
later pins still die there; the cut map carries what the page-pin map
cannot.

Half rule mirrors `structure_annotate` exactly: `char_offset <
len(text) / 2` → first half (`structure_annotate.py:425`).

### D2 — Carve-out rescue, license gate, deferred tails

In the `legal_starts` branch, the "the" carve-out becomes: dot-shaped AND
(`":" in title` OR not `_LICENSE_TITLE_RE.search(title)`), where
`_LICENSE_TITLE_RE` (module level, next to `_BOILERPLATE_CAPTION_RE`,
case-insensitive) matches the sentence-case license vocabulary observed in
the corpus regression scan: `project gutenberg`, `e-book of`/`ebook of`,
`free software foundation`, `mit license`, `gnu free documentation`,
`origin of this software`, `endorse or promote`, `documentation license`,
`redistributions? of`. The scan over all four fixtures showed this admits
exactly ch4 (hcd) plus six knowledge-compilation headings (reviewed at
regen — they are the compilation's real numbered headings) and keeps all 12
license shapes rejected (9 in user-manual, incl. "2. The MIT License").

Tail-truncated captures: when `bm.end(2) >= len(raw)` the title class ran
to the chunk's final character — the line is incomplete at the chunk
boundary ("7. The IDEO" fragment, p6.p2 tail). Such matches are collected
during the scan and claimed only after it, and only if the number is still
unclaimed — the complete "7. The IDEO Field Guide…" capture on p6.p3 wins
first. A complete heading that merely sits at a chunk's end still claims
(post-scan), so no legitimate claim is lost.

### D3 — Claim pin tier (fill-only)

In the pin assembly (`_pipeline.py`, after the loose-digit rescue, before
interpolation): for each roster chapter of `src` with a claim, not already
in `chapter_first_pg`, not in `toc_killed_`, claim page not in
`boiler_pages_`/`toc_like_pages_`, and `_pin_fits_window` → pin at the
claim page. This pins ch1@2, ch2@3, ch3@4 (ch4@4 is also pinned, then
monotone-rejected as designed). No `page < 10` floor: a derivation claim is
heading evidence, the strongest kind the legacy path has.

### D4 — Cut map

Built after monotone selection, the claim tier, and the page-pin range
construction, before extensions are applied (D6 orders the steps). For
each roster chapter c with a claim (page P, ppos, half) where P equals
c's final pin page (or c is an unpinned claimed chapter — it will be
sentinel-recovered with range start P, see D5), record `cut = (P, ppos,
half, after=c, before_contains=…)`. `before_contains` = whether the
BEFORE chapter (the after-chapter's roster predecessor) has a
pre-extension range containing P, computed from the page-pin ranges
before extensions are applied (D6 orders the steps). Multiple cuts on one
page are stored ascending by ppos. Cuts are consulted only for chapters
that survive to bucket assembly: a cut whose after-chapter is ToC-killed
or filtered out is dropped at admission time and its page falls back to
today's rule.

Admission (both loops — single-section `_pipeline.py:1622-1662` and
round-robin `:1663-1798`; factor a shared `_chunk_chapter_owner(page,
ppos)` helper): walk the page's cuts ascending; segment before the first
cut → its before-chapter; boundary chunk → after-chapter on first half,
else before-chapter iff `before_contains`, else after-chapter; between cuts
→ the previous cut's after-chapter; after the last cut → its
after-chapter. Verify the chosen owner's range contains the page (and for
boundary chunks, the chosen chapter's); on any miss, fall through to
today's first-range-wins rule. Pages without cuts keep today's behavior
byte-for-byte.

### D5 — Range extension and sentinel recovery

Extension: after `source_chapter_ranges_` is built
(`_pipeline.py:1473-1498`), for each consecutive roster pair (j, j+1) where
j+1 has a cut on page P == j+1's range start page (its pin page, or its
claim page when j+1 is sentinel-recovered — its range does not exist yet
at pass time) and j's range end == P-1: if the cut's ppos > 0 (pre-heading
chunk positions exist on P), set j's end to P. ppos == 0 cuts extend
nothing (ch4→ch5; ch15→ch16). A sentinel j has no range at pass time; its
recovery formula below embeds its own extension, so the pass skips it.
Extensions happen AFTER `before_contains` was computed (D4) so the
second-half rule keeps seeing pre-extension truth. Predicted extensions
on hcd: ch1 (2,2)→(2,3) via ch2's cut (p3.p1); ch11 (11,11)→(11,12) via
ch12's cut (p12.p1); recovery-embedded: ch6→(5,6) via ch7's cut
(p6.p3), ch10→(10,11) via ch11's cut (p11.p2), ch13→(12,13) via ch14's
cut (p13.p1), ch15 stays (13,13) (ch16's cut at ppos 0).

Sentinel recovery: in the sentinel insertion block
(`_pipeline.py:1547-1550`), a roster chapter with a claim and no range gets
`(claim_page, next_roster_boundary_end)` where the end is the next roster
chapter's start page minus 1, extended onto that chapter's cut page when
its cut ppos > 0. ch6 → (5, 6), ch10 → (10, 11), ch13 → (12, 13), ch15 →
(13, 13). Chapters without any claim keep the `(0, -1)` sentinel (the
placeholder-note path still speaks for them). `single_section_mode`
counting and `_chapter_range_gate` are unaffected (the key set is
identical; only sentinel tuples become real ranges).

Expected final hcd legacy ranges (rule-derived; ch19–21 are predictions
pending the implementation's claim map — ch20/ch21 cut positions were not
captured, so derive them from the claim map + the extension rule): 1:(2,3),
2:(3,3), 3:(4,4), 4:(4,4),
5:(5,5), 6:(5,6), 7:(6,8), 8:(9,9), 9:(10,10), 10:(10,11), 11:(11,12),
12:(12,12), 13:(12,13), 14:(13,13), 15:(13,13), 16:(14,15), 17:(16,18),
18:(19,20), 19:(20,21), 20:(22,22), 21:(23,∞). Overlapping tuples are
expected and resolved by cuts at admission. The diagnosis draft's
1:(2,2), 11:(11,11), 13:(12,12), 18:(19,19) were extension-rule misses,
corrected here (ch13 via the recovery-embedded extension; live oracle
confirms p13.p0 → ch13).

### D6 — Assembly order in `_pipeline.py`

1. Derivation (returns claims) → roster → pin tiers (existing) → claim
   tier (D3) → interpolation (existing) → monotone selection (existing) →
   page-pin ranges built (existing) → `before_contains` captured → cuts
   built (D4) → extensions applied (D5) → gate → target filter → sentinel
   recovery/replacement (D5) → buckets with cut-aware admission (D4).

### D7 — Verification and baselines

- New unit tests: claim recording + half computation; carve-out rescue
  (ch4 claims; 12 license shapes rejected; tail fragment defers); claim
  tier; cut admission (the five hcd same-page/boundary pairs asserted
  chunk-by-chunk against the live-oracle table); extension + sentinel
  recovery; falls-back-to-legacy when a cut owner lacks the page.
- Baselines: regenerate the hcd section (and only sections the diff shows
  changed) with `scripts/export_chapter_fixtures.py`'s exact format;
  classify every diff as ground-truth-verified (vs the oracle table) or
  investigate. knowledge-compilation gains six roster claims from the
  carve-out rescue — reviewed at regen (outcome: ZERO new KC claims — the
  six regex-level candidates die on the full guard chain; its roster and
  baselines are byte-identical, veto intact).
- Live: the hcd document is tree-driven; confirm via one enumeration
  replay that the answer is unchanged (the legacy path never runs for it),
  and compare the regen'd legacy splits against the captured live
  annotations table.

**Accepted divergence (documented, not fixed):** live p6.p2 is annotated
ch7/sec 7.1 by the tree annotator's most-recent-start span fallback (the
chunk is 98% ch6 content — "Five Whys… affinity mapping" — with ch7's
heading fragment truncated at its tail). The legacy cut assigns p6.p0–2 →
ch6, which keeps the phase table (the todo's goal) and reads more
faithfully for this chunk. The legacy path has no section-level evidence
at this position; adding it is out of scope.

## Deviations decided during apply (recorded in tasks.md inline)

- **Claim map travels as `self._chapter_claims`, not a 4th return
  element (D1).** ~24 test call sites and monkeypatched doubles unpack
  `_derive_chapter_numbers` positionally; changing the arity would touch
  every one. The instance attribute travels with the roster the same way;
  the audit script surfaces `rec["claims"]`.
- **Evidence filter on claims (extends D3/D4/D5).** Legacy tests caught
  printed-ToC probe rows (which key the page under `"page"`, yielding
  page 0) recording claims that leaked into the claim tier, cut map,
  extension pass, and sentinel recovery — resurrecting phantom "(approx
  pages 0+)" ranges. One shared predicate (`page ≥ 1`, not boilerplate,
  not ToC-like) filters `src_claims_` for all four consumers; claims
  without page evidence keep the `(0, -1)` sentinel and the generic
  fallback.
- **Single-target fallback reordered (extends D5/D6).** The empty-range
  generic fallback ran before sentinel recovery, so a single-target query
  ("summarize chapter 4") for a claimed-but-unpinned target fell back to
  generic search before recovery could give it a real range. Order is
  now: `single_section_mode` decided from the pre-recovery key set
  (byte-identical value to before), recovery runs, then the fallback
  fires only when no target carries a real range — `(0, -1)` sentinels
  still fall back exactly as today.
- **Tail deferral refined (D2).** Defer only when the match starts after
  the chunk's first character AND runs to the chunk's final character
  (`bm.end(2) >= len(raw) and bm.start() > 0`): a match at offset 0 is a
  standalone heading emission and must claim in-loop (pve ch1
  regression).

## Risks

- The carve-out rescue widens admission for "The …" titles corpus-wide;
  bounded by the license vocabulary gate and verified by the four-book
  baseline diff. If knowledge-compilation's roster corrupts or its
  anthology veto flips, tighten the gate (e.g. require the matched line to
  be a standalone line) with the counter-example in hand.
- Overlapping ranges are new for downstream consumers
  (`filter_chapters_by_target`, window composition, straddle tolerance);
  the cut admission must be the only place ranges overlap, and the
  owner-verification fallback bounds any mistake to today's behavior.
- The claim tier pins on pages < 10 for the first time (derivation-claim
  evidence); guarded by toc/boiler/window checks and exercised by hcd
  ch1–3 in tests.
