# Architecture

Technical architecture and system design for SecondBrain.

## Components

SecondBrain consists of layered components that work together to provide document intelligence:

| Layer | Components | Responsibility |
|-------|------------|----------------|
| CLI Interface | `cli/commands.py` | User-facing commands (ingest, search, chat, etc.) |
| Configuration | `config/` | Environment variable management via Pydantic |
| Document Processing | `document/` | Parsing and chunking of supported file types |
| Embedding | `embed/` | Vector generation via OpenAI-compatible API |
| Storage | `storage/` | MongoDB vector storage and retrieval |
| Search | `search/` | Similarity search and ranking |
| RAG | `rag/` | Retrieval-augmented generation for chat |
| Utils | `utils/` | Docker management, performance monitoring |

## Data Flow

See [Data Flow](DATA_FLOW.md) for detailed processing pipeline.

## Schema

See [Schema Reference](SCHEMA.md) for MongoDB document structure.

## Technology Stack

| Component | Technology |
|-----------|------------|
| CLI Framework | Click 8.x |
| Document Parsing | Docling 2.x |
| Database | MongoDB with $vectorSearch |
| Drivers | PyMongo (sync), Motor (async) |
| HTTP Client | httpx |
| Data Validation | Pydantic 2.x |
| Async | asyncio native |
| Observability | OpenTelemetry |

## Key Design Decisions

### 1. Separation of Concerns

Each module has a focused responsibility:
- `document/` handles parsing only
- `embed/` handles embeddings only
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

Using MongoDB's native `$vectorSearch` for similarity retrieval:
- No separate vector database required
- Leverages existing MongoDB infrastructure
- Server-side similarity computation

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
    │ (HTTP)  │           │ (MongoDB) │          │ (LLM API) │
    └────┬────┘           └─────┬─────┘          └─────┬─────┘
         │                      │                      │
         └──────────────────────▼──────────────────────┘
```