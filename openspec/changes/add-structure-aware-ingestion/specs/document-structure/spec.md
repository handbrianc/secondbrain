# Document Structure (delta)

## ADDED Requirements

### Requirement: Structure capture at ingest

The system SHALL capture document structure once per document at ingest from
authoritative sources and persist it: for PDFs the outline/bookmark tree
(`pypdfium2 get_toc`) and `/PageLabels` (`FPDF_GetPageLabel`); for parsed
documents the docling heading hierarchy (`SectionHeaderItem.level`); for audio
ASR timestamps. Outline/bookmark evidence SHALL be authoritative over derived
headings where both describe the same node. Capture failure SHALL NOT fail
ingest: the document is stored without a tree.

#### Scenario: PDF with outline yields a chapter tree

- **WHEN** a PDF with a nested bookmark outline is ingested
- **THEN** the stored tree contains a node per outline entry with kind,
  level, number (when the title carries one), title, and a 1-based
  `page_start` on the same axis as the chunk `page_number`
- **AND** each node's page range spans to the next sibling boundary so ranges
  are contiguous and nestable

#### Scenario: PDF without outline falls back to heading hierarchy

- **WHEN** a PDF has no bookmark outline but docling detects headed sections
- **THEN** the tree is built from heading-hierarchy levels alone
- **AND** outline-derived nodes, when present, take precedence in the merge

#### Scenario: Capture failure does not fail ingest

- **WHEN** structure capture raises (unreadable outline, pypdfium2 error)
- **THEN** the document is ingested and stored without a tree
- **AND** the failure is logged as a warning

### Requirement: Persistent structure store

The system SHALL persist captured structure in SQLite tables
`structure_nodes`, `page_labels`, `audio_segments`, and `structure_meta`
keyed by `source_file` (the exact string stored in vector payload
`source_file`), created with `CREATE TABLE IF NOT EXISTS` and without
touching `PRAGMA user_version`. Re-capture SHALL be idempotent: saving
replaces the whole tree for that `source_file` in one transaction.

#### Scenario: Re-capture is idempotent

- **WHEN** the same document is re-ingested and its tree is saved again
- **THEN** the store holds exactly one tree for that source_file with the
  same deterministic node ids

#### Scenario: Treeless document looks up as None

- **WHEN** a document without stored structure is looked up
- **THEN** the store returns no tree (not an empty one)

### Requirement: Structure inspector CLI

The system SHALL provide `secondbrain structure <doc>` printing the stored
tree (kind, number, title, page or time ranges), the page-label table, and
audio segments, with a `--json` mode. Documents without a stored tree SHALL
get explicit re-ingest guidance; unknown sources SHALL error.

#### Scenario: Tree document prints its outline

- **WHEN** the user runs `secondbrain structure report.pdf` for an ingested
  document with a stored tree
- **THEN** the output lists every chapter/section node with its page range
  and printed page labels

#### Scenario: Treeless document gets re-ingest guidance

- **WHEN** the queried document has no stored tree
- **THEN** the command prints guidance to re-ingest and exits successfully

### Requirement: Backfill via re-ingest

Re-ingesting an ingested file (`ingest <path>`, with default hash skipping) SHALL recapture
and persist its tree and refresh structural payload fields on already-stored
points without regenerating embeddings for chunks whose text is unchanged
(text-hash dedup preserved).

#### Scenario: Re-ingest backfills structure cheaply

- **WHEN** a document whose chunks are already stored is re-ingested
- **THEN** its stored tree exists afterwards
- **AND** its stored points carry the structural payload fields
- **AND** embeddings were not regenerated for unchanged chunk text

### Requirement: Audio anchors

Audio ingest SHALL persist ASR timestamps as `t_start`/`t_end` on audio nodes
and chunks and derive topic segments (`audio_segments`); when the ASR output
carries no timestamps, capture SHALL degrade to a single whole-document
segment and ingest SHALL still succeed.

#### Scenario: Timestamped audio stores segments

- **WHEN** an audio file with timestamped ASR output is ingested
- **THEN** the stored tree carries segment nodes with time ranges
- **AND** audio chunks carry `t_start`/`t_end` payload fields

#### Scenario: Untimestamped audio degrades safely

- **WHEN** ASR output provides no timestamps
- **THEN** the tree degrades to one whole-document segment
- **AND** ingest completes without error
