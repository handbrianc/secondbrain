# Anthology-Aware Chapter Summarization — Tasks

## Fixtures and baselines (before any code change)

- [x] 1. Export corpus chunk fixtures from the live store to
  `tests/fixtures/chapter_map/` (user-manual, pve-admin-guide, hcd-report,
  knowledge-compilation; fields: chunk_text, page_number, page_pos,
  chunk_role, element_type, source_file)
- [x] 2. Record pre-change baselines in
  `tests/fixtures/chapter_map/baselines.json`: legacy chapter ranges + bucket
  first-chunk pages for the three reference documents, N.1 evidence pins, and
  evidence-pin divergence scores per document (gate calibration input)

## Detection and routing

- [x] 3. Add the multi-signal anthology shape detector
  (`_structure_mixin.py`): ≥3 part-opener headings, ≥2 numbering restarts,
  minimum scale; returns part-opener pages or None
- [x] 4. Route in `_iterative_query`: after source selection, claimed
  documents take the anthology branch before any roster/pinning work;
  unclaimed documents proceed byte-identically

## Anthology path

- [x] 5. Build per-part maps in `_pipeline.py`: part ranges from opener
  pages, per-part section roster/pins from heading chunks inside the part,
  per-part body buckets (page-cap sampling constants as legacy)
- [x] 6. Add `_generate_anthology_summary(parts)` and
  `_generate_whole_document_overview(chunks)` in `_fallback_mixin.py`,
  reusing `_split_bounded` / `_summarize_bounded` / `_on_chunk` streaming;
  parts contract per design.md §2

## Agreement gate

- [x] 7. Add the gate after legacy range derivation: compare final range
  starts against `evidence_pin_pg_` (±2 pages), run only when ≥ 4 chapters
  are comparable, veto below the calibrated threshold → whole-document
  overview fallback; gate may not modify pins or ranges

## Rider

- [x] 8. Extend the bare-chapter title capture class with `"` (and typographic
  quotes) so quoted phrases survive in roster titles

## Tests

- [x] 9. Detector tests: positive (compilation fixture, synthetic anthology),
  negative (user-manual, pve fixtures)
- [x] 10. Per-part map tests: 16 parts with correct boundaries
  (3/13/22/37/61/66/73/77/81/86/91/95/101/106/109/115, last end 120);
  section pins inside parts (I.1 §5 @p7)
- [x] 11. Gate tests: reference books pass; synthetic disagreeing map vetoes
  to overview fallback; document without N.1 evidence skips the gate
- [x] 12. Characterization tests: reference books' legacy ranges match
  `baselines.json` after the change
- [x] 13. End-to-end `_iterative_query` tests: compilation fixture streams
  per-part summaries (no placeholders, no cross-part content); single-book
  fixture keeps legacy enumeration

## Validation

- [x] 14. `openspec validate add-anthology-aware-chapter-summarization`
- [x] 15. `ruff check . && ruff format --check .` and `mypy` on touched files
- [x] 16. Fast suite: `pytest -m "not integration and not chaos"` green
- [x] 17. Replay harness against the live store: compilation summarizes
  per-part; `summarize UserManual.pdf` chapter map and prompt transcript
  unchanged
