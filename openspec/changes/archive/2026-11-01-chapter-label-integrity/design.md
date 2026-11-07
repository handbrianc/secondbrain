# Design

## Context

The multi-chapter overview is produced by `_generate_multi_chapter_summary`
(`src/secondbrain/rag/pipeline/_fallback_mixin.py:593`), which streams one
`Chapter N — Title` heading per roster chapter and summarizes that chapter's
bucket via `_summarize_bounded`. Buckets are assembled upstream by page-range
fetching (`_pipeline.py` legacy path) or `_tree_chapter_buckets`
(`_structure_mixin.py:2656`, stored-tree path). The legacy path's overview
runs through `_generate_multi_chapter_summary_with_coverage`
(`_pipeline.py:2304`), which delegates **one chapter per call** to the funnel
with a single-key roster — discovered during the r2 acceptance replay. The
existing `_chapter_range_gate` (`_structure_mixin.py:2276`) vets pin-vs-pin
agreement only and is skipped entirely when a document carries fewer than 4
evidence pins (this report carries 0). Chunks carry the structured identity
fields `section_id`, `chapter_id`, and `heading_path` (ingest-time docling
capture — sparse: only some chunks carry them; `chapter_id` values may be
non-numeric slugs), plus `page_number`/`page_pos`/`chunk_role`/`chunk_text`;
line-initial `N.M` text markers exist only in magazine-style documents (this
report has none, and is 17 pages — inside the text path's front-matter
floor). Constants calibration convention lives beside `_CHAPTER_GATE_*`
(`_structure_mixin.py:271-273`); the placeholder-note wording lives inline in
`_generate_multi_chapter_summary` and is asserted verbatim by existing tests.

**r2 acceptance-replay discovery (live store, `story_mapping_epics_report.pdf`):**
the v1 text-marker guard was a no-op — the doc's 119 body chunks span pages
1–17 (all under the page-20 floor) and carry no `N.M` text lines, while the
payload's structured fields identify the contested content precisely
(page 8: `chapter_id=7`, `section_id=7.1–7.5` under a "Chapter 6" page-range
pin; page 9: `8.1–8.2`). Structured identity is ingest-time evidence and is
authoritative over query-time page-range pins.

See proposal.md for motivation and specs/rag-pipeline/spec.md for the
behavioral contract.

## Goals / Non-Goals

**Goals:**
- One deterministic pass over the final buckets, inside the shared funnel, so
  both the legacy and stored-tree callers are covered.
- Reassign mislabeled content to the chapter its own marker names; drop it
  when that chapter is not rostered; never summarize it under the wrong
  heading.
- Acknowledge roster gaps with a streamed note so a partial overview can no
  longer pass as complete.
- Keep streamed output and stored answer byte-identical (notes go through
  `_on_chunk` like headings).

**Non-Goals:**
- Suppressing or interpreting `show_thinking` output (the model's mismatch
  note is display-only; the deterministic marker guard replaces any need to
  parse reasoning).
- Re-pinning page ranges or touching the agreement gate, anthology path,
  single-section full-fetch path, or the per-chapter instruction's grounding
  and no-hedging rules.
- Re-ingesting the report to capture its structure tree (operational, not
  code; the tree path already carries its own no-cross-chapter guarantee).
- Fixing the upstream detection that mis-pins this document's ranges — the
  guard makes wrong pins harmless instead of chasing pin perfection.

## Decisions

**D1 — Guard inside the shared funnel AND once over the full roster in the
legacy coverage wrapper (r2).** The funnel keeps the guard as the tree-path /
standalone safety net, but the legacy path's
`_generate_multi_chapter_summary_with_coverage` delegates one chapter per
call with a single-key roster — a guard inside those delegations alone would
drop (not reassign) foreign content and could never see roster gaps. So the
wrapper runs the guard **once over the full roster** before its loop and
passes the guarded buckets down; each per-chapter funnel call then re-runs
the guard on already-clean buckets (a no-op). The wrapper owns the guard
reason line for guard-emptied chapters (mirroring its existing degraded-window
note splicing) and appends the roster note once at the end. The guard/reason/
note logic lives in shared helpers on the fallback mixin so both owners stay
byte-identical. Alternative considered: moving the wrapper's delegation to one
full-roster funnel call — rejected; that would change the wrapper's per-chapter
coverage-note splicing and its streaming behavior (fix-summary-fidelity D2).

**D2 — Per-chunk reassignment, not per-bucket dominance veto.** A chunk's own
marker is per-chunk evidence; moving only mismatched chunks preserves any
genuine chapter-N content sharing the bucket (mixed buckets are possible after
a half-page boundary error). A whole-bucket dominance veto would throw away
good content and needs a threshold to calibrate. The rule is threshold-free:
identity mismatch → move (or drop), match or absent → stay.

**D3 — Identity extraction: structured payload first, text markers second
(r2).** Priority order, first hit wins: `section_id` dotted/bare numeric
prefix (`"7.1"` → 7, `"11"` → 11) → numeric `chapter_id` (non-numeric slugs
ignored) → `Chapter N` prefix of `heading_path` → heading-shaped text marker
(the v1 rule: line-initial `\d+\.\d+` in the first two lines, ≤120-char line,
dot-leader-free, no trailing bare page number, page < 20 floor). Structured
fields never hit the page floor — they are ingest-time evidence, immune to
the ToC-row hallucination the floor defends against; the floor stays on the
text path only. Conflict policy: first available field in priority order wins
(deterministic; ingest-internal disagreement is not re-litigated at query
time). Implemented as a module-level `@staticmethod` next to
`_detect_chapter_openings` for unit testability without instantiating the
pipeline.

**D4 — Reassignment target must be rostered; dedupe by chunk id.** Moving a
chunk into chapter M's bucket appends by `(chunk_id)` uniqueness — a chunk
already in M's bucket (page-range overlap) is not duplicated. A dropped chunk
is only dropped from buckets, never from the store. Processing walks chapters
in ascending key order and each chunk moves at most once (a moved chunk is not
re-examined), so the pass terminates deterministically in one sweep.

**D5 — Placeholder reason line and roster note are new streamed blocks with
fixed wording.** The placeholder note gains a second line: "Content in this
chapter's detected page range self-identifies as chapter M and was summarized
under chapter M's heading." (drop variant: "...could not be attributed to any
rostered chapter and was skipped."). The roster note: "Coverage note: the
detected chapter roster does not include chapter(s) X, Y — they may exist but
were not located in the document's structure; this overview covers only the
chapters listed above." Both stream via `_on_chunk` and are appended to the
stored transcript, preserving the streamed == stored invariant the module
already documents. Roster note fires only when `len(chapter_keys) >= 3` and
`min(keys) > 1 or gaps within 1..max(keys)`.

**D6 — Constants with calibration comments, mirroring `_CHAPTER_GATE_*`.**
`_BUCKET_MARKER_MAX_LINES = 2`, `_BUCKET_MARKER_MAX_HEADING_CHARS = 120`,
`_ROSTER_NOTE_MIN_CHAPTERS = 3`. No score thresholds (D2 is threshold-free).

## Revision history

- **r2 (2026-11-01, live acceptance replay):** v1's text-marker guard was a
  verified no-op on the target document (17-page doc under the page-20 floor;
  no `N.M` text lines; structured payload fields present and decisive), and
  the live legacy path routes through the per-chapter coverage wrapper, which
  the v1 guard could neither reassign across nor note for. D1 gained the
  wrapper integration, D3 gained structured-first identity, and the spec
  delta gained the structured-identity scenarios. Tasks group 4 covers the
  rework.

## Risks / Trade-offs

- [False marker positives move good content] → Line-anchored `N.M` shape with
  the opener guards; list items and inline numbers don't match; unit tests
  cover list-item, dot-leader, and page-suffix negatives.
- [Dropped foreign content reduces coverage] → It was about to be mislabeled;
  the placeholder reason says where it went. Recall is restored by the
  operational re-ingest (tree path), not by the guard.
- [Wording churn breaks stored-transcript tests] → New wording lives in
  module constants; existing placeholder wording is untouched.
- [Tree path regresses] → D3/D4 are no-ops on clean buckets (clean-bucket
  byte-identity scenario); existing tree-path tests cover the funnel.

## Migration Plan

No data migration. Deploy is a code-only change; rollback is a revert. The
guard is additive: with no markers in buckets it is a no-op, so the legacy
path's treeless behavior changes only where it was provably mislabeling.

## Open Questions

(none — the marker-shape rules are pinned by D3; wording is fixed by D5;
calibration constants are declared in D6.)
