# Data Flow Architecture

Detailed data flow and component interactions in SecondBrain.

## High-Level Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Documents  │────▶│   Ingestor   │────▶│  Chunker    │
└─────────────┘     └──────────────┘     └─────────────┘
                                               │
                                               ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Search    │◀────│   Storage    │◀────│ Embeddings  │
└─────────────┘     └──────────────┘     └─────────────┘
```

## Ingestion Pipeline

### Step 1: Document Loading

```python
# Input: File path or directory
# Output: Raw text content

Parser Selection:
├── PDF → PDFParser
├── DOCX → DocxParser
├── PPTX → PptxParser
├── XLSX → XlsxParser
├── HTML → HTMLParser
├── Markdown → MarkdownParser
├── Image → OCRParser (Tesseract)
└── Audio → TranscriptionParser (Whisper)
```

### Step 2: Text Chunking

```python
# Input: Raw text
# Output: List of text chunks

Chunking Strategy:
1. Split by chunk_size (default: 4096 chars)
2. Apply overlap (default: 200 chars)
3. Preserve document metadata
4. Generate unique chunk IDs
```

### Step 3: Embedding Generation

```python
# Input: Text chunks
# Output: Vector embeddings

Process:
1. Batch chunks (default: 10 per batch)
2. Rate limit API calls (default: 10/sec)
3. Cache embeddings (LRU cache, default: 1000)
4. Call sentence-transformers API
5. Store embeddings with metadata
```

### Step 4: Storage

```python
# Input: Chunks + Embeddings + Metadata
# Output: MongoDB documents

Document Structure:
{
  "_id": ObjectId,
  "document_id": "uuid",
  "chunk_index": 0,
  "content": "text...",
  "embedding": [0.1, 0.2, ...],
  "metadata": {
    "filename": "doc.pdf",
    "file_type": "pdf",
    "source_path": "/path/to/doc.pdf",
    "ingested_at": "2024-01-15T10:30:00Z"
  }
}
```

## Search Pipeline

### Step 1: Query Processing

```python
# Input: Natural language query
# Output: Query embedding

1. Generate embedding for query
2. Use same model as ingestion
3. Apply same preprocessing
```

### Step 2: Vector Search

```python
# Input: Query embedding
# Output: Ranked results

Process:
1. MongoDB vector similarity search
2. Calculate cosine similarity
3. Filter by threshold (optional)
4. Sort by similarity score
5. Limit to top-k results
```

### Step 3: Result Formatting

```python
# Input: Raw results
# Output: User-friendly display

1. Extract content and metadata
2. Format similarity scores
3. Add source references
4. Apply output format (table/json)
```

## Component Interactions

### CLI ↔ Core API

```
User Command
    ↓
CLI Parser (Click)
    ↓
Command Handler
    ↓
Service Layer
    ↓
Storage/Embedding APIs
```

### Async Flow

```python
async def ingest_documents(path: Path):
    # 1. Load documents asynchronously
    documents = await load_documents_async(path)
    
    # 2. Chunk in parallel
    chunks = await chunk_documents_async(documents)
    
    # 3. Generate embeddings in parallel
    embeddings = await generate_embeddings_async(chunks)
    
    # 4. Store in parallel batches
    await store_async(embeddings)
```

## Error Handling Flow

```
Operation Start
    ↓
Try Block
    ↓
Circuit Breaker Check
    ↓
Execute Operation
    ↓
Success → Return Result
    ↓
Failure → Record Failure
    ↓
Circuit Breaker Update
    ↓
Retry or Fail
```

## Performance Bottlenecks

### Common Bottlenecks

1. **Embedding API** - Rate limited to protect service
2. **MongoDB Writes** - Batch size limits
3. **File I/O** - Sequential reading
4. **Memory** - Embedding cache size

### Optimization Strategies

```python
# Parallel processing
with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(process, documents))

# Batch operations
for batch in chunked(documents, batch_size=20):
    await store_batch(batch)

# Connection pooling
mongo_client = MongoClient(maxPoolSize=50, minPoolSize=10)
```

## Monitoring Points

### Key Metrics

- **Ingestion Rate**: Documents/minute
- **Embedding Latency**: ms per chunk
- **Search Latency**: ms per query
- **Cache Hit Rate**: % of cached embeddings
- **Circuit Breaker State**: Open/Closed/Half-Open

### Logging

```python
# Structured JSON logs
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "event": "document_ingested",
  "document_id": "uuid",
  "chunks": 12,
  "duration_ms": 2345
}
```

## Scalability

### Horizontal Scaling

- **Stateless CLI** - Can run on multiple machines
- **Shared MongoDB** - Central storage
- **Distributed Embeddings** - Multiple sentence-transformers instances

### Vertical Scaling

- **Increase workers** - More CPU cores
- **Larger batch size** - More throughput
- **Larger cache** - Fewer API calls
