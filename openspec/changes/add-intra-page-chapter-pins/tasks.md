# Tasks

## 1. Derivation claim channel (`_structure_mixin.py`)

- [x] 1.1 Pass-1 and pass-2 claim recording: at each roster claim, record (page_number, page_pos, match char offset, half = `char_offset < len(text)/2`); return the claim map as a fourth element; update both call sites (`_pipeline.py:526-528`, `scripts/audit_chapter_summaries.py`) — *deviation: the map travels on the instance as `self._chapter_claims` instead of a 4-tuple return; `_derive_chapter_numbers` keeps its 3-tuple return because ~24 test call sites and monkeypatched doubles unpack it positionally (see proposal deviation note)*
- [x] 1.2 Tail-deferral: matches with `bm.end(2) >= len(raw)` collect into a pending list and claim post-scan only if the number is still unclaimed (same guard chain re-run) — *refined empirically: defer only when `bm.end(2) >= len(raw) and bm.start() > 0`; a match at the chunk's very start is a standalone heading emission and must claim in-loop (pve ch1 regression)*
- [x] 1.3 Carve-out rescue: "the" + dot-shaped admits without colon unless `_LICENSE_TITLE_RE` (new module-level sentence-case license vocabulary regex) matches; colon-bearing shape unchanged; verify with a direct probe that ch4 claims and the 12 observed license shapes stay rejected
- [x] 1.4 Unit tests for 1.1–1.3 (claim map shape, half computation, ch4 title, license rejects, tail deferral with the "7. The IDEO" fragment); `pytest tests/unit/rag -q` green *(new module green; corpus-wide green lands with the task-3 baseline regen — legacy hcd expectations fail until then, by design)*

## 2. Pin, cut, range assembly (`_pipeline.py`)

- [x] 2.1 Claim pin tier (fill-only, D3 guards) after the loose-digit rescue; ch1–3 pin at 2/3/4 in the fixture
- [x] 2.2 Cut map construction (D4) after monotone selection, with `before_contains` from pre-extension ranges
- [x] 2.3 Range extension rule (D5) after `source_chapter_ranges_`; sentinel recovery replacing `(0, -1)` for claimed chapters in the sentinel block
- [x] 2.4 Shared `_chunk_chapter_owner(page, ppos)` helper + cut-aware admission in both the single-section and round-robin bucket loops, with owner-verification fallback to first-range-wins
- [x] 2.5 Unit tests: cut admission for the five hcd pairs asserted against the live-oracle table (page 4, 5, 6, 10–11, 12–13, 13–14, 14), extension/sentinel recovery, fallback path; `pytest tests/unit/rag -q` green *(new module green incl. the 13-page oracle table; corpus-wide green lands with the task-3 baseline regen)*

## 3. Baselines and corpus reconciliation

- [x] 3.1 Regenerate the hcd-report baseline section (ranges, keys, bucket_pages, titles) from the post-change derivation in the export tool's exact format; classify every diff against the design's expected table — anything unexplained is a defect, not an update *(via /tmp/opencode/regen_hcd_pins.py: ranges hard-asserted == corrected design table; buckets classified as capped window subsets oracle-consistent on all 9 live pages; round-trip byte-identical; other three books canonical-identical; the 5 pending tests flip green)*
- [x] 3.2 Review knowledge-compilation's diff (six new carve-out claims) and user-manual/pve (expect byte-identical); confirm the anthology veto still fires and the calibration tests stay green *(actual: KC roster byte-identical — the ~6 regex-level predicted claims die on the full guard chain (0 new claims); veto intact (16 part headings, 0 legacy headings, no note); user-manual 18/18 + pve 20/20 rosters and baselines byte-identical; calibration green)*
- [x] 3.3 `pytest tests/unit/rag tests/unit/document -q` green *(tests/unit/rag: 717 passed + the 5 baseline tests now green = 722; tests/unit/document: 483 passed)*

## 4. Acceptance

- [x] 4.1 Lint + types on touched files: `ruff check`, `ruff format`, `mypy` *(ruff check: all clean incl. the 4 A-touched files; ruff format: 3 files already formatted; mypy: both in-gate pipeline files clean — `scripts/audit_chapter_summaries.py` carries only 3 pre-existing monkeypatch-pattern notes, and `scripts/` is outside the project mypy gate)*
- [x] 4.2 Full fast suite `pytest -m "not integration and not chaos" -q` green *(4562 passed, 3 skipped, 0 failed, 57 s; +35 over the prior recorded baseline = this change's 27 + B's 8 new tests)*
- [x] 4.3 Live: one enumeration replay of the hcd report (tree-driven path) answers unchanged (21/21 chapters, clean titles); record the legacy-vs-live split comparison in `verification.md` *(exit 0; ch19 full tree title marker present, no coverage note; split comparison recorded)*
- [x] 4.4 Write `verification.md`; `openspec validate add-intra-page-chapter-pins` green; update the knowledge todo
