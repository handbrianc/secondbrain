# Design

## Context

Recon anchors (2026-10-29, all verified in-repo):

- **Unscoped document pick**: `_iterative_query` (`src/secondbrain/rag/pipeline/_pipeline.py:371`) picks the tree source by max body-chunk count for unscoped chapter/section queries (`:468-475`, legacy path `:491-521`); a source mention scopes it only via `_resolve_source_filter` (`_routing_mixin.py:227-236`), called from `_orchestration.py:81/252/525/666`. `chapter_id` values (`"15"`) are numbers, so sources collide.
- **Runtime guard exists**: `_guarded_tree_chapter_map` (`_structure_mixin.py:2442-2546`) already filters ToC-span nodes at query time (archived `fix-chapter-coverage`); the stored tree itself stays polluted.
- **Ghost origin**: `capture_docling_headings` (`structure_capture.py:857-936`) turns ToC-page `SectionHeaderItem`s into chapter nodes; `is_plausible_heading` (`chunker.py:302-327`) passes anything with a numbered prefix; ToC listings/page-run machinery already exists (`_pdf_toc_listings` `:1725-1783`, `_longest_paged_run` `:1696-1722`); `recover_chapter_numbers` (`:1962-2100`) matches titles but never validates the printed→physical page mapping (real Ch 7: printed 153 → physical 163 via PageLabels; ghosts sit on pp. 9–22 with `number` set, real nodes `number=None`).
- **Audio path**: `ingestor/_sync.py` orchestrates; worker result wait is a flat `future.result(timeout=300)` (`:1225`) sized for text extraction; observed audio stage: 408 s transcription (WhisperS2T model build per fresh pool worker, `docling_factory.py:655-764`) + LLM topic segmentation via the shared LiteLLM endpoint; total 6m48s for a 9.9 s clip, zero observability.
- **Logging**: `setup_logging` (`logging/__init__.py:112-173`) attaches a file handler only when `SECONDBRAIN_LOG_FILE` is set; sole call site `cli/__init__.py:43`; request-ID context exists in `utils/tracing.py`.

Constraints: tests/fixtures only during verification (no live Qdrant `embeddings` collection or `~/.secondbrain/secondbrain.db` writes); ruff complexity rules intentionally off; pytest xdist `-n auto --dist=loadfile`.

## Goals / Non-Goals

**Goals:**

- Multi-source collections never silently answer a numbered chapter/section query from the wrong source.
- Capture stops minting ToC ghost nodes; recovery only assigns physically-consistent numbers.
- Audio ingest leaves a per-stage timing trail and never spuriously times out a live transcription worker.
- A default rotating file log + threshold slow-call WARNINGs make stalls attributable without debug env vars.

**Non-Goals:**

- Re-ingesting or repairing the user's live collection (existing trees heal on next backfill re-ingest; the runtime guard shields query behavior meanwhile).
- Reworking the runtime guard or anything covered by `fix-chapter-bucket-sampling` / `fix-chunk-heading-context` (in-flight, implemented).
- New CLI commands or schema migrations; embedding regeneration.
- General heartbeat/progress streaming for all workers (only the audio wait bound is made coherent).

## Decisions

**D1 — Per-source resolution defaults to per-source results, not an interactive prompt.**
For an unscoped numbered query, the pipeline asks the structure store which sources carry a tree node with that number (new source-scoped lookup in `storage/structure_sqlite.py`), then builds each matching source's chapter/section window and formats them as separately labeled parts. A resolved source mention shortcuts to that one source (existing `_resolve_source_filter`). The ambiguity prompt remains the fallback for surfaces that cannot merge parts (e.g. page-number lookup). *Alternative considered*: always prompt on collision — rejected; an interactive stop on a common question ("summarize chapter 5") is worse than an attributed multi-part answer, and the spec admits either with attribution.

**D2 — Attribution at part level, not per source line.** Each per-source part gets a part header ("Source: <file>") in formatted context; per-line tags stay untouched. This avoids format churn against in-flight `fix-chunk-heading-context`, which already appends `heading_path` to per-line tags. *Alternative*: source in every per-line tag — rejected as redundant after window purity guarantees single-source windows.

**D3 — Window purity enforced at assembly.** The chapter/section window assembly in `_structure_mixin.py` filters admitted chunks by the window's source file (`find_chunks` `:2485-2508` gains a source argument); chunks lacking source metadata keep today's single-collection behavior. *Alternative*: post-hoc drop in formatting — rejected; filtering at assembly keeps window statistics (coverage notes) honest.

**D4 — Ghost suppression = (page inside ToC span) AND (text matches a ToC listing row).** At capture, `capture_docling_headings` drops candidates meeting both conditions, using the existing listing extraction (`_pdf_toc_listings`) and title normalization; suppressed candidates are recorded in `structure_meta` (`suppressed_toc_headings`). A page-inside-span test alone is too eager (front-matter headings); a text-match test alone re-admits ghosts when pages are mis-parsed. Real chapters start at/after the ToC span's end and survive. *Alternative*: fix at merge time — rejected; capture has both signals in hand and the merge path stays simpler.

**D5 — Recovery maps printed pages through PageLabels; offset derived, never assumed.** `recover_chapter_numbers` computes the printed→physical offset from documents that have usable page labels; where the outline lacks page-anchored evidence, it derives the offset from sibling-listing consistency (median offset of matched nodes) instead of a constant. Assignment requires the node's physical range to be consistent with the mapped page within the existing plausibility tolerance (3 pages), and refuses on collision — even with a number freed by ghost suppression. *Alternative*: fixed offset per document — rejected; PageLabels semantics vary (observed offset 10, but run-on offsets are a known hazard per the rag-pipeline spec's "Run-on ToC offset validates against body evidence").

**D6 — Audio wait bound derived per file kind.** The executor wait in `ingestor/_sync.py` (mirrored in `_async.py`) becomes stage-aware: text tasks keep the current 300 s; audio transcription gets `base_model_load + per_second_factor × audio_duration × window_count`, floored generously (e.g. ≥ 900 s), configurable (`SECONDBRAIN_TRANSCRIPTION_WAIT_SECONDS` override). Rationale: the 408 s observation is dominated by a one-time model build per fresh pool worker; a duration-scaled bound with a floor covers it without heartbeat plumbing. *Alternative*: worker heartbeats — rejected as cross-process signaling overkill for this change.

**D7 — Stage timing instrumented at the ingestor call sites, not inside capture.** `_sync.py`/`_async.py` wrap each audio stage call (transcription, topic segmentation, chunking, embedding) with a small timing helper from the new logging module; `structure_capture.py` stays untouched by this area. Slow-stage threshold defaults to 60 s (env-overridable `SECONDBRAIN_SLOW_STAGE_SECONDS`); logs carry the file name and reuse the request-ID context. *Alternative*: instrument inside capture functions — rejected; keeps write scopes disjoint from the document-structure lane.

**D8 — Slow-call instrumentation at the shared client layer.** A `contextmanager` helper (`timed_external_call(operation, target)`, threshold default 10 s, env `SECONDBRAIN_SLOW_CALL_SECONDS`) wraps LLM provider, embedding-client, and Qdrant call sites (`rag/llm/**`, `embedding/**`, `storage/qdrant*`). Calls that bypass the shared client are still covered at stage level by D7. Emits WARNING regardless of log level; includes operation, target, elapsed.

**D9 — Default rotating file log in `setup_logging`.** Default destination `~/.secondbrain/logs/secondbrain.log`, `RotatingFileHandler` (10 MB × 5 backups); `SECONDBRAIN_LOG_FILE` overrides the path; `SECONDBRAIN_LOG_DISABLE_FILE=1` suppresses; console behavior unchanged. Thresholds/paths as env-overridable constants co-located in the logging package rather than new typed-config surface — logging concerns stay in the logging package and avoid config-model churn in this change.

## Risks / Trade-offs

- [Per-source resolution multiplies LLM calls when many sources share a number] → windows build only for sources whose tree carries the number (rare: typically 1–2); existing token budget guards in formatting apply per part.
- [Ghost suppression eats a real chapter] → suppression requires both conditions (span + listing match); candidates recorded in `structure_meta` for audit; runtime guard unaffected; unit tests pin real-chapter survival.
- [Derived recovery offset wrong for odd PageLabels] → consistency-derived median offset + 3-page tolerance + collision refusal; unmatched nodes stay number-less (spec'd), worst case is today's behavior minus ghosts.
- [Wait-bound floor wastes 15 min on a truly hung worker] → floor configurable; expiry now names stage/bound/elapsed (attributable), and stage WARNINGs show liveness before expiry.
- [Default file log grows disk] → rotation caps (10 MB × 5); disable switch; only CLI processes write it.
- [Slow-call wrapper overhead] → monotonic clock + one conditional log record; negligible vs network calls.
- [In-flight spec collisions at archive] → D2/D7 deliberately avoid per-line-format and capture-file churn; reconciliation notes in proposal Impact.

## Migration Plan

No schema or API migration. Deploy = code change only; existing polluted trees keep their ghosts until a user backfill re-ingest (runtime guard shields queries meanwhile); new log directory appears on first CLI run. Rollback = revert; log files under `~/.secondbrain/logs/` are inert leftovers.

## Open Questions

None. Defaults (thresholds, rotation size, per-source-vs-prompt) are decision D1/D8/D9 with env overrides; none change specs or task breakdown.
