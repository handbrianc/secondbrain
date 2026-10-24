# Structure-Aware Ingestion — Proposal

## Why

Broad-coverage chapter/section queries over long documents reconstruct document
structure at *query time* from regex heuristics over chunk text (chapter
banners, section numbers, ToC rows, footers). Forensic replay of the failing
`hcd_best_practices_report.pdf` chat session showed the heuristic stack is at
its edge: chapters 1–5 were never enumerated (roster gates trimmed them),
chapters 10/13/15 degraded to "no document content was retrieved" placeholders
(same-page openers defeated strict monotone pinning, and no recovery tier
exists), and chapter 6's summary was contaminated with section 5 content
(a `(5, 5)` range plus the per-page chunk cap). The anthology change
(2026-10-23) needed a bespoke shape detector + per-part path for exactly the
same class of failure — each new document shape currently buys new heuristics.

Meanwhile the authoritative structure signals are discarded at ingest:

- PDF outlines/bookmarks and `/PageLabels` are never read (pypdfium2 provides
  `PdfDocument.get_toc()` and raw `FPDF_GetPageLabel`; both verified present in
  the installed stack).
- docling's heading-hierarchy stage is off by default
  (`HeadingHierarchyOptions(enabled=False)`, docling 2.138.0) and detected
  headings are flattened to text+page.
- The chunker deliberately downgrades section-numbered headings to `body`
  (`chunker.py:134-135`), so `hcd_best_practices_report.pdf` is stored as 160
  chunks that are *all* `body` — no structural metadata at all.
- Qdrant payload fields `chapter_id`, `section_id`, `section_label` are
  write-never/read-never (indexed, never populated).

Fix direction (user-approved design): capture structure once at ingest from
authoritative sources, persist a document tree in SQLite, populate the
structural payload fields, and make query time a lookup — the legacy regex
machinery is retained as fallback for documents without a stored tree.

## What Changes

- **Structure capture at ingest (new):** a capture module reads PDF
  outline/bookmarks (`pypdfium2 get_toc`), `/PageLabels` (`FPDF_GetPageLabel`),
  docling heading hierarchy (enabled for PDF parsing), and ASR timestamps
  (audio); merges them into one document tree; and persists it in SQLite
  (`StructureStore`: `structure_nodes`, `page_labels`, `audio_segments`),
  captured exactly once per document in the processor worker path and persisted
  once per document by the ingest paths.
- **Headings preserved (chunker):** section-numbered heading segments are no
  longer downgraded to `body`; chunk *text* and boundaries stay byte-identical
  (role classification is label-only), so text hashes and existing embeddings
  remain valid.
- **Structural payload fields (vector storage):** chunks carry `node_id`,
  `heading_path`, `chapter_id`, `section_id`, `section_label`; `chunk_role`
  joins the indexed payload fields; re-ingest refreshes structural payload on
  already-stored points (dedup-skipped) without regenerating embeddings.
- **Tree-lookup query path (rag pipeline):** chapter/section enumeration
  resolves from the stored tree first (SQL ranges → page-range / ID filters on
  the existing retrieval machinery); the regex reconstruction pipeline is
  demoted to fallback and runs only for documents without a stored tree.
  Anthology detection and the chapter-range agreement gate continue to govern
  the fallback path unchanged.
- **Audio anchors:** ASR timestamps persist as `t_start`/`t_end` on audio
  chunks and topic segments (`audio_segments`); audio structure appears in the
  same tree and inspector.
- **Inspector CLI (new):** `secondbrain structure <doc>` prints the stored
  tree (chapters/sections with page ranges and printed labels), page-label
  table, and audio segments; documents without a stored tree get explicit
  re-ingest guidance.
- **Backfill:** re-ingest (`ingest <path>`, with default hash skipping) is the backfill
  mechanism — it captures the tree and refreshes structural payload fields on
  existing points; no separate migration command.

## Capabilities

### New Capabilities

- **document-structure** — persistent document-structure store, capture
  contract (outline, page labels, heading hierarchy, audio anchors), tree
  lookup API, inspector CLI, backfill semantics.

### Modified Capabilities

- **document-ingestion** — structure capture wired into every ingest path
  (exactly once per document); docling heading hierarchy enabled for PDF
  parsing; section-numbered headings keep their heading role.
- **vector-storage** — structural payload fields populated and indexed;
  payload refresh on re-ingest for dedup-skipped points.
- **rag-pipeline** — stored tree drives chapter/section enumeration when
  present; legacy regex reconstruction demoted to fallback.

## Dependencies

- None external. Verified against the installed stack: docling 2.138.0
  (`HeadingHierarchyOptions`, `SectionHeaderItem.level`), pypdfium2 5.13.0
  (`get_toc`, `FPDF_GetPageLabel`), Qdrant ≥1.x (`create_payload_index`,
  point-level payload overwrite).

## Impact

**Code:**

- `src/secondbrain/storage/structure_sqlite.py` (new) — `StructureStore` +
  models (`DocumentStructure`, `StructureNode`, `PageLabelRange`,
  `AudioSegment`), mirroring the `ConversationStorage` pattern
  (sync + `*_async` twins, `ValidatableService`, `CREATE TABLE IF NOT EXISTS`).
- `src/secondbrain/document/structure_capture.py` (new) — outline / page-label
  / heading-hierarchy / audio capture and merge.
- `src/secondbrain/document/structure_annotate.py` (new) — per-chunk
  structural annotation from the tree.
- `src/secondbrain/document/docling_factory.py` — enable
  `heading_hierarchy_options.enabled` for PDF pipelines.
- `src/secondbrain/document/processor.py` — capture call in the worker path;
  chunk annotation after chunking; worker returns the captured tree.
- `src/secondbrain/document/chunker.py` — drop the section-numbered → `body`
  downgrade (role classification only; merge policy untouched).
- `src/secondbrain/document/ingestor/_sync.py`, `_async.py` — persist the
  tree once per document; refresh payload after store.
- `src/secondbrain/storage/qdrant.py` — structural fields ride the payload;
  `chunk_role` payload index; `refresh_structural_payload` (is_empty-targeted
  read-modify-write in batches).
- `src/secondbrain/rag/pipeline/_pipeline.py`,
  `_structure_mixin.py`, `_fallback_mixin.py` — tree-lookup branch ahead of
  the legacy path; legacy path untouched as fallback.
- `src/secondbrain/cli/structure.py` (new) + `cli/__init__.py` registration —
  `secondbrain structure <doc>`.
- `src/secondbrain/management/__init__.py` — document delete also deletes the
  stored tree.
- `tests/unit/` — store, capture, annotate, chunker, qdrant, pipeline tests.
- `tests/fixtures/structure/` — synthetic PDF/heading fixtures where needed.

**Docs:** user-guide CLI page (new `structure` command) + README mention.

**Non-goals:**

- Automatic corpus re-ingest (backfill stays an explicit user action).
- Deleting the legacy regex pipeline (stays as fallback, under
  characterization tests).
- Editing stored structure by hand (the tree is derived, never hand-written).
- Rewriting the legacy enumeration tiers themselves.
