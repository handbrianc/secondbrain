# API Reference

Auto-generated API documentation for SecondBrain.

## Core Modules

### secondbrain

Main package containing all SecondBrain functionality.

```python
import secondbrain
```

### secondbrain.types

Type definitions and data models.

```python
from secondbrain.types import Document, Chunk, SearchResult
```

## Configuration

### secondbrain.config

Configuration management with Pydantic.

```python
from secondbrain.config import SecondBrainConfig

config = SecondBrainConfig()
```

## Document Processing

### secondbrain.document

Document ingestion and parsing.

```python
from secondbrain.document import DocumentParser
```

## Embedding

### secondbrain.embedding.local

Local embedding generation via sentence-transformers.

```python
from secondbrain.embedding.local import LocalEmbedder
```

## Storage

### secondbrain.storage.models

Database models and schemas.

```python
from secondbrain.storage.models import EmbeddingDocument
```

### secondbrain.storage.storage

Document storage operations.

```python
from secondbrain.storage.storage import DocumentStorage
```

### secondbrain.storage.pipeline

Ingestion pipeline.

```python
from secondbrain.storage.pipeline import IngestionPipeline
```

## Search

### secondbrain.search

Semantic search functionality.

```python
from secondbrain.search import SemanticSearch
```

## CLI

### secondbrain.cli.commands

CLI command implementations.

```python
from secondbrain.cli.commands import ingest, search, list_docs
```

### secondbrain.cli.display

Output formatting and display.

```python
from secondbrain.cli.display import DisplayFormatter
```

### secondbrain.cli.errors

CLI error handling.

```python
from secondbrain.cli.errors import CLIError
```

## Utilities

### secondbrain.utils.circuit_breaker

Circuit breaker pattern implementation.

```python
from secondbrain.utils.circuit_breaker import CircuitBreaker
```

### secondbrain.utils.connections

Connection management.

```python
from secondbrain.utils.connections import ConnectionManager
```

### secondbrain.utils.embedding_cache

Embedding cache with LRU eviction.

```python
from secondbrain.utils.embedding_cache import EmbeddingCache
```

### secondbrain.utils.perf_monitor

Performance monitoring utilities.

```python
from secondbrain.utils.perf_monitor import PerformanceMonitor
```

## Logging

### secondbrain.logging

Structured logging configuration.

```python
from secondbrain.logging import setup_logging
```

## Management

### secondbrain.management

Database management operations.

```python
from secondbrain.management import DatabaseManager
```

## Exceptions

### secondbrain.exceptions

Custom exception classes.

```python
from secondbrain.exceptions import (
    SecondBrainError,
    ConfigurationError,
    ConnectionError,
    DocumentError,
)
```
