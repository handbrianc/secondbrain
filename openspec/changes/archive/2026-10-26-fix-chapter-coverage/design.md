# Design

## Context

Verified 2026-10-26 against `pve-admin-guide-9.1.pdf`, its stored tree, and the pipeline code (see proposal.md — Why). Facts that shape the approach:

- **The PDF's bookmarks are clean but number-less**: 680 outline entries, correct 0-based dest pages (`Introduction` → 22, `Installing Proxmox VE` → 31), titles like "Introduction"/"Central Management" with no numbering tokens. `_parse_numbering` therefore yields `number=None` for every outline node.
- **The stored tree** (`~/.secondbrain/secondbrain.db`, `structure_nodes`, 3,324 nodes): the only numbered chapter-shaped nodes are `1 Introduction (3–8)` and `7 Proxmox VE Storage (9–22)` — both ranges sit inside the ToC page span (pages 3–22); they are docling headings captured from ToC-page text. The real chapter bodies live in number-less outline-derived nodes with correct ranges (`Introduction (23–31)`, `Installing Proxmox VE (32–48)`, …). Junk also present: `Chapter 1`/`Chapter 2` as section/subsection nodes (docling split the "Chapter 1" run-on from the "Introduction" title) and GFDL sections captured as numbered sections.
- **Query path**: `_tree_chapter_map` (`_structure_mixin.py:2342`) keys strictly on integer `number` → degenerate 2-entry map; broad-coverage output falls to the legacy regex scan (`_derive_chapter_numbers`, `:910`), which titled chapter 1 "1.1 Central Management" and truncated its window to ~3 printed pages. The D2 coverage note (`_chapter_coverage_note`, `_pipeline.py:244`) did not fire because the window composition looked healthy against the *wrong* range.
- **Docling**: 2.138.0 / docling-parse 7.22.2 with the known space-glue regression documented in `_pretty_glued_title` ("the true fix is re-ingest with a docling build that does not glue").
- **In-flight changes this refines**: `add-structure-aware-ingestion` (tree capture/merge, tree-driven enumeration, byte-identical legacy guarantee) and `fix-summary-fidelity` (D2 window composition + coverage note). Their behavior is the baseline; this change corrects a gap both leave open.

## Goals / Non-Goals

**Goals:**

- A fully numbered chapter tree at correct body pages for documents whose outline titles carry no numbers — via ToC-listing number recovery at capture/merge time.
- A chapter map that can never be built from ToC-span ranges, and a clean, guarded fallback when the map is degenerate.
- Legacy-path guards so a missed chapter heading costs at most a title label, never most of a chapter's sections.
- Verified chapter-1 coverage (13/13 sections) for `pve-admin-guide-9.1.pdf` after re-ingest.

**Non-Goals:**

- No new CLI commands, no schema changes, no LLM prompt changes, no changes to the anthology path or the agreement gate.
- No query-time number recovery implementation (capture-time recovery covers new ingests; already-stored broken trees are fixed by re-ingest — the existing cheap backfill path).
- Not fixing docling's glue regression itself; only checking for a fixed release (environment-level) and relying on capture guards regardless.
- No retroactive re-ingest sweep over all stored documents.

## Decisions

**D1 — Recover numbers at capture/merge, not at query time.**
A post-merge numbering pass in `structure_capture.py` matches number-less nodes against the document's ToC listings (parsed from the ToC pages the capture already sees) and fills `number` before `save_structure`. Rationale: one-time cost, persisted, benefits the structure CLI, roster display, and every later query uniformly; query-time recovery would re-parse ToC text per query and leave roster/CLI output wrong. Alternative considered (query-side recovery in `_tree_chapter_map`) — rejected as duplicative per-query work.

- *Matching rule*: normalized title equality (case-fold, whitespace-squash — tolerant of the glue variants) between node title and listing title, aligned in document order and nesting level (ToC row level ↔ node level). A listing assigns at most one node; ambiguous or unmatched nodes stay number-less. Numbers already parsed from titles always win.
- *ToC text source*: a small, pure ToC-row parser in `structure_capture` (dot-leader rows like `1 Introduction .... 1`, `1.1 Central Management .... 2`). The pipeline's `_toc_chapter_listings` stays untouched — a ~30-line dedicated parser in the capture layer is preferred over a cross-layer refactor of the pipeline mixin.

**D2 — ToC-span guard in `_tree_chapter_map`.**
Before admitting a chapter-shaped node's range, test the range's stored chunks for dot-leader density (the same ToC-likeness signal the legacy tiers already use); a dense range contributes no map entry. Combined with D1 this yields, for the affected PDF, either a healthy 21-entry map or a clean bail — never a 2-entry map over ToC pages. A degenerate map (fewer usable entries than the tree's chapter-shaped, non-ToC-span nodes) logs and falls back to the legacy guarded path; the empty-bucket/placeholder machinery already speaks for any chapter the fallback cannot fill.

**D3 — Legacy guards in `_derive_chapter_numbers` + window assembly.**
- *Title guard*: the chapter-title scan rejects headings whose leading token is dotted (`^\d+(?:\.\d+)+\s`), mirroring the guard already applied to ToC-row capture at `:598`. The rejected heading remains a *section* boundary; the chapter's title falls back to the ToC-listing title for that number, else the number-only header (the `_fallback_mixin.py:579` header already renders `Chapter N` without a title).
- *Window clamp*: a chapter bucket's end page becomes `next chapter start − 1` when that boundary is derivable and lies beyond the current end — extend-only. If the next start is mis-derived below the current end, keep the current end. Start-pinning machinery (pins, footer offsets, anchors, agreement gate) is untouched.

**D4 — Environment: docling upgrade check, then re-ingest.**
Check for a docling-parse release fixing the glue regression (e.g. via `scripts/libyear.sh` / pip index). If found: upgrade, re-ingest the PDF. The re-ingest backfill regenerates embeddings only for changed chunk text (existing behavior). Either way, D1–D3 make the tree and query paths healthy; the upgrade only improves raw heading capture.

**D5 — Verification owner and tools.**
`secondbrain structure` inspection (21 numbered chapters, sections 1.1–1.13 present), the two chat queries re-run against the re-ingested document, `scripts/audit_chapter_summaries.py` sweep, and unit tests per spec scenario (`test_structure_capture.py`, `test_structure_tree_query.py`, `test_pipeline.py`).

## Risks / Trade-offs

- [Title-match numbering mis-assigns on documents with duplicate section titles] → exact unique normalized-title match + order/level alignment; ambiguous matches stay unnumbered and behavior falls back to today's.
- [Window clamp over-extends into a neighbor chapter when the next start is mis-derived] → extend-only clamp plus the existing agreement gate and D2 range admission; the fix-summary-fidelity window-composition note still reports foreign content if any slips through.
- [Legacy guards change output for documents whose headings mis-parse — narrows the in-flight delta's byte-identical legacy guarantee] → intentional; surfaced in the proposal. The guarantee is preserved for healthy documents (spec scenario "Healthy legacy documents are unchanged"). Reconcile wording when `add-structure-aware-ingestion` archives.
- [Degenerate-map fallback reverts to legacy for broken stored trees, which is slower than the tree path] → acceptable; the durable fix is re-ingest after D1, and the fallback is bounded by the same token budgets as today.
- [Docling upgrade may re-chunk the document → some re-embedding cost on re-ingest] → unchanged text keeps embeddings via text-hash dedup; cost is proportional to what the upgrade actually changes.
- [Capture-layer ToC parser duplicates pipeline ToC regexes] → deliberate small duplication (~30 lines, pure, unit-tested) vs a cross-layer refactor of `_structure_mixin`; revisit if a shared module emerges.

## Migration Plan

1. Land D1–D3 with unit tests (guards are additive; no stored-schema change).
2. Check/apply the docling-parse upgrade (D4) — optional, independent.
3. Re-ingest `pve-admin-guide-9.1.pdf` (rebuilds its tree idempotently; embeddings reused for unchanged text), then run the D5 verification gate.
4. Rollback: revert the commit and re-ingest — capture rebuilds the tree from whatever code version is active; no stored data migration exists to undo.

## Open Questions

- Whether an available docling-parse release actually fixes the space-glue regression — resolved during tasks (D4); the outcome only decides whether the upgrade lands, not the code design.
