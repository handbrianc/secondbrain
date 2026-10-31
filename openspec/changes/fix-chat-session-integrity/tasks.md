# Tasks

## 1. Service observability foundations (logging package + slow-call helper)

- [x] 1.1 In `src/secondbrain/logging/`, add a `timed_external_call(operation, target)` contextmanager that emits a WARNING (operation, target, elapsed seconds) when elapsed exceeds a threshold (default 10 s, env `SECONDBRAIN_SLOW_CALL_SECONDS`), with unit tests covering under-threshold silence, over-threshold warning, and env override; verify `pytest tests/unit/logging -q` green
- [x] 1.2 In `setup_logging` (`src/secondbrain/logging/__init__.py:112-173`), default to a `RotatingFileHandler` at `~/.secondbrain/logs/secondbrain.log` (10 MB, 5 backups), keep `SECONDBRAIN_LOG_FILE` as path override, add `SECONDBRAIN_LOG_DISABLE_FILE=1` suppression, keep console behavior unchanged; unit tests for default-on, override, and disable paths (tmp_path home), verify green
- [x] 1.3 Wire the helper at shared external-call sites — LLM provider requests (`src/secondbrain/rag/llm/`), embedding client (`src/secondbrain/embedding/`), Qdrant calls (`src/secondbrain/storage/`) — and add per-site tests (monkeypatched clock + captured records); verify the touched suites green

## 2. Per-source chapter/section resolution, window purity, attribution (rag-pipeline)

- [x] 2.1 Add a source-scoped lookup in `src/secondbrain/storage/structure_sqlite.py` (trees carrying a chapter/section node with a given number, per source) with unit tests on a seeded store; verify green
- [x] 2.2 In `_iterative_query` (`src/secondbrain/rag/pipeline/_pipeline.py:371`, unscoped pick `:468-475`, legacy path `:491-521`) and `_structure_mixin.py` (`_guarded_tree_chapter_map` `:2442-2546`, `find_chunks` `:2485-2508`): replace the single max-chunk document pick with per-source resolution for colliding numbers (source mention still shortcuts via `_resolve_source_filter`); enforce single-source window purity at assembly (source-aware `find_chunks`); tests: two seeded sources with colliding chapter 15 → per-source windows, no cross-source chunk admitted, unique number resolves directly; verify green
- [x] 2.3 Part-level attribution in context formatting (`src/secondbrain/rag/pipeline/_formatting_mixin.py`): per-source parts carry a "Source: <file>" part header, per-line tags unchanged; single-source output byte-identical to today; tests in `tests/unit/rag/` alongside the `fix-chunk-heading-context` format tests; verify green

## 3. Capture-side ToC ghost suppression + physically-consistent recovery (document-structure)

- [x] 3.1 In `capture_docling_headings` (`src/secondbrain/document/structure_capture.py:857-936`): suppress heading candidates whose physical page lies inside the detected ToC page span AND whose normalized text matches a ToC listing row (reuse `_pdf_toc_listings` `:1725-1783`); record suppressed candidates in `structure_meta` (`suppressed_toc_headings`); tests with a synthetic docling parse carrying ToC-page headings + a body heading (ghost dropped, real chapter kept); verify green
- [x] 3.2 In `recover_chapter_numbers` (`src/secondbrain/document/structure_capture.py:1962-2100`): map printed listing pages through page labels, derive the offset from usable labels (fallback: median of matched siblings), assign only within the 3-page plausibility tolerance, refuse colliding assignments; tests: printed-153→physical-163 assignment to the real node, ghost-range node refused, no-collision invariant; verify green
- [x] 3.3 Cross-check with the runtime guard: a tree captured with suppression + recovery yields a full chapter map via `_guarded_tree_chapter_map` (integration-style unit test with the seeded store); verify green

## 4. Audio ingest observability + coherent worker wait bound (document-ingestion)

- [x] 4.1 In `src/secondbrain/document/ingestor/_sync.py` (and mirrored `_async.py`), wrap the audio stages (decode, transcription, topic segmentation, chunking, embedding) with stage-timing logging (INFO on completion, WARNING past `SECONDBRAIN_SLOW_STAGE_SECONDS` default 60 s, file identified via request-ID context, failure logs stage + elapsed before surfacing); tests with monkeypatched stage callables; verify green
- [x] 4.2 Make the worker wait stage-aware (`future.result(timeout=300)` at `_sync.py:1225`, mirror in `_async.py`): audio transcription bound = base model-load + per-second factor × duration × window count, floor 900 s, override `SECONDBRAIN_TRANSCRIPTION_WAIT_SECONDS`; expiry logs stage, bound, elapsed at WARNING; tests: short clip with slow model build consumes result without spurious timeout; genuine expiry is attributable; verify green

## 5. Cross-lane verification and change bookkeeping

- [x] 5.1 `ruff check . && ruff format --check .`, `mypy .`, and `pytest -m "not integration and not chaos"` all green on the combined tree; fix cross-lane fallout only (no scope creep)
- [x] 5.2 `openspec validate fix-chat-session-integrity --strict` passes; record verification notes (commands + outcomes, including that no live Qdrant/SQLite writes occurred) in `openspec/changes/fix-chat-session-integrity/verification.md`
