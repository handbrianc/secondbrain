# Tasks

## 1. Heading plausibility predicate (chunker)

- [x] 1.1 Add `is_plausible_heading(text)` to `src/secondbrain/document/chunker.py` (numbered prefix always passes; else `< 120` chars, no trailing `.`, `:`, `,`, `;`, `—`, no `" - "` substring) and export it from `secondbrain.document`; verify with `python -c "from secondbrain.document.chunker import is_plausible_heading"` and targeted asserts ("19.2 pveperf" True, "Restart chrony:" False, "pvesubscription - Subscription Management" False, "GENERAL BTRFS ADVANTAGES" True, "FSYNCS/SECOND" True)
- [x] 1.2 Add unit tests for the predicate in `tests/unit/document/` (numbered/caps/label/long/synopsis cases) and run them green (`pytest tests/unit/document -k plausible -x -q`)

## 2. Capture gate (structure)

- [x] 2.1 Apply the predicate in `capture_docling_headings` (`src/secondbrain/document/structure_capture.py`): docling-heading items failing it are skipped from node creation; outline part untouched; update module docstring; verify with the new + existing `tests/unit/document/test_structure_capture.py` green
- [x] 2.2 Add capture-gate tests (run-in label "Restart chrony:" creates no node; numbered heading creates one; outline-derived node is never gated) and run the structure-capture suite green

## 3. Label/definition pairing (chunk assembly)

- [x] 3.1 In `_merge_segments` (`src/secondbrain/document/chunker.py`), route `section_header`-labeled segments failing `is_plausible_heading` into the normal accumulation path (no standalone structural flush); drop the label on join so merged chunks carry no heading label; plausible headings and table/caption/toc/navigation labels keep current behavior; verify `pytest tests/test_document/test_chunking.py tests/test_document/test_labeled_chunking.py tests/unit/document/test_chunker_role_regression.py -x -q` green
- [x] 3.2 Add pairing tests (implausible label joins following text and lands in a `body` chunk; plausible label stays standalone structural with byte-identical text; unlabeled streams byte-identical) and run them green

## 4. Ordered sticky inheritance (annotation)

- [x] 4.1 Extend `annotate_chunks` in `src/secondbrain/document/structure_annotate.py` with `ordered=False` kwarg and the sticky-owner rule (page mode only; containment re-checked; anchors update the owner; unordered behavior byte-identical); update module docstring; verify existing `tests/unit/document/test_structure_annotate.py` green unchanged (default path)
- [x] 4.2 Add ordered-mode tests (same-page siblings: unanchored body inherits sticky owner; oscillating page falls back to conservative rule; audio time-mode unaffected; unordered call still bails) and run them green
- [x] 4.3 Add the ordered-mode most-recent-start fallback (design D2 rule 3, from the 2026-10-27 live-verification finding: stored coverage 23.8% vs 87.1% full-stream while the bail remained): an unanchored page-mode chunk with candidates but no applicable sticky owner inherits the candidate with greatest (start, level, reading index); the conservative bail applies to unordered callers only; extend ordered-mode tests (no sticky owner → most-recent-start candidate; unordered call still bails; add-only contract) and run them green

## 5. Callers: fresh ingest + refresh

- [x] 5.1 Pass `ordered=True` at the fresh-ingest annotation site in `src/secondbrain/document/processor.py`; verify `tests/unit/document` + `tests/test_document` green
- [x] 5.2 Rework `refresh_structural_payload`/`_annotated_refresh_points` in `src/secondbrain/storage/qdrant.py` per design D3 (payload-only scroll of `is_empty(node_id)` points, sort by `(page_number, page_pos, chunk_id)`, one ordered annotate pass, batched `set_payload` by explicit ids with only present `ANNOTATION_PAYLOAD_KEYS`, no vector round-trip, points resolving no node left untouched); update the mock backend's refresh path to match semantics; verify refreshed mock points equal fresh-ingest annotations for the same chunks
- [x] 5.3 Update/extend wiring tests (`tests/unit/document/test_structure_refresh_wiring.py`, `tests/unit/document/test_structure_worker_wiring.py`, plus the qdrant refresh tests) for the ordered refresh and run them green
- [x] 5.4 Revise the refresh to annotate the document's FULL point set (design D3 revision, same finding: an `is_empty(node_id)`-filtered subset lacks heading anchors, so sticky inheritance never engages): payload-only scroll of all points, sort by `(page_number, page_pos, chunk_id)`, one ordered annotate pass, batched `set_payload` grouped by identical annotation, written only for points whose stored annotation keys are missing or differ (corrects stale annotations against an older tree; idempotent no-op otherwise); update refresh tests (full-set read, diff-gated writes, stale-annotation correction, no vector reads) and run them green

## 6. CLI ingest summary pluralization

- [x] 6.1 Pluralize the summary lines in `src/secondbrain/cli/ingest.py` (success/skipped/failed: "1 file" / "N files"); add/extend a CLI output test asserting "1 file" and "2 files"; run that test green

## 7. Full validation

- [x] 7.1 Run `ruff check . && ruff format --check .` and `mypy` on the touched packages; fix findings
- [x] 7.2 Run the fast suite `pytest -m "not integration and not chaos"` green
- [x] 7.3 Run `openspec validate fix-chunk-heading-context --strict` and mark tasks complete
- [x] 7.4 Re-ingest the PVE guide PDF and verify with the analysis scripts: body-chunk `heading_path` coverage ≥95% (from 76.7% missing), "FSYNCS/SECOND" no longer parented under "pvesubscription - Subscription Management", the §19.2 FSYNCS/SECOND > 200 definition chunk carries the §19.2 heading path, and the §9.6 `pvesr create-local-job` chunk still carries the full command; record numbers in the change's verification notes
