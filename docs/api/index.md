# API Reference

Complete API reference for SecondBrain's Python SDK and async API.

## Core Classes

### Document

Represents a document in the system.

```python
from secondbrain.document import Document

doc = Document(
    id="unique-id",
    title="Document Title",
    content="Document content...",
    metadata={"source": "file.pdf", "author": "John Doe"}
)
```

**Properties:**
- `id`: str - Unique document identifier
- `title`: str - Document title
- `content`: str - Document text content
- `metadata`: dict - Additional metadata
- `embeddings`: Optional[list[float]] - Vector embeddings

### Storage

Abstract storage interface.

```python
from secondbrain.storage import MongoDBStorage

storage = MongoDBStorage(
    uri="mongodb://localhost:27017",
    database="secondbrain"
)
```

**Methods:**
- `store_document(doc: Document) -> str`: Store a document
- `get_document(id: str) -> Optional[Document]`: Retrieve document
- `delete_document(id: str) -> bool`: Delete document
- `list_documents() -> List[Document]`: List all documents
- `search(query: str, limit: int = 10) -> List[Document]`: Semantic search

### Ingestor

Document ingestion pipeline.

```python
from secondbrain.ingestor import DocumentIngestor

ingestor = DocumentIngestor(
    storage=storage,
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    chunk_size=500,
    chunk_overlap=50
)

ingestor.ingest_file("document.pdf")
```

**Methods:**
- `ingest_file(path: str) -> List[str]`: Ingest single file
- `ingest_directory(path: str, recursive: bool = False) -> List[str]`: Ingest directory
- `ingest_batch(paths: List[str]) -> List[str]`: Batch ingestion

## Async API

All core classes support async operations.

```python
import asyncio
from secondbrain.storage import MongoDBStorage

async def main():
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    
    # Async operations
    await storage.store_document(doc)
    result = await storage.search("query", limit=10)
    
    return result

asyncio.run(main())
```

## Configuration

### Environment Variables

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "secondbrain"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 500
    chunk_overlap: int = 50
    
    class Config:
        env_file = ".env"
```

## Error Handling

```python
from secondbrain.exceptions import (
    DocumentNotFoundError,
    StorageError,
    IngestionError
)

try:
    doc = storage.get_document("nonexistent-id")
except DocumentNotFoundError:
    print("Document not found")
except StorageError as e:
    print(f"Storage error: {e}")
```

## Advanced Features

### Custom Embedding Models

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("custom-model-name")
embeddings = model.encode(["text to embed"])
```

### Batch Processing

```python
from secondbrain.ingestor import BatchIngestor

ingestor = BatchIngestor(
    storage=storage,
    batch_size=100,
    max_workers=4
)

ingestor.ingest_batch(document_paths)
```

### GPU Acceleration

```python
import torch

# Enable GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"

model = SentenceTransformer("model-name", device=device)
```

## See Also

- [Getting Started](../getting-started/index.md)
- [User Guide](../user-guide/index.md)
- [Developer Guide](../developer-guide/index.md)

---

For more information, see the source code documentation or open an issue on GitHub.
