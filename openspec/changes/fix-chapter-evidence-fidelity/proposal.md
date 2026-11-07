# Proposal

## Why

A live chat evaluation of `hcd_best_practices_report.pdf` (25 pages, 21 numbered
chapters) found three distinct fidelity defects:

1. **Polluted roster titles.** The overview headed chapter 7 with
   "7 Wikipedia — The Design of Everyday Things (D…" — a Source-Register row
   from page 23, not the chapter's heading. `bare_chapter_re`
   (`_structure_mixin.py`) makes the separating dot optional, so register rows
   like "7 Wikipedia — …" parse as chapter headings; the `\s` in the title
   class glues body text across lines, and the 80-character cap cuts the
   captured title mid-word. Probe sampling then preferred the register row
   over the real heading.
2. **Page-granular chunk annotation.** The stored page-10 chunk at `pos=0`
   contains the printed "9. Krippendorff's …" heading, yet is annotated
   `ch_id=10`, `heading_path="Chapter 10 — Co-Creation"`: the annotator
   assigns ownership per page from outline spans, ignoring where inside the
   page the next chapter starts. Docling missed 7 of 21 chapter headings
   (3, 5, 9, 12, 13, 14, 20), and chapter 13's bucket came back empty while
   its content sat in chunks annotated for chapter 15.
3. **Lost structure tree.** `capture_pdf_outline` on the same file returns a
   complete 56-node outline, yet the store holds no `structure_nodes` for the
   source — the tree was lost between capture and persistence, so the
   query-time pipeline fell back to legacy heuristics on a document that
   should be tree-driven.

Each defect breaks a guarantee the shipped specs already state ("no chapter's
summary draws content from another chapter's pages"; tree-driven enumeration
when a tree exists; titles from real headings).

## What Changes

- Ingest-side chunk annotation becomes position-aware: a chunk whose own text
  carries a numbered chapter-heading form anchors that chapter when the form
  sits in the chunk's first half; in the second half, ownership switches with
  the NEXT chunk. Page-granular outline spans no longer override in-chunk
  heading evidence.
- Numbered chapter headings the parser missed are synthesized from the
  document text stream using a shared `document/heading_forms.py` extraction
  module, so the stored tree's chapter roster matches the printed roster.
- The outline-tree persistence gap is diagnosed and closed; persistence
  failures become observable (logged), not silent.
- Query-time guards: the text-marker identity floor drops from page 20 to
  page 3 so short reports contribute in-chunk text markers, and roster-title
  capture is hardened (line-boundary capture, word-boundary trim,
  citation-shape rejection of source-register rows).
- Unchanged: the bucket identity guard and coverage note shipped by
  `chapter-label-integrity`, anthology detection, the agreement gate, the
  single-section full-fetch path, and the CLI surface. No stored data is
  migrated; the remedy for the affected document is a re-ingest from the
  original file plus deletion of the stale upload-path source key.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `document-structure`: position-aware chunk annotation, synthesis of
  numbered headings the parser missed, observable tree persistence.
- `rag-pipeline`: short-document text-marker floor, roster-title hygiene.

## Impact

- `src/secondbrain/document/structure_annotate.py` — position-aware
  annotation state machine.
- `src/secondbrain/document/structure_capture.py` — heading synthesis,
  persistence wiring/observability.
- `src/secondbrain/document/heading_forms.py` — NEW shared module: numbered
  heading forms and title extraction (dot-required bare `N.` / dotted `N.M`,
  line-boundary capture with bounded continuation, word-boundary trim).
- `src/secondbrain/rag/pipeline/_structure_mixin.py` — marker floor constant,
  roster-title regexes.
- Tests: `tests/unit/document/` (annotate, capture, heading_forms),
  `tests/unit/rag/` (marker floor, title hygiene; accepted churn in
  `_chapter_fixture_storage.py` baseline windows).
- No CLI/API changes; stored data remedied by re-ingest of
  `/home/bchand/hcd_best_practices_report.pdf` followed by deletion of the
  stale `/data/workspace/uploads/hcd_best_practices_report.pdf` source key.
