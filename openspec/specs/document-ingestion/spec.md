# Document Ingestion

## Purpose

Ingest documents from the local filesystem: Docling-based parsing and chunking, embedding
generation, and storage in the vector database, with batch/recursive processing, progress reporting,
and file-type detection.

> **Provenance (2026-10-15):** Promoted from the archived change delta
> `openspec/changes/archive/2026-03-06-secondbrain/specs/document-ingestion/spec.md` — the delta marker
> `## ADDED Requirements` became `## Requirements`; content is otherwise
> unchanged.


> **Note (2026-10-11):** Staleness pass — this archived spec records the MongoDB-era design; the shipped
> backend is Qdrant vector storage with SQLite conversation storage. The requirement text below is preserved
> as history; shipped behavior differs as follows:
>
> - **Storage:** MongoDB → Qdrant (`SECONDBRAIN_QDRANT_URL`; backend override `SECONDBRAIN_STORAGE_BACKEND`);
>   conversations → SQLite (`SECONDBRAIN_SQLITE_PATH`). All `SECONDBRAIN_MONGO_*` variables are gone.
> - **Defaults drift:** chunk size 512 → 4096 chars (overlap stays 50); embeddings embeddinggemma:latest/384-dim
>   → `text-embedding-3-small`/1536-dim; LLM Ollama/`llama3.2`/0.7/4096 → OpenAI-compatible/`gpt-4o-mini`/0.3;
>   search default top-k 5 → 50 with a minimum-similarity threshold filter applied by default.
> - **Renames:** `list` → `ls`; `--workers` → `--cores`; `--force` → `--yes`; `SECONDBRAIN_MONGO_*` →
>   `SECONDBRAIN_QDRANT_URL`/`SECONDBRAIN_STORAGE_BACKEND`; `SECONDBRAIN_MODEL` → `SECONDBRAIN_EMBEDDING_MODEL`;
>   `SECONDBRAIN_SENTENCE_TRANSFORMERS_URL` → `SECONDBRAIN_EMBEDDING_API_BASE`;
>   `SECONDBRAIN_CONVERSATION_DB` → `SECONDBRAIN_SQLITE_PATH`.
> - **Behavior inversions:** re-ingest skip is now the default (the flag inverted to `--no-skip-existing`);
>   duplicates are deduplicated by SHA256 `text_hash` by default (no `--replace` opt-in); an embedding cache is
>   implemented (was "no cache for now").
> - **Display drift:** result text preview truncation 200 → 100 chars; search result rendering lives in
>   `src/secondbrain/cli/display.py`.
>
> Most relevant here: the storage target (Qdrant), the chunk-size default, `--workers` → `--cores`, and the
> skip-existing inversion.

## Requirements

### Requirement: Document Ingestion

The system SHALL allow users to ingest documents from local filesystem paths and generate embeddings stored in MongoDB.

#### Scenario: Ingest single document

- **WHEN** user runs `secondbrain ingest document.pdf`
- **THEN** the system parses the document using Docling
- **AND** extracts text content in chunks
- **AND** generates embeddings using OpenAI-compatible API
- **AND** stores vectors in MongoDB with metadata

#### Scenario: Ingest multiple documents recursively

- **WHEN** user runs `secondbrain ingest /path/to/docs/ --recursive`
- **THEN** the system discovers all supported files in the directory tree
- **AND** processes each document sequentially
- **AND** reports progress for each file
- **AND** handles errors gracefully per file without stopping batch

#### Scenario: Ingest with custom chunk size

- **WHEN** user runs `secondbrain ingest document.pdf --chunk-size 1024`
- **THEN** the system chunks text into 1024-character segments
- **AND** uses 50-character overlap by default (configurable)

#### Scenario: Skip already ingested files

- **WHEN** user runs `secondbrain ingest /path/ --skip-existing`
- **THEN** the system checks if file hash exists in database
- **AND** skips files that have already been ingested
- **AND** reports skipped file count

#### Scenario: Supported document types

- **WHEN** user provides a document file
- **THEN** the system accepts: PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, LaTeX, CSV, Images (PNG, JPEG, TIFF,
  BMP, WEBP), Audio (WAV, MP3), WebVTT, XML, Docling JSON
- **AND** rejects unsupported formats with clear error message

#### Scenario: Document parsing failure

- **WHEN** user attempts to ingest a corrupted or unreadable file
- **THEN** the system logs the error
- **AND** reports failure to user
- **AND** continues with next file if batch

### Requirement: Batch Processing

The system SHALL process multiple documents in batch mode with progress reporting.

#### Scenario: Progress reporting during batch

- **WHEN** user runs `secondbrain ingest /path/` with 10 files
- **THEN** the system shows progress bar or file count
- **AND** reports completion percentage
- **AND** shows time estimate for remaining files

#### Scenario: Concurrent processing

- **WHEN** user runs `secondbrain ingest /path/ --workers 4`
- **THEN** the system processes up to 4 documents in parallel
- **AND** respects memory constraints

### Requirement: File Type Detection

The system SHALL automatically detect document file types by extension and MIME type.

#### Scenario: Automatic format detection

- **WHEN** user provides file with .pdf extension
- **THEN** system treats it as PDF document
- **AND** uses appropriate Docling converter

#### Scenario: Unknown file type

- **WHEN** user provides file with unknown extension
- **THEN** system rejects with helpful error message
- **AND** lists supported file extensions

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
