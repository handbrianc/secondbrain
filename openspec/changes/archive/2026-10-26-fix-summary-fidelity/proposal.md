# Proposal

## Why

A chat-driven, per-chapter summary of `pve-admin-guide-9.1.pdf` (2026-10-24) surfaced three fidelity defects that silently degrade every document summary, verified against the stored session, the vector store, and the pipeline code:

1. **Chapter-window context bleed.** The Chapter 16 (Backup and Restore) window's source context was "mostly about HA/CRS, oddly" (the model's own reasoning). Verified: CRS (Cluster Resource Scheduler) chunks sit at pages 432–433 — the tail of Chapter 15 (High Availability, pp. 409–433) — and leaked into the Chapter 16 window at the boundary. The model coped ("summarize only what's given"), so the emitted Chapter 16 summary is quietly incomplete (container backup modes, scheduling, restore options missing) with no warning to the user.
2. **Inconsistent reasoning-display policy.** The guarded per-window path promises "reasoning is … never forwarded to the terminal" (`rag/pipeline/_streaming.py`), but the overview/reduce path forwards every reasoning delta to the CLI renderer (`rag/pipeline/_fallback_mixin.py`, `emit("", reasoning)`), which prints raw chain-of-thought as `▸ Thinking:` blocks inline in the answer. Users cannot tell reasoning from answer content.
3. **Corrupted table extraction feeds wrong numbers.** A stored chunk contains the literal text `5.26 minutes 99.9999` — the availability table of the same guide flattened into a misaligned row. Both summary runs on different days repeated the resulting falsehood ("99.9999% availability corresponding to 5.26 minutes of downtime"); the real pairing is 99.999% ≈ 5.26 minutes, 99.9999% ≈ 31.5 seconds. Every future query touching that table inherits the error.

## What Changes

- Chapter-summarization windows become range-faithful: source chunks are admitted only from the chapter's own page range (bounded boundary tolerance), and a chapter whose window is empty or dominated by foreign-range content is flagged to the user instead of silently summarized from the wrong material.
- One reasoning-display policy across all streaming paths: reasoning is rendered only as a distinct, collapsed visual element and never as part of the answer text; the stored session history contains the finalized answer text — equal to the displayed text on the happy path (byte-for-byte content-channel parity), while repair passes (leak-scrub, retry, finalize trims) may supersede already-streamed draft text, a documented divergence — so `chat --history` is a faithful record.
- Table content is serialized into chunk text with row structure preserved (cells bound to their row labels, tables never split mid-row), and degenerate table serializations are flagged at ingest instead of being silently stored.

## Capabilities

### New Capabilities

_None — all changes land in existing capabilities._

### Modified Capabilities

- `rag-pipeline`: new requirements for chapter-window context purity (range-faithful chunk admission, boundary bleed exclusion) and coverage-gap surfacing (foreign-dominated or empty chapter windows produce an explicit coverage note, mirroring the existing rangeless-chapter placeholder).
- `conversational-rag`: new requirements for streaming reasoning display (single policy across guarded and reduce paths; reasoning never interleaved into answer content) and a documented display↔storage contract (the reduce path streams live; the stored history text is the finalized answer, equal to the displayed text on the happy path with repair-path divergence documented).
- `document-ingestion`: new requirements for table serialization fidelity (row-label/value adjacency preserved in chunk text; no mid-row table splits; degenerate serializations flagged at ingest).

## Impact

- **Code:** `src/secondbrain/rag/pipeline/` (`_streaming.py`, `_fallback_mixin.py`, chapter-window assembly in `_pipeline.py`/`_orchestration.py`, `_leak_scrub.py`), `src/secondbrain/cli/chat_helpers.py` (`_ThinkingStream` renderer), `src/secondbrain/document/` (`chunker.py`, `docling_factory.py` table-structure options), `scripts/audit_chapter_summaries.py` (extend to audit window purity).
- **Data:** stored chunks for already-ingested documents keep the corrupted table text until re-ingest; the change adds detection/flagging, not silent repair.
- **Behavioral risk:** tighter chapter-window admission can starve chapters whose opener pages were pinned loosely; the design must keep the existing chapter-pin requirements (rag-pipeline) and the agreement gate authoritative and reuse `scripts/audit_chapter_summaries.py` as the regression harness.
- **Scope note:** this proposal was requested to address the verified findings from the 2026-10-24 chat examination (chapter bleed, reasoning leak, table corruption); the observed one-word divergence between terminal scrollback and stored history is treated under transcript parity.
