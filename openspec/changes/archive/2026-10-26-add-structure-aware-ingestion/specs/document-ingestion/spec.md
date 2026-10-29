# Document Ingestion (delta)

## ADDED Requirements

### Requirement: Structure capture wired into ingestion

Every ingest path (single, recursive, sync, and multicore) SHALL invoke the
shared structure-capture module exactly once per document at the parse stage
and persist the captured tree once per document. Worker processes SHALL NOT
write to SQLite: capture returns the structure with the worker result and the
parent path persists it.

#### Scenario: Multicore ingest captures each document's tree

- **WHEN** a directory is ingested with `--cores 4`
- **THEN** every successfully parsed document has exactly one stored tree
- **AND** no SQLite write contention is introduced by worker processes

#### Scenario: Sync and async paths behave identically

- **WHEN** the same document is ingested through the sync and async paths
- **THEN** both produce the same stored tree

### Requirement: Heading hierarchy enabled for PDF parsing

The PDF conversion pipeline SHALL enable docling's heading-hierarchy stage
(`HeadingHierarchyOptions.enabled = True`) so detected section headings carry
hierarchy levels (bookmark-matched headings authoritative; numbering and font
style as fallback).

#### Scenario: Headings carry levels after conversion

- **WHEN** a PDF is converted with the pipeline options
- **THEN** detected section headers expose their hierarchy level
- **AND** the stage neither adds, removes, nor reorders text items

### Requirement: Heading roles preserved

Standalone section-numbered heading chunks (a single heading segment, not
merged with body content) SHALL keep a structural role so their metadata is
queryable; merged opener chunks (a heading merged together with following
body text into one chunk) SHALL keep the `body` role and SHALL carry the
structural annotation fields instead. Role classification SHALL NOT change
chunk text or boundaries: chunk text streams SHALL remain byte-identical for
unchanged input.

#### Scenario: Standalone section-numbered heading keeps a structural role

- **WHEN** a chunk consists of a single section-numbered heading segment
  (e.g. "11.18 Configuring the Autostart Service")
- **THEN** it is stored with a structural role rather than `body`

#### Scenario: Merged opener chunk stays body but is annotated

- **WHEN** a chunk merges a section-numbered heading with following body text
- **THEN** its role remains `body`
- **AND** its payload carries the structural annotation fields (node_id,
  heading_path, section_id)

#### Scenario: Role change does not move chunk boundaries

- **WHEN** the same document is chunked before and after the role change
- **THEN** the chunk text sequence is byte-identical
- **AND** text hashes are unchanged
