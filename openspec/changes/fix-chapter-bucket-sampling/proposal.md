# Proposal

## Why

A transcript audit of `secondbrain chat` against the Proxmox VE Administration Guide 9.1.0 found exactly one factual error in the chapter-by-chapter overview: chapter 16's VM "snapshot mode" was described with the *container* snapshot mode's text ("uses the underlying storage's snapshotting facilities"). Diagnosis against the live Qdrant store shows the structure-tree path delivered chapter 16's full, document-ordered content (132 body chunks, 28,447 chars) in a single LLM call — so the swap happened during brief-summary generation, which has no guard for the document's parallel, identically-named lists ("stop / suspend / snapshot mode" appears twice: VM block, then container block), and the formatted context carries no structural scope labels that would keep the two blocks visually distinct.

The same diagnosis exposed a latent defect in the legacy (treeless) multi-chapter sampler: it admits within-page chunks in storage enumeration order (`get_body_chunks` sorts by page only), making bucket selection storage-order-dependent and non-reproducible, and its flat 3-chunks-per-page cap starves dense pages — replaying the sampler over the live store shows a page holding six mode chunks contributes only 3, and the correct VM snapshot-mode description is among the dropped (this path did not run for the audited document, which has a structure tree; the defect affects treeless documents).

## What Changes

- Per-chapter brief summaries gain an attribution guard: when the source contains repeated item names under different scopes (e.g. the same mode name under different guest types), the summary instruction requires scope-faithful attribution — each item's description is attributed to its own scope, never swapped or merged across same-named items.
- Formatted summary context labels each chunk with its structural heading path in the source line, so scope markers (e.g. "Backup Modes > snapshot mode" vs. the container block under "Backup Modes") travel with every chunk instead of depending on a separate heading chunk appearing adjacent in the window.
- Legacy multi-chapter sampler: within-page admission follows document order (ascending page position) instead of storage enumeration order, making the selected window a deterministic function of stored content.
- Legacy multi-chapter sampler: the per-page admission cap scales with the page's body-chunk density (bounded), so pages holding many chunks are not reduced to the same fixed share as sparse pages; the per-chapter limit still bounds the window.
- Unchanged: window purity guarantees (in-range-only admission, one-page straddle tolerance), window-composition statistics and coverage notes, the single-section (≤2 chapters) lossless full-fetch path, ingestion and the stored vector store.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `rag-pipeline`: new requirements for (1) scope-faithful attribution in per-chapter summaries over repeated item names, (2) structural scope labels in formatted summary context, and (3) deterministic, density-aware admission in the legacy multi-chapter chapter-window sampler.

## Impact

- `src/secondbrain/rag/pipeline/_fallback_mixin.py` — per-chapter brief-summary instruction (attribution guard); `_split_bounded` unaffected for tree-path input.
- `src/secondbrain/rag/pipeline/_formatting_mixin.py` — `_format_context` source line gains the heading path when present in the chunk payload.
- `src/secondbrain/rag/pipeline/_pipeline.py` — legacy multi-chapter round-robin admission (document-order iteration, density-aware per-page cap).
- `src/secondbrain/storage/qdrant.py` — optional `page_pos` tiebreak in `get_body_chunks` ordering.
- No CLI/API surface changes; no changes to stored data; prompt changes are additive instruction text.
- Tests: `tests/unit/rag/test_chapter_window_purity.py` and `tests/unit/rag/test_pipeline_iterative.py` extend; new unit tests for admission order and density cap; end-to-end chapter-16 regression check against the live store.
