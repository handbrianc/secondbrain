# Embedding Generation

## Purpose

Generate vector embeddings for text chunks via a pluggable OpenAI-compatible embedding API:
batching, caching, model selection, and connection/failure handling.

> **Provenance (2026-10-15):** Promoted from the archived change delta
> `openspec/changes/archive/2026-03-06-secondbrain/specs/embedding-generation/spec.md` — the delta marker
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
> Most relevant here: the embedding model/dimension defaults, the embedding env-var renames, the
> cache-implemented inversion, the chunk-size default, and the Text Chunking word-aligned annotation below.

## Requirements

### Requirement: Embedding Generation

The system SHALL generate semantic embeddings for text chunks using OpenAI-compatible API with embeddinggemma:latest model.

#### Scenario: Generate embedding for text

- **WHEN** user ingests a document with extracted text
- **THEN** the system chunks text into segments
- **AND** generates embedding vector for each chunk using OpenAI-compatible API API
- **AND** returns 384-dimensional vectors (embeddinggemma output)

#### Scenario: OpenAI-compatible API service unavailable

- **WHEN** user attempts ingestion but OpenAI-compatible API is not running
- **THEN** the system reports connection error
- **AND** suggests checking if OpenAI-compatible API service is started
- **AND** does not proceed without valid connection

#### Scenario: Model not pulled

- **WHEN** user runs ingestion but embeddinggemma:latest is not available
- **THEN** the system automatically pulls the model
- **AND** reports pull progress
- **AND** continues with embedding generation

#### Scenario: Embedding cache

- **WHEN** user ingests same document twice
- **THEN** the system regenerates embeddings (no cache for now)
- **AND** allows force regeneration via flag

#### Scenario: Custom embedding model

- **WHEN** user sets SECONDBRAIN_MODEL environment variable
- **THEN** the system uses specified model instead of default
- **AND** validates model is available in OpenAI-compatible API

#### Scenario: Batch embedding generation

- **WHEN** system has multiple chunks to embed
- **THEN** the system sends batches to OpenAI-compatible API API
- **AND** processes efficiently to minimize API calls

### Requirement: Text Chunking

The system SHALL split documents into overlapping text chunks for embedding.

> **Note (2026-10-11):** Historical text below is preserved unchanged; the shipped chunker intentionally
> deviates from the "Preserve semantic boundaries" scenario. The shipped chunker
> (`src/secondbrain/document/chunker.py`) does not prefer sentence boundaries: it produces word-aligned,
> overlapping chunks with guaranteed size/overlap bounds — merging small segments, title detection, and
> overlap are all computed on word boundaries, so no chunk exceeds `chunk_size` and every consecutive pair
> overlaps by the configured amount. Sentence-boundary preference was deliberately not implemented; the
> algorithm is covered by invariant tests (chunk size, overlap, boundary and no-text-loss properties in
> `tests/test_document/test_chunking.py` and the property-based suite). This annotation records the
> word-aligned decision; the scenario text itself is retained as original intent, not shipped behavior.

#### Scenario: Fixed-size chunking

- **WHEN** system processes extracted text
- **THEN** it splits into chunks of configurable size (default: 512 chars)
- **AND** applies overlap between chunks (default: 50 chars)

#### Scenario: Preserve semantic boundaries

- **WHEN** chunk would split a sentence
- **THEN** the system prefers to break at sentence boundaries
- **AND** adjusts chunk size to respect natural breaks

#### Scenario: Empty chunk handling

- **WHEN** extracted text is empty or whitespace only
- **THEN** the system skips generating embedding for that chunk
- **AND** logs warning

### Requirement: OpenAI-compatible API Configuration

The system SHALL connect to OpenAI-compatible API via configurable URL and validate connectivity.

#### Scenario: Default OpenAI-compatible API URL

- **WHEN** SECONDBRAIN_SENTENCE_TRANSFORMERS_URL is not set
- **THEN** system connects to <http://localhost:local> embedding

#### Scenario: Custom OpenAI-compatible API URL

- **WHEN** user sets SECONDBRAIN_SENTENCE_TRANSFORMERS_URL to custom URL
- **THEN** system connects to specified URL
- **AND** validates connection before operations

#### Scenario: Connection timeout

- **WHEN** OpenAI-compatible API does not respond within timeout
- **THEN** system reports timeout error
- **AND** allows retry
