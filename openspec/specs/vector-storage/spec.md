# Vector Storage

## Purpose

Store embedding vectors with complete file and chunk metadata in the vector database (Qdrant):
vector index creation, duplicate handling, bulk insert, and connection configuration/validation.

> **Provenance (2026-10-15):** Promoted from the archived change delta
> `openspec/changes/archive/2026-03-06-secondbrain/specs/vector-storage/spec.md` — the delta marker
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
> Most relevant here: the entire storage migration (Qdrant, including vector-index and connection scenarios)
> and the duplicate-handling inversion (SHA256 `text_hash` dedup default-on).

## Requirements

### Requirement: Vector Storage

The system SHALL store embedding vectors in MongoDB with complete metadata.

#### Scenario: Store embedding with metadata

- **WHEN** system generates embedding for a chunk
- **THEN** it stores in MongoDB:
  - chunk_id (UUID)
  - source_file (filename)
  - page_number (if applicable)
  - chunk_text (the text content)
  - embedding (384-dim vector)
  - metadata (file_type, ingested_at, chunk_index)

#### Scenario: MongoDB connection

- **WHEN** system needs to store vectors
- **THEN** it connects to MongoDB using SECONDBRAIN_MONGO_URI
- **AND** uses database name from SECONDBRAIN_MONGO_DB (default: "secondbrain")
- **AND** uses collection from SECONDBRAIN_MONGO_COLLECTION (default: "embeddings")

#### Scenario: Create vector index

- **WHEN** system stores first embedding
- **THEN** it creates vector search index on embedding field
- **AND** uses cosine similarity metric

#### Scenario: Connection failure

- **WHEN** MongoDB is not available
- **THEN** system reports connection error
- **AND** suggests checking Docker Compose status
- **AND** does not proceed without valid connection

#### Scenario: Duplicate handling

- **WHEN** user ingests same file again
- **THEN** system creates new entries (allows duplicates)
- **OR** optionally replaces existing (--replace flag)

#### Scenario: Bulk insert

- **WHEN** system has multiple embeddings to store
- **THEN** it uses bulk insert for efficiency
- **AND** commits in batches

### Requirement: Metadata Storage

The system SHALL store comprehensive metadata alongside embeddings.

#### Scenario: File metadata

- **WHEN** system stores document embedding
- **THEN** it records:
  - source_file (full path or filename)
  - file_type (pdf, docx, etc.)
  - file_size (bytes)
  - file_hash (SHA256 for deduplication)
  - ingested_at (timestamp)

#### Scenario: Chunk metadata

- **WHEN** system stores chunk embedding
- **THEN** it records:
  - chunk_index (position in document)
  - chunk_text (content)
  - page_number (if PDF/DOCX)
  - char_count (text length)

### Requirement: MongoDB Configuration

The system SHALL use environment variables for all MongoDB configuration.

#### Scenario: Default MongoDB URI

- **WHEN** SECONDBRAIN_MONGO_URI is not set
- **THEN** system uses mongodb://localhost:27017

#### Scenario: Custom database name

- **WHEN** user sets SECONDBRAIN_MONGO_DB
- **THEN** system uses specified database

#### Scenario: Collection configuration

- **WHEN** user sets SECONDBRAIN_MONGO_COLLECTION
- **THEN** system uses specified collection

#### Scenario: Connection validation

- **WHEN** system starts any operation
- **THEN** it validates MongoDB connectivity first
- **AND** reports clear error if unavailable

### Requirement: Structural payload fields populated

When a document has a stored structure tree, every stored chunk point SHALL
carry structural payload fields: `node_id`, `heading_path`, `chapter_id`,
`section_id`, `section_label` (alongside the existing `chunk_role`,
`element_type`, and page fields). Documents without a tree SHALL store chunks
without these fields. `chunk_role` SHALL join the indexed payload fields so
role filters are index-backed.

#### Scenario: Annotated chunks store their structural fields

- **WHEN** chunks of a tree-ful document are stored
- **THEN** each point payload carries `node_id`, `heading_path`,
  `chapter_id`, `section_id`, `section_label`
- **AND** a payload index exists on `chunk_role`

#### Scenario: Treeless chunks omit the fields

- **WHEN** chunks of a document without a tree are stored
- **THEN** the structural fields are absent from their payloads

### Requirement: Structural payload refresh on re-ingest

Re-ingest SHALL refresh the structural payload fields of already-stored points
for the re-ingested document (batched read-modify-write targeted at points
missing `node_id`) so dedup-skipped points become queryable without
regenerating their embeddings.

#### Scenario: Dedup-skipped points gain structure

- **WHEN** a document is re-ingested and all its chunk texts hash-match
  already-stored points
- **THEN** the stored points' payloads gain the structural fields
- **AND** no embeddings are regenerated for them
