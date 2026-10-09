# API Reference

Python API reference for SecondBrain, generated from docstrings with
[mkdocstrings](https://mkdocstrings.github.io/). Every section below is
rendered directly from the package source in `src/secondbrain/`, so it stays
in sync with the code.

Install for library use:

```bash
pip install secondbrain
```

or in development mode:

```bash
pip install -e ".[dev]"
```

## Module Map

| Module | Purpose | Reference |
| ------ | ------- | --------- |
| `secondbrain.cli` | Click command-line interface (`secondbrain` entry point) | [CLI](cli.md) |
| `secondbrain.config` | `Config` singleton loaded from `SECONDBRAIN_*` environment variables | [Configuration](config.md) |
| `secondbrain.document` | Document parsing, chunking, and ingestion | [Document](document.md) |
| `secondbrain.embedding` | Embedding providers (OpenAI-compatible) | [Embedding](embedding.md) |
| `secondbrain.rag` | RAG pipeline and LLM providers (OpenAI, Anthropic) | [RAG](rag.md) |
| `secondbrain.search` | Semantic vector search | [Search](search.md) |
| `secondbrain.storage` | Qdrant vector storage and data models | [Storage](storage.md) |
| `secondbrain.conversation` | Chat sessions, history, and query rewriting | [Conversation](conversation.md) |
| `secondbrain.utils` | Circuit breaker, caching, rate limiting, tracing | [Utils](utils.md) |
| `secondbrain.logging` | Structured logging and health status | [Logging](logging.md) |
| `secondbrain.domain` | Domain entities, value objects, and interfaces | [Domain](domain.md) |
| `secondbrain.management` | List/delete/status operations over stored chunks | [Management](management.md) |

Additional support modules (no dedicated page): `secondbrain.exceptions`
(exception hierarchy), `secondbrain.constants` (tuning constants), and
`secondbrain.types` (shared type aliases).

## Typical Usage

```python
from secondbrain.document import DocumentIngestor
from secondbrain.search import Searcher

# Ingest documents
with DocumentIngestor() as ingestor:
    ingestor.ingest("./documents/", recursive=True)

# Search them
with Searcher() as searcher:
    results = searcher.search("semantic search query", top_k=10)
```

See the [User Guide](../user-guide/index.md) for command-line workflows and
the [Developer Guide](../developer-guide/index.md) for architecture notes.
