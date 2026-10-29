# Spec Delta: document-ingestion

## ADDED Requirements

### Requirement: Table serializations preserve row alignment

When tabular content is serialized into chunk text at ingest, the
serialization SHALL preserve each cell's binding to its row: cells SHALL
be emitted row by row such that a value remains adjacent to its own row
label/header, and a single table SHALL NOT be split across chunk
boundaries in the middle of a row. The observed degenerate form — a
flattened cell run like `5.26 minutes 99.9999` that separates a value from
its row label — SHALL NOT be producible from a well-formed source table.

#### Scenario: Value stays adjacent to its row label

- **WHEN** a document is ingested containing a two-column table that maps
  availability levels to yearly downtime (e.g. 99.999% → 5.26 minutes,
  99.9999% → 31.5 seconds)
- **THEN** the stored chunk text serializes each row with its label and
  value together
- **AND** no stored chunk pairs one row's value with a different row's
  label

#### Scenario: Oversized table splits at a row boundary

- **WHEN** a table's serialized text exceeds the chunk-size limit
- **THEN** the chunk split occurs between table rows
- **AND** no row is split so that its label and value land in different
  chunks

### Requirement: Degenerate table serializations are flagged at ingest

When the table-to-text serialization output fails the row-alignment
invariant (cells out of source order relative to their rows), ingest SHALL
flag the affected chunk(s) — via chunk metadata and an ingest-time warning
— rather than silently storing the degenerate text as if it were reliable
content.

#### Scenario: Flattened table row is flagged

- **WHEN** a PDF's table extraction produces a chunk whose cells read out
  of row order (detected by the row-alignment check)
- **THEN** the chunk is stored with a degenerate-table flag in its
  metadata
- **AND** the ingest report warns that the table's content may be
  unreliable

#### Scenario: Well-formed tables store unflagged

- **WHEN** a table's serialization passes the row-alignment check
- **THEN** the chunk stores with no degenerate-table flag
- **AND** ingest emits no warning for it
