# Design

## Context

Reproduction (explorer session `ses_e66f5e47cffe4cwMJTaoC0nz75`, scratch
scripts in `/tmp/opencode/repro_probe_drop.py`, `probe_matrix.py`,
`probe_final_checks.py` — no repo changes): the dense three-chapter book
from `tests/unit/rag/test_chapter_window_purity.py::TestDensePageDocumentOrder`
(`_dense_banner_book`, docstring at lines 586-591) rerun with the REAL
`_probe_document_structure` (no probe pin):

- probe returns 18/18 chunks including ch3's heading → the sample is not
  the problem;
- `_derive_chapter_numbers` → roster {1, 2} — ch3 dropped;
- flow enters `single_section_mode` (`_pipeline.py:1559`, ≤2 chapters) →
  two-chapter lossless fetch, no per-page bound: ch2's bucket absorbs
  ch3's page (12 chunks incl. 9 from one page);
- answer lists two chapters; ch3 has no bucket, no summary, and no note.

Variant matrix (same book, real probe sample):

| variant | roster | reading |
|---|---|---|
| V1 baseline | {1,2} | ch3 dropped |
| V2 banner title de-glued | {1,2} | the glued title is irrelevant |
| V3 banner without "Chapter" | {1,2,3} | no pass-1 capture → auth_max=0 |
| V4 ch3 heading as "Chapter 3 …" | {1,2,3} | pass 1 captures 3 → auth_max=3 |
| V5 heading removed from sample | {1,2} | the hypothesized rank-cut mechanism |
| V6 heading-only merge | {1,2} | **merging headings does not fix it** |
| sparse page 30 | {1,2} | density is irrelevant |

V3/V4 flip the outcome by moving `auth_max`; V6 shows the naive fix is
insufficient; V1≈V5 shows the drop is indistinguishable from the hypothesized
rank cut — but the ceiling, not a cut, is what fires.

Chain (all file:line verified): `_pipeline.py:461-464` calls
`_probe_document_structure(top_k=400)`; `_structure_mixin.py:1622-1686`
primary role-filtered scroll `limit=10000`, fallback (len < 5) all-chunk
scroll `limit=top_k`; `qdrant.py:864-914` sorts by `page_number` and slices
— page-ascending, no vectors, no scores. Roster derivation at
`_pipeline.py:526-528`; `auth_max` defined at `_structure_mixin.py:1262`;
silent ceiling guards at `:1316` (bare), `:1401` (banner), `:1422`
(ft_catch). Downstream: `filter_chapters_by_target` (`_constants.py:9`,
`_pipeline.py:536-540`), ToC phantom-kill can only remove more,
`single_section_mode = len(chapter_keys) <= 2` (`_pipeline.py:1559`),
buckets at 1601-1606, `_generate_multi_chapter_summary_with_coverage`
(`_pipeline.py:2307`). Double silence: the ceiling logs nothing, and the D5
gap note (`_fallback_mixin.py:310-332`) scans only `1..max(roster)` — a
dropped above-ceiling chapter is invisible to both.

Existing test coverage: `TestDensePageDocumentOrder` pins the probe to
`_dense_probe()` (three headings only) precisely to route around the drop
(lines 696-704 comment); the 26 purity tests pin admission/notes/thresholds
and none reproduces the drop.

## Decisions

### D1 — Role-gated ceiling exemption (the fix)

At `_structure_mixin.py:1313-1319` (bare loop) and `:1398-1403` (banner
loop), the ceiling clause `(auth_max > 0 and major > auth_max)` becomes
`(auth_max > 0 and major > auth_max and not is_heading_chunk)` where
`is_heading_chunk = chunk.get("chunk_role") == "heading"`. Rationale:

- The ceiling's documented purpose (`:1256-1261`) is suppressing noisy
  body text in Chapter-N-labeled books. Noise lives in body chunks; real
  headings in role-marked books live in heading chunks. Keying on the
  chunk's role preserves the noise guard exactly where it operates.
- Marker-less books (all body) keep today's ceiling — there is no role
  signal to distinguish a heading from prose there, and inventing one is
  out of scope.
- `ft_catch` (`:1422`) keeps the unconditional ceiling: its matches are
  flattened-ToC row shapes, and an above-ceiling ToC row is a phantom by
  construction.
- Residual risk (accepted): a dot-less numbered heading-role line above
  the ceiling in a Chapter-N-labeled book ("12 Selection and Assignment"
  stored as a heading chunk) would now claim. Numbered non-dotted section
  headings are rare; the baseline diff review (D4) measures whether any
  fixture regresses.

### D2 — Heading channel into the derivation input

At `_pipeline.py:526-528`, before `_derive_chapter_numbers`, merge
`self._searcher.storage.find_structural_chunks(chunk_roles=["heading"],
source_prefix=source_filter)` into `structure_chunks`, dedup by `chunk_id`
(preferring the probe's copy), preserving page order. This mirrors the
opener-evidence pattern and its comment at `_pipeline.py:1575-1598`
("opener-page evidence must not depend on the probe sample"). It is
complementary, not sufficient alone (V6): with the exemption (D1) it also
covers probe-sample truncation for role-marked oversized books. Marker-less
books gain nothing here (no heading roles exist) — their truncation hazard
is the recorded follow-up.

### D3 — Surfacing

At the three ceiling guards, `logger.debug("Ceiling refused chapter %d for
%s (%s match)", major, source, shape)` on the refusal path. Debug level:
the refusal is routinely correct (noise); the point is that it is no longer
invisible when debugging a dropped chapter.

### D4 — Tests and reconciliation

- New tests in `tests/unit/rag/test_chapter_window_purity.py` (or a sibling
  module): (a) the dense book with the REAL probe → roster {1,2,3}, ch3
  bucketed, three summaries, no single-section degradation; (b) body-noise
  regression — a Chapter-N book with a bare above-ceiling body line keeps
  its roster; (c) heading-channel merge — a double whose primary sample
  omits a heading chunk still derives it via the channel; (d) refusal log
  emitted (caplog). The existing `TestDensePageDocumentOrder` stays as-is
  (it pins D3/D4 document-order behavior with a pinned probe).
- Fixture reconciliation: probe all four book fixtures for above-ceiling
  heading-role bare matches before/after; baselines regenerate only for
  books whose derived roster actually changes, with the diff classified.
  Expected: no fixture changes (the four books' ceilings already admit
  their full rosters) — if one changes, classify against ground truth
  before accepting.
- Live: the hcd document is tree-driven (derivation not consulted); one
  enumeration replay confirms no answer change.

## Risks

- The exemption widens admission for heading-role chunks in Chapter-N
  books; the four-fixture probe (D4) is the guard, plus the body-noise
  regression test pinning the ceiling's original purpose.
- The heading channel adds a storage call per derivation; it is the same
  call shape the opener scan already makes on this path
  (`_pipeline.py:1586-1590`) and is bounded by the source prefix filter.

## Deviations decided during apply (recorded in tasks.md inline)

- **Derivation sample merge sits before the empty-check.** The heading
  channel merges before `if not structure_chunks`, so an empty probe with
  a non-empty heading scan now proceeds to derivation instead of the
  generic one-shot. Degenerate probe-independence (both calls hit the
  same storage); a degraded storage returns `[]` for both and the
  generic fallback stays. Accepted.
- **`pending_bare` post-scan ceiling stays unconditional (with a log).**
  The tail-deferral post-scan keeps its unconditional ceiling — a
  tail-truncated capture above the ceiling would claim a truncated
  (corrupt) title, so refusal is safer; the complete capture on its
  neighbor chunk claims properly through the exemption. The refusal is
  logged per D3. The spec's letter ("only from non-heading chunks") is
  read as governing in-scan claims; truncated captures defer.
- **One harness reconciled (sanctioned).**
  `test_pipeline.py::test_spaced_title_backfill_replaces_glued_roster_title`
  pinned `_probe_document_structure` to two ToC rows, artificially hiding
  the stub storage's heading chunks from the derivation — the dependency
  D2 removes. With the real (unpinned) probe the pre-B sample already
  contained those headings. The harness now pins to the real probe's
  shape and serves ch6's heading (the sibling test at :6388 models this
  world); every assertion line unchanged.
- **Post-review hardening (review round, same day).** Two accepted
  findings, both in the channel this change owns. (1) The channel's
  degraded-storage except was silent; it now warns with ``exc_info``
  (mirroring the opener scan it was modeled on) — a silent failure would
  have reverted exactly this change's fix with zero signal. (2) The merge
  appended scan-only chunks wholesale, but the probe sorts by page number
  only (within-page order is the store's scroll order) and truncates
  after that sort, so its cut can land mid-page and drop a heading whose
  pos precedes included same-page chunks — appended at the end, a
  same-number body claim could shadow it (first-claim-wins). The merge
  now weaves scan-only chunks in at their ``(page_number, page_pos)``
  position, never disturbing the probe's own order; pageless chunks keep
  the historical append-at-end. Regression test:
  ``test_scan_only_heading_woven_before_shadowing_body_claim``
  (storage double with scroll-order within-page serving). The weave is
  identity when the scan dedupes empty (all fixture books), so no
  baseline changes.
