# Proposal: Fix chunk heading context and term/definition binding

## Why

An evaluation of a real CLI chat session against its source PDF (Proxmox VE Administration Guide 9.1) found three retrieval-caused factual defects, all traced to chunk structural metadata: 76.7% of body chunks (4,068 of 5,308) carry no `heading_path`, so retrieved definitions are attributed to the wrong section; the captured structure tree is polluted with non-heading nodes (3,324 nodes for a 21-chapter guide, ~2,700 unnumbered, many spurious — e.g. "Restart chrony:", "pvesubscription - Subscription Management" became tree nodes); and short term labels (e.g. "FSYNCS/SECOND") are ingested as orphaned standalone heading chunks, split from the definition text they introduce. The annotation starve-out is structural: `annotate_chunks` refuses to annotate unanchored prose when two sibling nodes share the chunk's page — which is the common case in real documents. A cosmetic ingest summary message ("Successfully ingested 1 files") is included while touching this area.

## What Changes

- **Heading plausibility gate at capture**: docling-detected section headers that fail a plausibility test (trailing sentence punctuation, over-long, "cmd - Description" synopsis shape) SHALL NOT become structure-tree nodes. Outline/bookmark-derived nodes stay authoritative and ungated. The same predicate drives chunking: implausible heading-labeled items are merged with adjacent body text (label/definition binding) instead of flushed as standalone structural segments.
- **Reading-order inheritance in chunk annotation**: `annotate_chunks` gains an ordered mode. When an unanchored chunk's last annotated node still contains the chunk's page, the chunk inherits that node (sticky owner) instead of being left unannotated by the same-page-sibling ambiguity bail-out. The unordered (stateless) behavior is preserved for callers that cannot guarantee reading order.
- **Reading-order refresh**: the qdrant structural payload refresh sorts a document's unannotated points by `(page_number, page_pos)` and annotates them in one ordered pass, so re-ingested documents gain the same heading coverage as freshly ingested ones.
- **Ingest summary pluralization**: the CLI ingest summary prints "1 file" / "N files" (and likewise for skipped/failed counts).

Term/definition binding for heading-plausible short labels (e.g. "FSYNCS/SECOND") is achieved structurally: such labels remain heading nodes under their (now correct) parent, and ordered inheritance binds the following definition chunk to that node, so its `heading_path` ends with the term.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `document-structure`: heading capture SHALL apply a plausibility gate to docling-detected headings before node creation, and chunk annotation SHALL provide reading-order inheritance so unanchored body chunks are no longer left unannotated by same-page ambiguity.
- `document-ingestion`: chunk assembly SHALL bind implausible heading-labeled items to adjacent body text (label/definition pairing) instead of emitting them as standalone structural segments.

## Impact

- **Code**: `src/secondbrain/document/chunker.py` (plausibility predicate + merge-path pairing), `src/secondbrain/document/structure_capture.py` (gate applied to docling heading capture), `src/secondbrain/document/structure_annotate.py` (ordered sticky inheritance), `src/secondbrain/document/processor.py` (pass ordered mode), `src/secondbrain/storage/qdrant.py` (ordered refresh), `src/secondbrain/cli/ingest.py` (pluralization).
- **Tests**: unit tests for the predicate, pairing, sticky inheritance, and ordered refresh; existing chunker/structure/annotate suites must stay green.
- **Stored data**: existing ingested documents gain correct annotations only after re-ingest (payload refresh on re-ingest covers already-stored points); the PVE guide PDF is re-ingested during verification.
- **No breaking changes**: chunk text streams remain byte-identical for unchanged input (pairing only reroutes *standalone structural flushes* of implausible labels, which previously produced orphan chunks); annotation only adds payload keys.
