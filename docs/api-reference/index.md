# API Reference

This section provides detailed documentation for all SecondBrain public APIs.

## Overview

SecondBrain provides both synchronous and asynchronous APIs for document intelligence operations:

- **CLI**: Command-line interface using Click
- **Core Modules**: Document ingestion, embedding generation, storage, and search
- **Configuration**: Environment-based configuration with Pydantic
- **Types**: Type definitions and data models

## API Modules

### Command-Line Interface
- [CLI Reference](./cli.md) - All CLI commands and options

### Core Functionality
- [Document Ingestion](./document.md) - Multi-format document processing
- [Embedding Generation](./embedding.md) - sentence-transformers integration with rate limiting
- [Storage](./storage.md) - MongoDB vector storage with batch operations
- [Search](./search.md) - Semantic search with cosine similarity

### Supporting Modules
- [Configuration](./config.md) - Pydantic-based configuration management
- [Logging](./logging.md) - Rich JSON logging and health checks
- [Exceptions](./exceptions.md) - Custom exception hierarchy
- [Types](./types.md) - Type definitions and data models

## Getting Started

### Synchronous API

```python
from secondbrain import SecondBrain

# Initialize
sb = SecondBrain()

# Ingest documents
sb.ingest("/path/to/documents/")

# Search
results = sb.search("semantic query", top_k=5)

for result in results:
    print(f"Score: {result.score}, Text: {result.text}")
```

### Asynchronous API

```python
import asyncio
from secondbrain import AsyncSecondBrain

async def main():
    sb = AsyncSecondBrain()
    
    # Async ingestion
    await sb.ingest("/path/to/documents/")
    
    # Async search
    results = await sb.search("semantic query", top_k=5)
    
    for result in results:
        print(f"Score: {result.score}, Text: {result.text}")

asyncio.run(main())
```

## Navigation

- [Getting Started](../getting-started/index.md) - Installation and quick start
- [User Guide](../user-guide/index.md) - Usage guides and examples
- [Developer Guide](../developer-guide/index.md) - Development documentation
- [Architecture](../architecture/index.md) - System design and data flow
