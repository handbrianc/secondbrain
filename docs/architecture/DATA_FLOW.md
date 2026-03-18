# Data Flow Architecture

Documentation of data flow and component interactions in SecondBrain.

## Overview

SecondBrain processes documents through a pipeline of components that transform raw files into searchable semantic embeddings.

## High-Level Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   User CLI   │────▶│   Document Ingest│────▶│   Embedding Gen  │────▶│   MongoDB Store  │
│  (secondbrain)│     │    (docling)     │     │  (sentence-transformers API)    │     │(vector search)   │
└──────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘
          │                                                                   │
          │                                                                   ▼
          │                                                          ┌──────────────────┐
          │                                                          │   User Query     │
          │                                                          │   (semantic)     │
          │                                                                   │
          │                                                                   ▼
          │                                                          ┌──────────────────┐
          │                                                          │   Searcher       │
          │                                                          │   (cosine sim)   │
          └───────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. CLI Layer

**Purpose**: User interface for all operations

**Components**:
- `secondbrain.cli` - Click-based command interface
- Error handling and user feedback
- Output formatting (text, JSON, rich tables)

**Responsibilities**:
- Parse user input and arguments
- Validate inputs before processing
- Format and display results
- Handle errors gracefully

**Entry Points**:
```python
# CLI commands
secondbrain ingest <path>       # Document ingestion
secondbrain search <query>      # Semantic search
secondbrain list                # List documents
secondbrain delete              # Delete documents
secondbrain status              # Database statistics
secondbrain health              # Service health check
```

### 2. Document Ingestion

**Purpose**: Extract and chunk text from various file formats

**Components**:
- `secondbrain.document.DocumentIngestor` - Main ingestion logic
- `docling.document_converter` - Multi-format document parsing
- Text chunking with configurable size and overlap

**Supported Formats**:
- **Documents**: PDF, DOCX, PPTX, XLSX
- **Web**: HTML, Markdown, AsciiDoc, LaTeX
- **Data**: CSV, JSON, XML
- **Media**: Images (PNG, JPG, TIFF), Audio (WAV, MP3)

**Processing Pipeline**:

```
File Input
    │
    ▼
┌─────────────────┐
│  File Validation│  - Check file type
│                 │  - Verify file size
│                 │  - Security checks
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Text Extraction│  - Use docling converter
│                 │  - Handle multiple formats
│                 │  - Extract metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Text Chunking │  - Split by chunk_size
│                 │  - Add chunk_overlap
│                 │  - Preserve page info
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Duplicate Check│  - Hash text content
│                 │  - Skip duplicates
│                 │  - Track seen chunks
└────────┬────────┘
         │
         ▼
    Embedding Generation
```

**Chunking Strategy**:

```python
# Configuration
chunk_size = 4096      # Tokens per chunk
chunk_overlap = 50     # Overlap between chunks

# Algorithm
text = "..."  # Full document text
start = 0
while start < len(text):
    end = start + chunk_size
    # Find last space before end
    chunk_end = text.rfind(" ", start, end)
    chunk = text[start:chunk_end]
    chunks.append(chunk)
    start = chunk_end - chunk_overlap  # Overlap for context
```

### 3. Embedding Generation

**Purpose**: Convert text chunks to semantic vector embeddings

**Components**:
- `secondbrain.embedding.EmbeddingGenerator` - sentence-transformers API client
- Rate limiting for API protection
- Connection validation and caching
- Async/sync dual API

**sentence-transformers Integration**:

```
Text Chunk
    │
    ▼
┌─────────────────┐
│ Rate Limiter    │  - Sliding window
│                 │  - Max requests/sec
│                 │  - Prevent overload
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Connection Check│  - TTL-cached validation
│                 │  - sentence-transformers availability
│                 │  - Model verification
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ API Request     │  POST /api/embeddings
│                 │  { "model": "embeddinggemma",
│                 │    "prompt": "text chunk" }
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Response Parse  │  Extract embedding vector
│                 │  768-dimensional float array
└────────┬────────┘
         │
         ▼
    Vector Storage
```

**Rate Limiting**:

```python
# Configuration
rate_limit_max_requests = 10
rate_limit_window_seconds = 1.0

# Sliding window algorithm
class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=1.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = []  # Timestamps
    
    def acquire(self):
        now = time.time()
        # Remove old requests
        self.requests = [t for t in self.requests 
                        if now - t < self.window_seconds]
        
        # Wait if at limit
        while len(self.requests) >= self.max_requests:
            sleep_time = self.window_seconds - (now - min(self.requests))
            time.sleep(max(0, sleep_time))
            now = time.time()
            self.requests = [t for t in self.requests 
                            if now - t < self.window_seconds]
        
        self.requests.append(now)
```

### 4. Vector Storage

**Purpose**: Store and retrieve embeddings with MongoDB

**Components**:
- `secondbrain.storage.VectorStorage` - MongoDB operations
- Connection pooling for performance
- Vector search index management
- Async/sync dual API

**Document Structure**:

```json
{
  "_id": "ObjectId",
  "chunk_id": "uuid-v4",
  "source_file": "/path/to/document.pdf",
  "page_number": 1,
  "chunk_text": "Extracted text content...",
  "embedding": [0.123, -0.456, 0.789, ...],  // 768 dimensions
  "metadata": {
    "file_type": "pdf",
    "ingested_at": "2026-03-06T12:00:00Z",
    "chunk_index": 0
  },
  "version": 1
}
```

**Vector Search Index**:

```json
{
  "name": "embedding_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [{
      "type": "vector",
      "path": "embedding",
      "numDimensions": 768,
      "similarity": "cosine"
    }]
  }
}
```

**Storage Pipeline**:

```
Embedding + Metadata
    │
    ▼
┌─────────────────┐
│  Connection     │  - Validate MongoDB
│  Validation     │  - Check cache TTL
│                 │  - Reconnect if needed
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Index Check    │  - Create if missing
│                 │  - Wait for READY status
│                 │  - Timeout after retries
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Insert         │  - Single or batch
│                 │  - Add timestamp
│                 │  - Handle duplicates
└─────────────────┘
```

### 5. Semantic Search

**Purpose**: Find similar documents using vector similarity

**Components**:
- `secondbrain.search.Searcher` - Search orchestration
- Query sanitization for security
- Cosine similarity calculation
- Result filtering and ranking

**Search Pipeline**:

```
User Query
    │
    ▼
┌─────────────────┐
│ Query Sanitization│ - Check length
│                 │  - Block injection
│                 │  - Strip control chars
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Embed Query     │  - Generate embedding
│                 │  - Same model as ingestion
│                 │  - Rate limited
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Vector Search   │  MongoDB $vectorSearch
│                 │  {
│                 │    "queryVector": [0.123, ...],
│                 │    "path": "embedding",
│                 │    "numCandidates": 100,
│                 │    "limit": 10,
│                 │    "index": "embedding_index"
│                 │  }
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Apply Filters   │  - Source file filter
│                 │  - File type filter
│                 │  - Regex matching
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Score Results   │  - Cosine similarity
│                 │  - Normalize scores
│                 │  - Sort by relevance
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Format Output   │  - Add metadata
│                 │  - Preview text
│                 │  - Rich/JSON format
└─────────────────┘
```

**Cosine Similarity**:

```python
def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a ** 2 for a in vec1) ** 0.5
    magnitude2 = sum(b ** 2 for b in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0
    
    return dot_product / (magnitude1 * magnitude2)
```

**MongoDB Aggregation Pipeline**:

```javascript
[
  // 1. Vector search
  {
    "$vectorSearch": {
      "queryVector": [0.123, ...],
      "path": "embedding",
      "numCandidates": 100,
      "limit": 10,
      "index": "embedding_index"
    }
  },
  
  // 2. Apply filters
  {
    "$match": {
      "source_file": { "$regex": "document" },
      "metadata.file_type": "pdf"
    }
  },
  
  // 3. Project results
  {
    "$project": {
      "chunk_id": 1,
      "source_file": 1,
      "page_number": 1,
      "chunk_text": 1,
      "score": { "$meta": "vectorSearchScore" }
    }
  }
]
```

## Data Flow Examples

### Document Ingestion Flow

```
User: secondbrain ingest report.pdf
    │
    ├─▶ CLI: Parse arguments
    │   - path: "report.pdf"
    │   - recursive: false
    │   - batch_size: 10
    │
    ├─▶ DocumentIngestor: Ingest
    │   ├─▶ Validate file
    │   │   - Exists? ✓
    │   │   - Supported type? ✓ (PDF)
    │   │   - Size < 100MB? ✓
    │   │
    │   ├─▶ Extract text (docling)
    │   │   └─▶ [Segment(text="Page 1...", page=1), ...]
    │   │
    │   ├─▶ Chunk text
    │   │   └─▶ [Chunk(text="First chunk...", page=1), ...]
    │   │
    │   ├─▶ Deduplicate
    │   │   └─▶ Hash check, skip duplicates
    │   │
    │   └─▶ For each chunk:
    │       ├─▶ EmbeddingGenerator.generate(chunk.text)
    │       │   ├─▶ Rate limiter.acquire()
    │       │   ├─▶ sentence-transformers API: POST /api/embeddings
    │       │   └─▶ Return [0.123, ...] (768 dims)
    │       │
    │       └─▶ VectorStorage.store(chunk + embedding)
    │           ├─▶ Connection validation
    │           ├─▶ Index creation (if needed)
    │           └─▶ MongoDB insert
    │
    └─▶ CLI: Display results
        └─▶ "Successfully ingested 1 files"
```

### Semantic Search Flow

```
User: secondbrain search "machine learning"
    │
    ├─▶ CLI: Parse arguments
    │   - query: "machine learning"
    │   - top_k: 5
    │   - format: "default"
    │
    ├─▶ Searcher: Search
    │   ├─▶ Query sanitization
    │   │   - Length check ✓
    │   │   - Pattern check ✓
    │   │   - Strip control chars ✓
    │   │
    │   ├─▶ Connection validation
    │   │   ├─▶ sentence-transformers: validate_connection()
    │   │   └─▶ MongoDB: validate_connection()
    │   │
    │   ├─▶ Generate query embedding
    │   │   └─▶ EmbeddingGenerator.generate("machine learning")
    │   │       └─▶ [0.456, -0.789, ...] (768 dims)
    │   │
    │   └─▶ VectorStorage.search(embedding, top_k=5)
    │       ├─▶ Build aggregation pipeline
    │       ├─▶ Execute $vectorSearch
    │       └─▶ Return results with scores
    │
    └─▶ CLI: Display results
        └─▶ Rich table with 5 results
            - Source file
            - Page number
            - Similarity score
            - Text preview
```

## Performance Considerations

### Bottlenecks

1. **Embedding Generation** (slowest)
   - sentence-transformers API latency: ~100-500ms per chunk
   - Rate limited to 10 req/sec
   - **Mitigation**: Batch processing, async operations

2. **File I/O**
   - Large file reading
   - **Mitigation**: Streaming, chunked processing

3. **MongoDB Index Creation**
   - First-time index build: 5-30 seconds
   - **Mitigation**: Pre-create index, wait logic

### Optimization Strategies

1. **Batch Processing**
   ```python
   # Process 10 files concurrently
   ingestor.ingest(path, batch_size=10)
   ```

2. **Connection Caching**
   ```python
   # Validation cached for 60 seconds
   config.connection_cache_ttl = 60.0
   ```

3. **Async Operations**
   ```python
   # Non-blocking embedding generation
   embedding = await generator.generate_async(text)
   ```

4. **Duplicate Detection**
   ```python
   # Skip already-processed chunks
   text_hash = hash(normalized_text)
   if text_hash in seen_hashes:
       continue
   ```

## Error Handling

### Failure Points

| Component | Failure Mode | Recovery |
|-----------|-------------|----------|
| File Validation | Unsupported type, too large | Skip file, log error |
| Text Extraction | Corrupt file, format error | Retry, fallback to raw text |
| Embedding Gen | sentence-transformers down, timeout | Retry with backoff, queue for later |
| Storage | MongoDB down, index missing | Reconnect, create index, retry |
| Search | Invalid query, no results | Sanitize query, return empty |

### Error Propagation

```
Low-level error
    │
    ▼
┌─────────────────┐
│ Exception       │  Specific exception type
│ Hierarchy       │  - StorageConnectionError
│                 │  - EmbeddingGenerationError
│                 │  - DocumentExtractionError
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Error Handler   │  - Log full traceback
│ (Decorator)     │  - User-friendly message
│                 │  - Exit with code 1
└────────┬────────┘
         │
         ▼
    User Feedback
```

## Security Considerations

### Input Validation

1. **File Path Sanitization**
   - Block path traversal (`../`)
   - Resolve to absolute path
   - Verify within allowed directories

2. **Query Sanitization**
   - Block XSS patterns (`<script>`)
   - Block path traversal
   - Limit query length (10,000 chars)
   - Strip control characters

3. **File Size Limits**
   - Maximum 100MB per file
   - Prevents DoS via large files

### Data Protection

- No secrets in code (use environment variables)
- No PII logging
- Connection strings validated for format
- Rate limiting prevents API abuse

## Next Steps

- [Schema Reference](./SCHEMA.md) - Database schema details
- [Configuration](../developer-guide/configuration.md) - Tuning parameters
- [Development Guide](../developer-guide/development.md) - Implementation details
