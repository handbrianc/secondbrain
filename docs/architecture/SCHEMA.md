# Database Schema

SecondBrain uses MongoDB for vector storage and document management.

## Collections

### documents

Main collection for storing documents and their embeddings.

```json
{
  "_id": "unique-document-id",
  "title": "Document Title",
  "content": "Document text content...",
  "metadata": {
    "source": "file.pdf",
    "author": "John Doe",
    "created_at": "2026-03-28T12:00:00Z",
    "file_size": 1024,
    "mime_type": "application/pdf"
  },
  "embeddings": [0.1, 0.2, 0.3, ...],
  "chunks": [
    {
      "chunk_id": "chunk-1",
      "text": "First chunk text...",
      "embedding": [0.1, 0.2, 0.3, ...],
      "start_offset": 0,
      "end_offset": 500
    }
  ],
  "created_at": "2026-03-28T12:00:00Z",
  "updated_at": "2026-03-28T12:00:00Z"
}
```

**Indexes:**
- `_id`: Primary key
- `embeddings`: Vector index for similarity search
- `metadata.source`: For filtering by source
- `created_at`: For time-based queries

### collections

Logical grouping of documents.

```json
{
  "_id": "collection-id",
  "name": "finance-docs",
  "description": "Financial documents",
  "document_ids": ["doc-1", "doc-2", ...],
  "created_at": "2026-03-28T12:00:00Z",
  "metadata": {
    "owner": "user@example.com",
    "tags": ["finance", "reports"]
  }
}
```

## Vector Index Configuration

### MongoDB Vector Index

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embeddings",
      "numDimensions": 384,
      "similarity": "cosine"
    }
  ]
}
```

**Parameters:**
- `numDimensions`: Embedding dimension (384 for all-MiniLM-L6-v2)
- `similarity`: Cosine similarity for semantic search

### Performance Tuning

```python
# Create vector index
collection.create_index(
    [("embeddings", "vector")],
    options={
        "numDimensions": 384,
        "similarity": "cosine"
    }
)
```

## Data Types

### Document Metadata

Standard metadata fields:

```python
from pydantic import BaseModel

class DocumentMetadata(BaseModel):
    source: str
    author: Optional[str] = None
    created_at: datetime
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    tags: List[str] = []
    custom: Dict[str, Any] = {}
```

### Embedding Configuration

```python
class EmbeddingConfig(BaseModel):
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384
    device: str = "cpu"
    batch_size: int = 32
```

## Query Examples

### Vector Similarity Search

```python
pipeline = [
    {
        "$vectorSearch": {
            "index": "vector_index",
            "queryVector": [0.1, 0.2, ...],
            "path": "embeddings",
            "limit": 10,
            "numCandidates": 100
        }
    },
    {
        "$project": {
            "_id": 1,
            "title": 1,
            "content": 1,
            "score": {"$meta": "vectorSearchScore"}
        }
    }
]
```

### Metadata Filtering

```python
pipeline = [
    {
        "$match": {
            "metadata.source": {"$regex": "\\.pdf$"}
        }
    },
    {
        "$vectorSearch": {
            "index": "vector_index",
            "queryVector": [...],
            "path": "embeddings",
            "limit": 10
        }
    }
]
```

## Data Retention

### Automatic Cleanup

Configure TTL indexes for automatic document expiration:

```python
collection.create_index(
    [("expires_at", 1)],
    expireAfterSeconds=0
)
```

### Backup Strategy

```bash
# MongoDB backup
mongodump --db secondbrain --out /backup/

# Restore
mongorestore --db secondbrain /backup/secondbrain
```

## See Also

- [Data Flow](DATA_FLOW.md) - How data moves through the system
- [API Reference](../api/index.md) - Programmatic access
- [Configuration](../developer-guide/configuration.md) - Database setup
