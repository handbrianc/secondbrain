# Proposal

## Why

Chapter summaries for large PDFs are silently wrong when the stored structure tree degenerates. Verified on `pve-admin-guide-9.1.pdf` (2026-10-26): the document's bookmark outline is clean (680 entries, correct destination pages) but its titles carry no numbering tokens, so the stored tree's only numbered chapter nodes are docling headings captured from the table-of-contents pages — `1 Introduction (pages 3–8)` and `7 Proxmox VE Storage (pages 9–22)`, both on the ToC page span. The number-keyed tree chapter map therefore holds 2 of 21 chapters with wrong ranges; broad-coverage queries fall back to the legacy regex scan, which titles chapter 1 from its first section heading ("1.1 Central Management") and truncates its window to ~3 of 9 printed pages — 12 of 13 sections silently missing from the "Chapter 1" summary, with no coverage note (the D2 composition note only guards foreign/empty windows, not a wrong range). Fact spot-checks showed every other chapter faithful; the defect is upstream of the LLM.

## What Changes

- **Numbering recovery (capture/merge)**: when outline or docling node titles carry no numbering token, recover chapter/section numbers by matching node titles against the document's parsed ToC listings (title match + page plausibility), so a number-less outline still yields a fully numbered chapter tree at correct body pages.
- **Chapter-map integrity (tree query path)**: `_tree_chapter_map` SHALL NOT admit chapter-map entries whose page range lies inside the document's ToC page span, and SHALL treat a number-keyed map that covers far fewer chapters than the tree's chapter-shaped nodes as degenerate — recover numbers via title matching against the number-less chapter nodes, or bail to the guarded legacy path, rather than summarize from 2 bogus ranges.
- **Legacy fallback guards**: a dotted-prefix heading ("1.1 Central Management") SHALL NOT become a chapter's title; a chapter's legacy page window SHALL end at the next chapter's start rather than at the next parseable heading, so a missed title costs a label, not most of a chapter's sections.
- **Environment check + re-ingest**: check for a docling-parse release fixing the known space-glue regression (documented in `_pretty_glued_title`); upgrade if available, re-ingest the affected PDF, and rebuild its tree.
- **Verification**: `secondbrain structure` inspection, chapter-1 coverage check (13/13 sections), fact spot-checks, `scripts/audit_chapter_summaries.py` sweep, and unit tests for the new guards.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `document-structure`: ADDED requirement "Chapter numbering recovery from ToC listings" — extends the capture/merge behavior (which stores a number only "when the title carries one", per in-flight `add-structure-aware-ingestion`) to the number-less-outline case.
- `rag-pipeline`: ADDED requirements "Stored-tree chapter map integrity" and "Legacy chapter title and window guards". Framed as ADDED (not MODIFIED of the in-flight "Stored tree drives chapter enumeration" / "Legacy reconstruction is fallback only") because those requirement names do not yet exist in the main spec; the interplay — a degenerate chapter map is a fourth legacy-fallback trigger, and the new legacy guards intentionally narrow the in-flight delta's byte-identical guarantee for mis-derived documents — is surfaced in design.md for reconciliation at archive time.

## Impact

- **Code**: `src/secondbrain/document/structure_capture.py` (merge/numbering recovery), `src/secondbrain/rag/pipeline/_structure_mixin.py` (`_tree_chapter_map`, `_derive_chapter_numbers` guards), `src/secondbrain/rag/pipeline/_fallback_mixin.py` (legacy window clamp and chapter header path). Tests under `tests/unit/document/`, `tests/unit/rag/`, `tests/unit/storage/`.
- **Data**: re-ingesting `pve-admin-guide-9.1.pdf` rebuilds its tree in the structure store; unchanged chunk text keeps its embeddings (existing re-ingest backfill behavior).
- **Dependencies**: possible docling-parse upgrade — environment-level, no code dependency change.
- **Spec interplay**: refines in-flight `add-structure-aware-ingestion` (tree-driven enumeration gains a fourth fallback trigger; the byte-identical legacy guarantee is narrowed for mis-derived documents only) — see design.md, Risks.
- **No breaking changes**: CLI, APIs, and stored schemas are unchanged; behavior changes are corrections and guards.
