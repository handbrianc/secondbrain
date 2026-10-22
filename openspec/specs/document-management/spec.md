# Document Management

## Purpose

List, delete, and report on ingested documents and chunks: per-file and per-chunk listings, filtered
and confirmed deletes, and database statistics/health.

> **Provenance (2026-10-15):** Promoted from the archived change delta
> `openspec/changes/archive/2026-03-06-secondbrain/specs/document-management/spec.md` — the delta marker
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
> Most relevant here: the `list` → `ls` command rename, `--force` → `--yes` on destructive deletes, the
> storage target, and the display truncation drift.

## Requirements

### Requirement: List Documents

The system SHALL list ingested documents and chunks from the database.

#### Scenario: List all documents

- **WHEN** user runs `secondbrain list`
- **THEN** system returns list of unique source files
- **AND** shows: source_file, chunk_count, file_type, ingested_at

#### Scenario: List chunks for specific file

- **WHEN** user runs `secondbrain list --source file.pdf`
- **THEN** system returns all chunks from that file
- **AND** shows: chunk_id, chunk_index, page_number, text_preview

#### Scenario: List by chunk ID

- **WHEN** user runs `secondbrain list --chunk-id <uuid>`
- **THEN** system returns specific chunk details
- **AND** shows: full text, metadata

#### Scenario: List with pagination

- **WHEN** user runs `secondbrain list --limit 10 --offset 20`
- **THEN** system returns chunks 20-30
- **AND** shows total count for pagination UI

#### Scenario: List empty database

- **WHEN** user runs `secondbrain list` but no documents ingested
- **THEN** system reports "No documents found"
- **AND** suggests running ingest command

### Requirement: Delete Documents

The system SHALL delete documents and chunks from the database.

#### Scenario: Delete by source file

- **WHEN** user runs `secondbrain delete --source file.pdf`
- **THEN** system removes all chunks from that file
- **AND** confirms deletion with count

#### Scenario: Delete specific chunk

- **WHEN** user runs `secondbrain delete --chunk-id <uuid>`
- **THEN** system removes that specific chunk only
- **AND** confirms deletion

#### Scenario: Delete all documents

- **WHEN** user runs `secondbrain delete --all`
- **THEN** system prompts for confirmation
- **AND** removes all documents and embeddings
- **AND** confirms "Database cleared"

#### Scenario: Delete with filter

> **Annotation (2026-10-08):** Now implemented — `delete --file-type` (src/secondbrain/cli/search.py, Deleter.delete(file_type=...)); accepts extensions and category aliases.

- **WHEN** user runs `secondbrain delete --file-type pdf`
- **THEN** system removes all PDF document chunks

#### Scenario: Delete confirmation

- **WHEN** user attempts destructive delete
- **THEN** system requires --force flag for non-interactive use
- **AND** warns about data loss

### Requirement: Database Statistics

The system SHALL provide database statistics and health information.

#### Scenario: Show statistics

> **Annotation (2026-10-08):** Storage size (approximate) and connection status now shown by `status` (StatusChecker.connection_status / estimate_storage_size, src/secondbrain/management/__init__.py).

- **WHEN** user runs `secondbrain status`
- **THEN** system shows:
  - Total documents
  - Total chunks
  - Storage size (approximate)
  - Database connection status

#### Scenario: Index status

- **WHEN** user runs `secondbrain status`
- **THEN** system reports vector index status
- **AND** shows if index is healthy
