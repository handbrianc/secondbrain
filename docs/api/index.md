# API Reference

Auto-generated API documentation from docstrings using MkDocs + mkdocstrings.

## Overview

SecondBrain exposes a Python API alongside its CLI for programmatic use.

## Installation for Library Use

```bash
pip install secondbrain
```

Or in development mode:

```bash
pip install -e .
```

## Core Modules

### Configuration

**File**: `src/secondbrain/config/__init__.py`

```python
from secondbrain.config import config, Config

# Get singleton config
cfg = config()

# Access settings
uri = cfg.mongo_uri
chunk_size = cfg.chunk_size
```

**Config Class** — Settings loaded from `SECONDBRAIN_*` environment variables.

### Document Ingestion

**File**: `src/secondbrain/document/__init__.py`

```python
from secondbrain.document import DocumentIngestor

ingestor = DocumentIngestor(
    chunk_size=4096,
    chunk_overlap=50,
    verbose=True
)

results = ingestor.ingest(
    path="./documents/",
    recursive=True,
    batch_size=10,
    cores=None  # Auto-detect
)
```

**DocumentIngestor** — Parses and chunks supported file types into vectorizable chunks.

### Search

**File**: `src/secondbrain/search/__init__.py`

```python
from secondbrain.search import Searcher

with Searcher() as searcher:
    results = searcher.search(
        query="semantic search query",
        top_k=20,
        source_filter=None,
        file_type_filter=None
    )
```

**Searcher** — Performs vector similarity search via MongoDB $vectorSearch.

### Storage

**File**: `src/secondbrain/storage/`

Synchronous storage client:

```python
from secondbrain.storage.client import StorageClient

client = StorageClient()
client.connect()
client.store(document)
results = client.search(vector, top_k=10)
```

Async storage client:

```python
from secondbrain.storage.async_client import AsyncStorageClient

async with AsyncStorageClient() as client:
    results = await client.search(vector, top_k=10)
```

### Embedding Generation

**File**: `src/secondbrain/embed/generator.py`

```python
from secondbrain.embed.generator import EmbeddingGenerator

gen = EmbeddingGenerator()

# Single embedding
vec = gen.generate("text to embed")

# Batch
vectors = gen.generate_batch(["text1", "text2"])

# Async
vec = await gen.generate_async("text to embed")
```

### Management Operations

**File**: `src/secondbrain/management/`

```python
from secondbrain.management import Lister, Deleter, StatusChecker

# List chunks
lister = Lister()
chunks = lister.list_chunks(limit=100)

# Delete documents
deleter = Deleter()
count = deleter.delete(source="/path/to/file.pdf")

# Check status
checker = StatusChecker()
stats = checker.get_status()
```

### RAG Pipeline

**File**: `src/secondbrain/rag/`

```python
from secondbrain.rag import RAGPipeline
from secondbrain.rag.providers import LLMProviderFactory

pipeline = RAGPipeline(
    searcher=searcher,
    llm_provider=llm_provider,
    top_k=10,
    context_window=5
)

result = pipeline.chat(
    query="What is the topic?",
    session=conversation_session,
    show_sources=True
)
```

## CLI API

The CLI entry point is exposed as a library function:

```python
from secondbrain.cli import main

# Equivalent to calling `secondbrain` from command line
main()
```

## Type References

### ChunkInfo

```python
from secondbrain.storage import ChunkInfo

@dataclass
class ChunkInfo:
    chunk_id: str
    text: str
    source: str
    page: int
    file_type: str
    score: float | None = None
    chunk_index: int = 0
    created_at: datetime | None = None
```

### Document

```python
from secondbrain.document import Document

@dataclass
class Document:
    source: Path
    file_type: str
    text: str
    chunks: list[Chunk]
    metadata: dict[str, Any]
```

### ConversationSession

```python
from secondbrain.conversation import ConversationSession

session = ConversationSession.create(storage=storage)
session.add_user_message("Question here")
response = session.get_assistant_response()
```

## Exception Types

```python
from secondbrain.exceptions import (
    SecondBrainError,
    StorageConnectionError,
    ServiceUnavailableError,
    CLIValidationError,
    DocumentParseError,
    EmbeddingError
)

try:
    # operations
except SecondBrainError as e:
    logger.error(f"SecondBrain error: {e}")
```

## Usage Examples

### Simple Ingestion Script

```python
from secondbrain.document import DocumentIngestor
from secondbrain.embed.generator import EmbeddingGenerator
from secondbrain.storage.client import StorageClient

def ingest_and_index(path: str):
    # Ingest
    ingestor = DocumentIngestor(chunk_size=4096)
    doc = ingestor.ingest_single(path)

    # Generate embeddings
    gen = EmbeddingGenerator()
    vectors = gen.generate_batch([c.text for c in doc.chunks])

    # Store
    client = StorageClient()
    for chunk, vec in zip(doc.chunks, vectors):
        client.store({**asdict(chunk), "vector": vec})

if __name__ == "__main__":
    ingest_and_index("./report.pdf")
```

### Batch Search

```python
from secondbrain.search import Searcher
from secondbrain.embed.generator import EmbeddingGenerator

def search_multiple(queries: list[str], top_k: int = 5):
    gen = EmbeddingGenerator()
    searcher = Searcher()

    results = {}
    for q in queries:
        vec = gen.generate(q)
        results[q] = searcher.search(vec, top_k=top_k)

    return results

if __name__ == "__main__":
    answers = search_multiple([
        "What is machine learning?",
        "Explain neural networks"
    ])
```

### Interactive Chat

```python
from secondbrain.chat import InteractiveChat

chat = InteractiveChat(
    session_name="research",
    model="gpt-4o-mini",
    show_sources=True
)

while True:
    query = input("You: ")
    if query.lower() in ("quit", "exit"):
        break
    response = chat.ask(query)
    print(f"Assistant: {response}")
```