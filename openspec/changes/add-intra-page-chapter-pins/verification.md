# Verification — add-intra-page-chapter-pins

## Diagnosis (recap, all verified against fixtures + the live store)

The legacy derivation's page-granular ranges cannot represent same-page
chapter starts. On hcd-report, five pairs share a page — {3,4}@4, {5,6}@5,
{9,10}@10, {12,13}@12, {14,15}@13 — and two detection defects compounded
the limit: ch4's real heading ("4. The Four Phases of HCD Work", page 4
pos 2, char 259) was rejected by the D6-r3 "the"-carve-out (dot-shaped
"The …" titles needed a colon; this one has none), and no pin tier could
pin ch1–4 (openings floor page 20, sec-header head-window finds no N.M,
loose-digit rescue floors page 10). With ch4 missing, the consecutive-run
filter dropped the {1,2,3} prefix; with ch3–ch6 same-page pairs, monotone
selection sentineled ch6/10/13/15 to `(0, -1)`.

## Oracle

Live tree-driven annotations captured from the host store during diagnosis
(pages 4, 5, 6, 10, 11, 12, 13, 14 pulled; `StorageFactory.create_from_config(config())`
+ `_ensure_collection()` + scroll). The rule the oracle dictates: a
second-half heading keeps its boundary chunk with the previous chapter
only while the previous chapter's pre-extension range still contains the
cut page (p4.p2→ch3, p13.p3→ch14); when the previous span has ended
(p11.p2→ch11, p14.p0→ch16, p20.p4→ch19) the chunk goes to the heading's
chapter.

## Implementation results

- **Claim map**: all 21 hcd chapters claim with (source, page, ppos, char
  offset, half); ch4 claims with the title "The Four Phases of HCD Work";
  the "7. The IDEO" tail fragment on p6.p2 never claims (deferred; the
  complete capture on p6.p3 wins).
- **Carve-out rescue**: `_LICENSE_TITLE_RE` (sentence-case license
  vocabulary) keeps all 12 observed license shapes rejected (9 in
  user-manual incl. "2. The MIT License", "1. The Project Gutenberg eBook
  of"); user-manual/pve rosters byte-identical (18/18, 20/20).
- **Claim pin tier**: ch1@2, ch2@3, ch3@4, ch4@4 pinned; ch4's pin is
  monotone-rejected (same page as ch3) and recovers as a sentinel-recovery
  range (4,4) — ch5's cut at ppos 0 extends nothing.
- **Ranges** (actuals JSON `/tmp/opencode/pins_apply_actuals.json`,
  asserted == the corrected design table by the regen script): 1:(2,3),
  2:(3,3), 3:(4,4), 4:(4,4), 5:(5,5), 6:(5,6), 7:(6,8), 8:(9,9), 9:(10,10),
  10:(10,11), 11:(11,12), 12:(12,12), 13:(12,13), 14:(13,13), 15:(13,13),
  16:(14,15), 17:(16,18), 18:(19,20), 19:(20,22), 20:(22,22),
  21:(23,10**6). No hcd chapter carries `(0, -1)`. The diagnosis draft's
  table had four extension-rule misses, corrected in design.md before
  apply: 1:(2,2)→(2,3), 11:(11,11)→(11,12), 13:(12,12)→(12,13),
  18:(19,19)→(19,20); row 19's (20,22) was derived at apply time from
  ch20's cut (p22.p1, ppos>0), superseding the provisional (20,21).
- **Routing vs oracle**: exact match on all nine captured pages (3, 4, 5,
  6, 10, 11, 12, 13, 14), chunk by chunk — including the recovered page-6
  phase table (p6.p0–2 → ch6, "Phase Methods Output Common failure…") and
  ch1's page-3 tail (p3.p0 → ch1). Non-captured pages (19, 20, 22, 23)
  verified rule-consistent: p20.p0–3 → ch18 (its extended range), p20.p4 →
  ch19 (2nd-half, before-span ended), p22.p0 → ch19, p23 → ch21.
- **Accepted divergence (documented in design.md)**: live p6.p2 is
  annotated ch7/sec 7.1 by the tree annotator's most-recent-start span
  fallback; the legacy cut assigns it to ch6 (the chunk is 98% ch6
  content). The legacy path has no section-level evidence there.

## Baselines (task 3.1–3.2)

Regenerated surgically via `/tmp/opencode/regen_hcd_pins.py`: hcd's
`ranges` / `multi.keys` / `multi.bucket_pages` / `multi.titles` replaced
from the post-change derivation captured exactly the way the consuming
tests capture it (ranges debug line + multi-summary recorder); round-trip
byte-identical before mutation; the other three books canonical-identical.
Classification: ranges hard-asserted against the corrected design table;
buckets are capped window subsets (per-chapter limit 8, per-page density
caps) oracle-consistent on every live page; collision-chapter buckets
eyeballed — ch1 [2×5,3], ch2 [3×5], ch3 [4,4,4], ch4 [4,4,4], ch6
[5,6,6,6], ch7 [6×4,7,7,7,7], ch10 [10,10,11,11], ch11 [11×5,12], ch12
[12×4], ch13 [12,13]. The 5 baselines-pending tests flipped green.
knowledge-compilation: roster byte-identical — the ~6 regex-level
carve-out candidates predicted during diagnosis die on the full guard
chain (0 new claims); anthology veto intact (16 part headings, 0 legacy
headings, no veto note); calibration tests green.

## Deviations (recorded in design.md + tasks.md inline)

Claim map on the instance (`self._chapter_claims`) instead of a 4-tuple
return (~24 positional call sites); evidence filter (page ≥ 1, not
boilerplate, not ToC-like) after legacy tests caught printed-ToC probe
rows resurrecting phantom "(approx pages 0+)" ranges; single-target
fallback reordered (single_section_mode decided pre-recovery — same value
as before — recovery runs, fallback only when no target carries a real
range); tail deferral refined to `bm.end(2) >= len(raw) and bm.start() > 0`
(a match at offset 0 is a standalone heading emission — pve ch1).

## Gates

- `pytest tests/unit/rag -q` → 717 passed / 5 baselines-pending before
  regen; **722 passed, 0 failed** after (incl. 27 new
  `test_intra_page_chapter_pins.py` tests: claim shape/half, carve-out +
  12 license rejects, tail deferral, claim tier, the 13-page oracle
  routing table, extension/sentinel recovery, fallback).
- `pytest tests/unit/document -q` → 483 passed (0 modified).
- ruff check + format clean; mypy clean on both touched pipeline files
  (`scripts/audit_chapter_summaries.py` arity update carries 3 pre-existing
  mypy notes on unauthored monkeypatch lines; `scripts/` is outside the
  project mypy gate).
- Full fast suite: see "Suite totals" below.
- Live: the hcd document is tree-driven (the legacy path never runs for
  it); enumeration replay confirms the answer is unchanged — see below.

## Suite totals

Full fast suite `pytest -m "not integration and not chaos" -q` →
**4562 passed, 3 skipped, 0 failed** (57 s; the prior change's recorded
baseline was 4527 passed / 3 skipped — the +35 delta is exactly this
change's 27 new tests plus fix-chapter-heading-probe-rank's 8, applied
sequentially in the same tree).

## Live replay

`secondbrain chat "summarize by chapter hcd best practices report"
--session pins-probe-verify` (exit 0; excerpt
`/tmp/opencode/replay_pins.txt`): all 21 chapters enumerated 1..21 with
clean titles and no coverage note; chapter 19 renders the full stored
tree title "Agentic API-Contract Documentation (OpenAPI-First Tooling)" —
the tree-driven-path marker (the legacy derivation truncates at
"(OpenAPI" on the source `\ufffe` corruption) — confirming the live
document still takes the tree-driven path and the legacy derivation is
never consulted for it. Content matches replay #3's verified answer
(ch5's 18F method groups, ch13's page-13 takeaway, ch15's five ISO
diagnostics, ch16's stage checklists, ch21's source register). The
legacy-vs-live split comparison: the regenerated legacy buckets match the
live annotations on all nine captured pages (see Implementation results)
except the one documented p6.p2 divergence, which the tree annotator
resolves by section-span fallback.
