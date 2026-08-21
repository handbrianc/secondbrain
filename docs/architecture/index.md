# Architecture

Technical architecture and system design for SecondBrain.

## Components

SecondBrain consists of layered components that work together to provide document intelligence:

| Layer | Components | Responsibility |
| ------- | ------------ | ---------------- |
| CLI Interface | `cli/` | User-facing commands (ingest, search, chat, etc.) |
| Configuration | `config/` | Environment variable management via Pydantic |
| Document Processing | `document/` | Parsing and chunking of supported file types |
| Embedding | `embedding/` | Vector generation via OpenAI-compatible API |
| Storage | `storage/` | Qdrant vector storage and retrieval |
| Search | `search/` | Similarity search and ranking |
| RAG | `rag/` | Retrieval-augmented generation for chat |
| Utils | `utils/` | Circuit breaker, tracing, caching, Docker management, performance monitoring |
| Management | `management/` | List/delete/status operations for stored documents |

## Data Flow

See [Data Flow](DATA_FLOW.md) for detailed processing pipeline.

## Schema

See [Schema Reference](SCHEMA.md) for Qdrant payload and SQLite schema.

## Technology Stack

| Component | Technology |
| ----------- | ------------ |
| CLI Framework | Click 8.x |
| Document Parsing | Docling 2.x |
| Vector Database | Qdrant with cosine similarity |
| Conversations | SQLite (sessions/messages) |
| Drivers | qdrant-client, sqlite3 |
| HTTP Client | httpx |
| Data Validation | Pydantic 2.x |
| Async | asyncio native |
| Observability | OpenTelemetry |

## Key Design Decisions

### 1. Separation of Concerns

Each module has a focused responsibility:

- `document/` handles parsing only
- `embedding/` handles embeddings only
- `storage/` handles persistence only

This allows independent testing and replacement of components.

### 2. Async-First Design

Storage layer supports both sync and async operations via abstract interfaces:

- Sync: Blocking operations for CLI simplicity
- Async: Concurrent operations for API performance

### 3. Configuration-Driven

All settings via environment variables following 12-factor app principles:

- `SECONDBRAIN_*` prefix for all config
- Pydantic validation at startup
- Test-aware configuration switching

### 4. Local-First Privacy

Core processing always happens on-host:

- Document parsing: Local with Docling
- Chunking: Local algorithm
- Only embedding generation may contact external APIs

### 5. Vector Search Foundation

Using Qdrant for vector similarity retrieval:

- All chunk metadata stored in the Qdrant payload, so search needs one round trip
- Cosine similarity for ranking
- Chosen backend selected via `SECONDBRAIN_STORAGE_BACKEND` (`qdrant` or `mock`)

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Interface                            │
│  ingest ── search ── ls ── delete ── chat ── status ── health  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    Document Layer     │
                    │   (Docling Parser)    │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │    Chunking Engine    │
                    │  (Character Splitter) │
                    └───────────┬───────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
    ┌────▼────┐           ┌─────▼─────┐          ┌─────▼─────┐
    │ Embedder│           │  Storage  │          │   RAG     │
    │ (HTTP)  │           │ (Qdrant)  │          │ (LLM API) │
    └────┬────┘           └─────┬─────┘          └─────┬─────┘
         │                      │                      │
         └──────────────────────▼──────────────────────┘
```
