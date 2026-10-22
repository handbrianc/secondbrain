# Semantic Search

## Purpose

Semantic search over stored embeddings using cosine similarity: query embedding, configurable top-k
with similarity filtering, result formatting (default/verbose/JSON), and fast response times.

> **Provenance (2026-10-15):** Promoted from the archived change delta
> `openspec/changes/archive/2026-03-06-secondbrain/specs/semantic-search/spec.md` — the delta marker
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
> Most relevant here: the default top-k (5 → 50) and the minimum-similarity threshold filter, the storage
> target, and the display drift.

## Requirements

### Requirement: Semantic Search

The system SHALL perform semantic search using cosine similarity on stored embeddings.

#### Scenario: Search with text query

- **WHEN** user runs `secondbrain search "query text"`
- **THEN** system generates embedding for query text
- **AND** performs cosine similarity search in MongoDB
- **AND** returns top-k results (default: 5)

#### Scenario: Custom result count

- **WHEN** user runs `secondbrain search "query" --top-k 10`
- **THEN** system returns top 10 results instead of default

#### Scenario: Search results format

- **WHEN** user performs search
- **THEN** results include:
  - chunk_text (matching text)
  - source_file (file it came from)
  - page_number (if available)
  - score (similarity score 0-1)

#### Scenario: Empty results

- **WHEN** search query has no similar results
- **THEN** system returns empty list
- **AND** reports "No results found"

#### Scenario: Search with filters

- **WHEN** user runs `secondbrain search "query" --source file.pdf`
- **THEN** system filters results to specific source file only

### Requirement: Search Result Display

The system SHALL format and display search results clearly.

#### Scenario: Default display

- **WHEN** user performs search without flags
- **THEN** results show:
  - Rank (1, 2, 3...)
  - Source file
  - Page number (if available)
  - Score (percentage)
  - Text preview (truncated to 200 chars)

#### Scenario: Verbose display

- **WHEN** user runs `secondbrain search "query" --verbose`
- **THEN** results show full text content
- **AND** all metadata

#### Scenario: JSON output

- **WHEN** user runs `secondbrain search "query" --json`
- **THEN** results output as JSON for scripting

### Requirement: Search Performance

The system SHALL optimize search for fast response times.

#### Scenario: Vector index usage

- **WHEN** system performs search
- **THEN** it uses MongoDB vector search index
- **AND** returns results within 1 second for <10k chunks

#### Scenario: Query embedding

- **WHEN** user submits search query
- **THEN** system generates embedding via OpenAI-compatible API
- **AND** uses same model as ingestion
