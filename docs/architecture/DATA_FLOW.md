# Data Flow

This document describes how data flows through the SecondBrain system.

## Ingestion Pipeline

### Step-by-Step Flow

```
┌──────────────┐
│  Input File  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Parser     │ (Docling)
│ - PDF        │
│ - DOCX       │
│ - TXT        │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Chunker    │
│ - Split text │
│ - Overlap    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Embedder   │ (Sentence Transformers)
│ - Encode     │
│ - Batch      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Storage    │ (MongoDB)
│ - Index      │
│ - Persist    │
└──────────────┘
```

### Detailed Steps

#### 1. File Parsing

```python
# Input: File path
# Output: Raw text

from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("document.pdf")
text = result.text
```

**Processing:**
- Detect file format
- Extract text content
- Preserve structure (headings, lists)
- Handle encoding

#### 2. Text Chunking

```python
# Input: Raw text
# Output: List of chunks

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks
```

**Parameters:**
- `chunk_size`: Target chunk length (default: 500 tokens)
- `overlap`: Overlap between chunks (default: 50 tokens)

#### 3. Embedding Generation

```python
# Input: List of text chunks
# Output: List of embeddings

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(chunks, batch_size=32)
```

**Optimization:**
- Batch processing for speed
- GPU acceleration when available
- Model caching

#### 4. Storage

```python
# Input: Documents with embeddings
# Output: Stored in MongoDB

document = {
    "id": uuid.uuid4(),
    "content": chunk,
    "embeddings": embedding.tolist(),
    "metadata": {...}
}
collection.insert_one(document)
```

**Indexing:**
- Create vector index
- Build metadata indexes
- Optimize for search

## Search Pipeline

### Query Flow

```
┌──────────────┐
│   User Query │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Embedder   │
│ - Encode     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Vector Search│
│ - Similarity │
│ - Ranking    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Results    │
│ - Top-K      │
│ - Scoring    │
└──────────────┘
```

### Search Steps

#### 1. Query Embedding

```python
query_embedding = model.encode(["user question"])
```

#### 2. Vector Search

```python
pipeline = [
    {"$vectorSearch": {
        "queryVector": query_embedding[0].tolist(),
        "path": "embeddings",
        "limit": 10
    }}
]
results = list(collection.aggregate(pipeline))
```

#### 3. Result Processing

```python
# Format results
formatted = [
    {
        "id": doc["_id"],
        "content": doc["content"],
        "score": doc["score"],
        "metadata": doc["metadata"]
    }
    for doc in results
]
```

## RAG Pipeline

### Retrieval-Augmented Generation

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Query      │────▶│  Search      │────▶│  Context     │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                                                  ▼
                                    ┌──────────────────────┐
                                    │   LLM Generation     │
                                    └──────────┬───────────┘
                                               │
                                               ▼
                                    ┌──────────────────────┐
                                    │   Response           │
                                    └──────────────────────┘
```

## Async Processing

### Event-Driven Architecture

```python
import asyncio
from motor.motor_asyncio import AsyncMongoCollection

async def ingest_document(file_path: str):
    # Parse
    text = await parse_file_async(file_path)
    
    # Chunk
    chunks = chunk_text(text)
    
    # Embed
    embeddings = await generate_embeddings_async(chunks)
    
    # Store
    await collection.insert_many([...])
```

### Connection Pooling

```python
# MongoDB connection pool
client = AsyncMongoClient(
    "mongodb://localhost:27017",
    maxPoolSize=10,
    minPoolSize=5
)
```

## Performance Metrics

### Ingestion Speed

- **Parsing**: ~100-500 pages/minute (PDF)
- **Embedding**: ~1000-5000 chunks/second (GPU)
- **Storage**: ~1000-10000 docs/second

### Search Latency

- **Query Embedding**: ~10-50ms
- **Vector Search**: ~5-20ms
- **Total**: ~20-100ms

## See Also

- [Schema](SCHEMA.md) - Database structure
- [API Reference](../api/index.md) - Programmatic access
- [Async API](../developer-guide/async-api.md) - Async operations
