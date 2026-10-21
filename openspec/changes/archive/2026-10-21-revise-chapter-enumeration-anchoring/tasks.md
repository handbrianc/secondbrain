# Chapter Enumeration Anchoring — Tasks

Reference evidence (from the 2026-10-20 diagnosis, scripts in
`/tmp/opencode/diagnose_chapters.py` and `/tmp/opencode/replay_tiers.py`):
observed ranges `{1:(3,3), 5:(4,4), 6:(5,21), 7:(22,22), 8:(23,23),
15:(24,598), 16:(599,658), 17:(659,947), 18:(948,∞)}`; all 18 chapters
carry `N.1` heading chunks at true openers (1.1@20, 2.1@29, 3.1@43, 4.1@47,
5.1@51, 6.1@89, 7.1@103, 8.1@125, 9.1@143, 10.1@161, 11.1@175, 12.1@235,
13.1@237, 14.1@263, 15.1@271, 16.1@469, 17.1@475, 18.1@481); run-on ToC
rows recovered 11 printed openers equal to stored pages; 1,222 bare-number
nav footers agree printed == stored.

## 1. Footer offset (`src/secondbrain/document/fast_text.py`)

- [x] 1.1 `_FOOTER_PAGE_RE` (line 79): accept an optional `/total` suffix —
  `^\s*(\d{1,4})(?:\s*/\s*\d{1,4})?\s*$` — so bare `"29"` parses while
  `"1 About Oracle VirtualBox"` and `"iii"` still do not.
- [x] 1.2 `footer_page_offset` (line 147): change the sanity guard
  `0 < printed < physical` to `0 < printed <= physical` so offset-0 books
  resolve. Keep the ≥3-pages / ≥80%-agreement gates exactly as they are.

## 2. Section-heading evidence tier (`rag/pipeline/_structure_mixin.py`, wired in `rag/pipeline/_pipeline.py`)

- [x] 2.1 Add `_section_heading_pins(full_chapters, src, heading_chunks,
  boiler_pages)` → `dict[int, int]` (plus a module-level `_SECTION_PIN_RE`
  = `^(\d{1,2})\.1(?:\.\d+)?\s+`): for each roster chapter, first
  heading-role chunk matching the regex on a page ≥ 10, not in
  `boiler_pages`, and whose page is not dot-leader-dense (guard helper
  from task 4.1). Pin = page − 1 when that page has body chunks for src,
  else the heading's own page; document the ±1-page contract in the
  docstring. Cap chapter numbers at 30 (same bound as the section scan).
- [x] 2.2 Wire it in `_pipeline.py` as the FIRST pin tier (before the
  heading-anchor fetch at line ~246 — reuse that fetch, just reorder),
  inserting pins via `_pin_fits_window` at insertion time; record the
  chapter numbers it pinned in a `provisional_pins_` set (used by 3.2).
- [x] 2.3 Existing anchors (`_heading_title_anchors`), body-title scan,
  and all later tiers keep their "only fill unpinned chapters" semantics —
  no behavior change for chapters the evidence tier already pinned.

## 3. Exact ToC evidence overrides provisional pins (`_pipeline.py`)

- [x] 3.1 Add an evidence-validated offset fallback for the run-on tier:
  when `footer_offset_ is None`, compute `evidence_offset_` = majority of
  `(section_heading_pin_page(ch) + adjust − printed)` over recovered rows
  that have a section-heading pin (use the pin page, not the raw heading
  page, so the same ±1 rule applies); require a strict majority (more
  agreeing rows than any other offset, and ≥2 agreeing rows). No majority
  → no run-on pins from this fallback.
- [x] 3.2 In the run-on pin loop (`_pipeline.py:624-645`): allow the pin
  when `ch in provisional_pins_` even though `ch in chapter_first_pg` —
  i.e. replace the provisional pin instead of skipping; keep skipping for
  chapters pinned by anchors/body-title/scans. Same for the ToC-listing
  reconciliation tier (`_pipeline.py:471-530`): its pins may replace
  provisional pins under the same rule. Deliberate precedence change: ToC
  printed-page evidence outranks ±1 section-heading pins; anchors remain
  fuzzy-fill only.

## 4. Scan guards (`_pipeline.py`, `_structure_mixin.py`)

- [x] 4.1 Add a `_dot_leader_page(chunks_on_page)` helper: a page is
  ToC-like when ≥60% of its non-empty chunk lines end in 1–4 digits or
  contain `..{2,}` leaders; export for reuse.
- [x] 4.2 Body-title scan (`_pipeline.py:283-340`): refuse a match whose
  following text contains `on page \d+` (mirror the section scan's guard
  at line ~749).
- [x] 4.3 Section-number scan (`_pipeline.py:721-759`) and loose-digit scan
  (`_pipeline.py:761-806`): skip ToC-like pages per 4.1 (defense in depth;
  the evidence tier leaves them nothing to pin in the reference doc).

## 5. Token-granular heading anchors (`rag/pipeline/_structure_mixin.py`)

- [x] 5.1 In `_heading_title_anchors`'s match logic, require every
  title token (case-folded, whitespace-squashed) to appear as a whole
  token in the heading text, with token-count slack ≤ +2 (version
  suffixes like "…Release 7" vs "…Release 7.2"). Keep the existing
  glued/spaced squash comparison paths working.
- [x] 5.2 Update `test_toc_pin_respects_heading_anchor_precedence` and add
  a companion asserting the NEW order (ToC pin replaces a provisional
  section-heading pin; anchor does not).

## 6. Enumeration completeness + prompt

- [x] 6.1 `_pipeline.py` after ranges are built (~line 962): for every
  target roster chapter missing from `chapter_ranges_`, insert
  `(0, -1)` — an empty range yields an empty bucket and the existing
  placeholder path (`_fallback_mixin.py:475-494`) emits the note. Verify
  bucket collection, round-robin merge, and `single_section_mode` handle
  the empty range without touching boundary computation (`chapter_first_pg`
  stays the boundary source).
- [x] 6.2 `config/rag.py` rule 12: drop the hard-coded "21" — require
  enumerating every chapter present in the context, whatever the number.

## 7. Tests — multi-document generality matrix

New fixtures live beside the existing harness patterns
(`tests/unit/rag/test_pipeline.py`, `tests/unit/rag/test_pipeline_iterative.py`,
`tests/test_document/test_fast_text_gaps.py`). Each fixture is a synthetic
storage shape; no fixture may encode VirtualBox-specific strings beyond the
archetype. Mark the new tests `unit` (default marker set applies).

- [x] 7.1 fast_text: bare footer `"29"` parses; `"78 / 634"` parses as 78;
  `"iii"`, `"1 About Oracle VirtualBox"`, `"Loading 42%"` rejected;
  offset-0 majority `{"25":"25","26":"26","27":"27"}` → 0; mixed roman
  front matter + digit body → digit majority; existing consistent-offset
  cases unchanged.
- [x] 7.2 Archetype `offset0-bare-footers` (this manual's shape:
  bare footers, banner-less openers, ToC rows as body chunks, `N.1`
  headings, cross-reference sentence trap, license headings): end-to-end
  pin test — all chapters pinned within ±1 of truth; scans pin nothing
  spurious; ranges disjoint and ordered.
- [x] 7.3 Archetype `printed-offset-footers`: footers `"N / M"` with
  printed ≠ physical; ToC pins land at printed + offset (exact-evidence
  override verified).
- [x] 7.4 Archetype `footerless-evidence`: no nav chunks; recovered rows +
  `N.1` headings agree on a constant offset → pins; conflicting offsets →
  no ToC pins, interpolation/placeholder still produce complete output.
- [x] 7.5 Archetype `all-caps-headings`: ALL-CAPS opener headings match
  roster titles; "REFERENCES"-style license headings do not anchor;
  sentence-like headings do not anchor.
- [x] 7.6 Archetype `magazine-openings` (ML4T `[ 591 ]` marker shape):
  `_detect_chapter_openings` behavior unchanged (existing tests stay
  green; add one end-to-end with the evidence tier present).
- [x] 7.7 Archetype `glued-toc-pve`: run-on row shapes from the PVE
  comments still recover and pin (existing tests stay green).
- [x] 7.8 Archetype `unnumbered-tail-chapters`: tail chapters without
  `N.1` sections (e.g. licensing/appendix) rely on anchors/interpolation
  and, when they get no range, appear as placeholders — output enumerates
  the full roster.
- [x] 7.9 Guard tests: dot-leader page classification (threshold edges),
  `on page N` refusal in body-title scan, ToC-like page skip in section/
  loose-digit scans, front-matter floor in the evidence tier.
- [x] 7.10 Prompt: rendered `rag_system_prompt` contains no hard-coded
  chapter count.

## 8. Verification

- [x] 8.1 `ruff check . && ruff format --check .` and `mypy .` clean for
  touched files.
- [x] 8.2 Full fast suite green: `pytest -m "not integration and not chaos"`.
- [x] 8.3 Live end-to-end against the real ingested manual (read-only,
  LLM stubbed): rerun `/tmp/opencode/diagnose_chapters.py` with
  `PYTHONPATH=<worktree>/src` and the main repo venv — expect all 18
  chapters enumerated, ranges covering each chapter's true opener region
  (±2 pages of the `N.1` table above where no ToC row refines), no
  placeholder for chapters with real content, and correct per-chapter
  content in the stub window samples (ch7 → Guest Additions content @103+,
  ch15 → VBoxManage content @271+, ch16/17/18 → their real bodies).
- [x] 8.4 Record before/after ranges and bucket page spans in the task
  notes below.

## Task notes (evidence)

### 8.1 Lint / types

- `ruff check` and `ruff format --check` clean on all touched files
  (`src/secondbrain/document/fast_text.py`, `src/secondbrain/config/rag.py`,
  `src/secondbrain/rag/pipeline/_pipeline.py`,
  `src/secondbrain/rag/pipeline/_structure_mixin.py`,
  `tests/unit/rag/test_pipeline.py`,
  `tests/test_document/test_fast_text_gaps.py`).
- `mypy` clean on the four touched source files (one `cast` added in the
  dot-leader-classification block to match the `ChunkInfo` protocol type, as
  at the existing appendix-sweep call site). `tests/` is excluded from mypy
  by `[tool.mypy] exclude` in `pyproject.toml`, matching repo policy.

### 8.2 Test counts

- Targeted suite
  (`tests/test_document/test_fast_text_gaps.py tests/unit/rag/test_pipeline.py
  tests/unit/rag/test_pipeline_iterative.py`): baseline 281 passed →
  320 passed (39 new tests, 0 regressions).
- Full fast suite (`pytest -m "not integration and not chaos"`): baseline
  3501 passed / 1 failed / 3 skipped → after 3540 passed / 1 failed /
  3 skipped. The single failure
  (`tests/test_storage/test_qdrant_listing.py::TestListChunks::test_source_filter_matches_text_tokens`,
  qdrant-local `MatchText` tokenization) was confirmed identical at baseline
  by re-running with this change's diff stashed — pre-existing environment
  issue, untouched by this change (`git status`: no storage paths modified).

### 8.3 Live verify

- `PYTHONPATH=<worktree>/src /home/bchand/secondbrain/.venv/bin/python
  /tmp/opencode/diagnose_chapters.py` → `/tmp/opencode/after_fix_diagnose.txt`
  (byte-identical re-run of `/tmp/opencode/after_diagnose.txt` after the
  final anchor-needle adjustment, i.e. the adjustment is behavior-neutral on
  the live book). All 18 chapters enumerated with real titles; no
  placeholder notes; window samples carry each chapter's real content
  (ch7 → Guest Additions @103-105, ch15 → VBoxManage @271-273, ch16 →
  Reference @468-469, ch17 → Change Log @475-477, ch18 → Licensing/Release 7
  @480-483).
- Tier outcome on the live book: 11 chapters refined by run-on ToC rows
  ("Pinned chapter N … via run-on ToC row (printed P + offset 0)" for
  2, 3, 7, 8, 9, 10, 11, 12, 14, 15, 17); the other 7 keep their
  section-heading evidence pins (1, 4, 5, 6, 13, 16, 18), all of which
  equal the final range starts. The 3.1 evidence-offset fallback was not
  needed live (the 1,222 agreeing nav footers resolve offset 0 first); it is
  exercised by the footerless archetype tests (7.4).

### 8.4 Before/after ranges and bucket page spans (live UserManual.pdf)

- Before: `{1:(3,3), 5:(4,4), 6:(5,21), 7:(22,22), 8:(23,23), 15:(24,598),
  16:(599,658), 17:(659,947), 18:(948,∞)}` — 9 chapters detected, all wrong.
- After: `{1:(20,28), 2:(29,42), 3:(43,45), 4:(46,49), 5:(50,87),
  6:(88,102), 7:(103,124), 8:(125,142), 9:(143,160), 10:(161,174),
  11:(175,234), 12:(235,235), 13:(236,262), 14:(263,270), 15:(271,467),
  16:(468,474), 17:(475,479), 18:(480,∞)}` — all 18 chapters, every start on
  the `N.1` table in the header (exact for 15 of 18; 4→46 vs 4.1@47,
  13→236 vs 13.1@237, 16→468 vs 16.1@469 all within the ±1 evidence
  contract, later refined where run-on rows existed).
- Stub summarize-window page spans (sampled from the buckets): ch1
  [21,22,23], ch2 [29,30,31], ch3 [43,44,45], ch4 [47,48,49], ch5
  [50,51,52], ch6 [89,90,91], ch7 [103,104,105], ch8 [125,126,127], ch9
  [143,144,145], ch10 [161,162,163], ch11 [175,176,177], ch12 [235], ch13
  [237,238,239], ch14 [263,264,265], ch15 [271,272,273], ch16 [468,469],
  ch17 [475,476,477], ch18 [480,481,482,483].

### Sanctioned existing-test edits (all documented per the change contract)

- 5.2 (`tests/unit/rag/test_pipeline.py:4554`): docstring added to
  `test_toc_pin_respects_heading_anchor_precedence`; body untouched.
- 5.2 companion (`tests/unit/rag/test_pipeline.py:4586`): new
  `test_toc_listing_replaces_provisional_evidence_pin` in the existing
  `TestToCListingResolution` class.
- 7.1/1.2 (`tests/test_document/test_fast_text_gaps.py:190`):
  `test_printed_above_physical_skipped` renamed with its fixture moved to
  `"98 / 634"` so the same printed>physical refusal now rides the new
  `/total`-suffix stamp shape.
- 6.1 (`tests/unit/rag/test_pipeline.py:4222`): existing
  `test_degenerate_interp_gap_skips_duplicate_pin` adjusted for the
  sentinel-range semantics (empty range yields an empty bucket, roster line
  without a page claim).

### Additional necessary artifact update

- `tests/snapshots/assembled_prompt.txt` regenerated: the golden file pins
  the full prompt text, and the spec-mandated rule-12 rewrite
  (`config/rag.py`) intentionally changes one sentence of it
  ("If the context contains 21 chapters, your answer must name all 21." →
  "Enumerate every chapter present, whatever the total count."). All
  structural-marker assertions (`test_golden_prompt_carries_structural_markers`)
  still pass; only the rule-12 sentence changed.

### 5.1 implementation note

- The token walk itself (`_heading_tokens_admit_suffix`) proved correct; the
  new granularity test exposed that the roster-title prep's trailing
  page-number strip (`\s+\d{1,4}\s*$`) truncated version titles
  ("Networking Release 7" → "Networking Release") before the walk, letting
  "…Release 7.2 subnets" through on two-token slack. Fix: the walk needle
  falls back to the un-truncated spelling whenever the heading extends past
  the trailing token, so the dot-segment rule admits "…Release 7.2" but
  refuses "…Release 7.2 subnets". Live-verify neutral (see 8.3).

