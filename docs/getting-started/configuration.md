# Configuration Reference

Complete configuration guide for SecondBrain CLI. All settings are environment variables prefixed with `SECONDBRAIN_`.

## Quick Start

Create a `.env` file in your project root:

```bash
# Essential settings
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_CHUNK_SIZE=4096
```

See [Example .env File](#example-env-file) for complete template.

## Configuration Loading

SecondBrain uses Pydantic Settings to load configuration:

1. **Environment variables** (highest priority)
2. **`.env` file** in working directory
3. **Default values** (lowest priority)

Settings are case-insensitive and prefixed with `SECONDBRAIN_`.

---

## MongoDB Settings

### `SECONDBRAIN_MONGO_URI`
- **Type**: `str`
- **Default**: `mongodb://localhost:27017`
- **Required**: No (but MongoDB connection required for functionality)
- **Validation**: Must start with `mongodb://` or `mongodb+srv://`
- **Examples**:
  ```bash
  # Local MongoDB
  SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
  
  # MongoDB Atlas
  SECONDBRAIN_MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true
  
  # With authentication
  SECONDBRAIN_MONGO_URI=mongodb://user:pass@host:27017,host:27017/?authSource=admin
  ```

### `SECONDBRAIN_MONGO_DB`
- **Type**: `str`
- **Default**: `secondbrain`
- **Description**: Database name for storing embeddings
- **Example**: `SECONDBRAIN_MONGO_DB=my_vector_db`

### `SECONDBRAIN_MONGO_COLLECTION`
- **Type**: `str`
- **Default**: `embeddings`
- **Description**: Collection name within the database
- **Example**: `SECONDBRAIN_MONGO_COLLECTION=document_chunks`

---

## Embedding Settings

### `SECONDBRAIN_LOCAL_EMBEDDING_MODEL`
- **Type**: `str`
- **Default**: `all-MiniLM-L6-v2`
- **Description**: Sentence-transformers model for local embedding generation
- **Supported Models**:
  | Model | Dimensions | Speed | Quality | Use Case |
  |-------|-----------|-------|---------|----------|
  | `all-MiniLM-L6-v2` | 384 | Fast | Good | General purpose, recommended default |
  | `all-mpnet-base-v2` | 768 | Medium | Better | Higher quality, more resources |
  | `multi-qa-mpnet-base-dot-v1` | 768 | Medium | Better | Optimized for QA tasks |
  | `all-distilroberta-v1` | 768 | Fast | Good | Balanced speed/quality |
- **Note**: Must match `SECONDBRAIN_EMBEDDING_DIMENSIONS`

### `SECONDBRAIN_EMBEDDING_DIMENSIONS`
- **Type**: `int`
- **Default**: `384`
- **Validation**: Must be positive
- **Description**: Vector dimensionality (must match selected model)
- **Common Values**:
  - `384`: all-MiniLM-L6-v2
  - `768`: all-mpnet-base-v2, multi-qa-mpnet-base-dot-v1
  - `1024`: Large models (e.g., all-mpnet-large)
- **Example**: `SECONDBRAIN_EMBEDDING_DIMENSIONS=768`

### `SECONDBRAIN_EMBEDDING_CACHE_SIZE`
- **Type**: `int`
- **Default**: `1000`
- **Validation**: Must be non-negative
- **Description**: Maximum embeddings to cache in memory
- **Memory Impact**: ~1.5MB per 1000 embeddings (384 dims, float32)
- **Performance**: Reduces API calls for duplicate text
- **Disable**: Set to `0`
- **Example**: `SECONDBRAIN_EMBEDDING_CACHE_SIZE=5000`

### `SECONDBRAIN_EMBEDDING_BATCH_SIZE`
- **Type**: `int`
- **Default**: `20`
- **Validation**: 1-100
- **Description**: Batch size for embedding generation API calls
- **Trade-offs**:
  - Higher (50-100): Better throughput, more memory
  - Lower (10-20): Less memory, slower
- **Recommendation**: 20-50 for most systems
- **Example**: `SECONDBRAIN_EMBEDDING_BATCH_SIZE=50`

### `SECONDBRAIN_EMBEDDING_DTYPE`
- **Type**: `str`
- **Default**: `float32`
- **Valid Values**: `float32`, `float64`
- **Description**: Data type for embedding vectors
- **Trade-offs**:
  - `float32`: 50% smaller storage, sufficient precision
  - `float64`: MongoDB default, higher precision
- **Recommendation**: `float32` for most use cases
- **Example**: `SECONDBRAIN_EMBEDDING_DTYPE=float32`

### `SECONDBRAIN_EMBEDDING_STORAGE_FORMAT`
- **Type**: `str`
- **Default**: `array`
- **Valid Values**: `array`, `binary`
- **Description**: How embeddings are stored in MongoDB
- **Options**:
  - `array`: JSON array format (required for MongoDB vector search)
  - `binary`: BSON Binary format (compact, but breaks vector search)
- **Recommendation**: Always `array` for vector search functionality
- **Example**: `SECONDBRAIN_EMBEDDING_STORAGE_FORMAT=array`

---

## Document Chunking Settings

### `SECONDBRAIN_CHUNK_SIZE`
- **Type**: `int`
- **Default**: `4096`
- **Validation**: Must be positive
- **Description**: Maximum characters per text chunk
- **Trade-offs**:
  - Larger (4096-8192): Better context, fewer chunks
  - Smaller (512-2048): Finer granularity, more precise search
- **Recommendations**:
  - Books/long docs: 4096-8192
  - Articles/emails: 1024-2048
  - Code snippets: 512-1024
- **Example**: `SECONDBRAIN_CHUNK_SIZE=2048`

### `SECONDBRAIN_CHUNK_OVERLAP`
- **Type**: `int`
- **Default**: `50`
- **Validation**: Must be non-negative and less than chunk_size
- **Description**: Characters overlapping between consecutive chunks
- **Purpose**: Maintain context across chunk boundaries
- **Trade-offs**:
  - Higher overlap: Better context continuity, more storage
  - Lower overlap: Less storage, potential context loss
- **Recommendation**: 50-200 characters (10-20% of chunk_size)
- **Example**: `SECONDBRAIN_CHUNK_OVERLAP=100`

---

## File Processing Settings

### `SECONDBRAIN_SUPPORTED_EXTENSIONS`
- **Type**: `str`
- **Default**: `pdf,docx,pptx,xlsx,html,htm,md,txt,asciidoc,adoc,tex,csv,png,jpg,jpeg,tiff,tif,bmp,webp,wav,mp3,vtt,xml,json`
- **Description**: Comma-separated list of supported file extensions (without dots)
- **Categories**:
  - **Documents**: pdf, docx, pptx, xlsx, html, htm, md, txt, asciidoc, adoc, tex, csv
  - **Images**: png, jpg, jpeg, tiff, tif, bmp, webp (OCR extraction)
  - **Audio**: wav, mp3, vtt (transcription extraction)
  - **Data**: xml, json
- **Example**: `SECONDBRAIN_SUPPORTED_EXTENSIONS=pdf,md,txt`

### `SECONDBRAIN_MAX_FILE_SIZE_BYTES`
- **Type**: `int`
- **Default**: `104857600` (100MB)
- **Description**: Maximum file size allowed for ingestion
- **Purpose**: Prevent resource exhaustion from oversized files
- **Example**: `SECONDBRAIN_MAX_FILE_SIZE_BYTES=52428800` (50MB)

---

## Search Settings

### `SECONDBRAIN_DEFAULT_TOP_K`
- **Type**: `int`
- **Default**: `5`
- **Validation**: Must be positive
- **Description**: Default number of search results to return
- **Usage**: Override with `--top-k` CLI flag
- **Example**: `SECONDBRAIN_DEFAULT_TOP_K=10`

---

## Rate Limiting Settings

### `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS`
- **Type**: `int`
- **Default**: `10`
- **Description**: Maximum requests per rate limit window
- **Purpose**: Protect sentence-transformers API from overload
- **Throughput**: 10 req/s = 600 req/min
- **Example**: `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=20`

### `SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS`
- **Type**: `float`
- **Default**: `1.0`
- **Description**: Rate limit window in seconds
- **Behavior**: Sliding window rate limiting
- **Example**: `SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=2.0` (20 req per 2 seconds)

---

## Connection & Resilience Settings

### `SECONDBRAIN_CONNECTION_CACHE_TTL`
- **Type**: `float`
- **Default**: `60.0`
- **Description**: Time-to-live for connection validation cache (seconds)
- **Purpose**: Reduce connection check overhead
- **Trade-offs**:
  - Higher: Less validation overhead, slower failure detection
  - Lower: Faster failure detection, more validation calls
- **Example**: `SECONDBRAIN_CONNECTION_CACHE_TTL=30.0`

### `SECONDBRAIN_INDEX_READY_RETRY_COUNT`
- **Type**: `int`
- **Default**: `15`
- **Description**: Maximum retries waiting for MongoDB vector index
- **Exponential Backoff**: 100ms base, 2s max delay
- **Total Wait Time**: ~15 seconds with 15 retries
- **Purpose**: Handle MongoDB Atlas async index creation
- **Example**: `SECONDBRAIN_INDEX_READY_RETRY_COUNT=20`

### `SECONDBRAIN_INDEX_READY_RETRY_DELAY`
- **Type**: `float`
- **Default**: `1.0`
- **Description**: Initial delay for index ready retries (reserved for future use)
- **Note**: Current implementation uses fixed 100ms base delay

---

## Parallel Processing Settings

### `SECONDBRAIN_MAX_WORKERS`
- **Type**: `int | None`
- **Default**: `None` (auto-detect CPU count)
- **Validation**: Must be positive when set
- **Description**: Maximum worker processes for parallel document processing
- **Usage**:
  - `None`: Auto-detect (recommended)
  - `4`: Use 4 processes
  - CLI override: `--cores N` flag
- **Example**: `SECONDBRAIN_MAX_WORKERS=8`

---

## Streaming & Memory Settings

### `SECONDBRAIN_STREAMING_ENABLED`
- **Type**: `bool`
- **Default**: `true`
- **Description**: Enable streaming processing for memory efficiency
- **Behavior**:
  - `true`: Process documents in batches, release memory
  - `false`: Load all documents into memory first
- **Recommendation**: Always `true` for large document sets
- **Example**: `SECONDBRAIN_STREAMING_ENABLED=true`

### `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE`
- **Type**: `int`
- **Default**: `100`
- **Validation**: 1-200
- **Description**: Number of chunks per streaming batch for embedding generation
- **Performance Impact**:
  - Larger batches: Better embedding throughput (utilize batch API)
  - Smaller batches: Lower memory usage
- **Recommendation**: 100 for most systems
- **Example**: `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE=150`

---

## Storage Optimization Settings

### `SECONDBRAIN_STORAGE_COMPRESSION_ENABLED`
- **Type**: `bool`
- **Default**: `true`
- **Description**: Enable MongoDB collection-level compression (zstd)
- **Storage Savings**: 40-60% reduction
- **Overhead**: Minimal CPU impact
- **Recommendation**: Always `true`
- **Example**: `SECONDBRAIN_STORAGE_COMPRESSION_ENABLED=true`

### `SECONDBRAIN_TEXT_COMPRESSION_ENABLED`
- **Type**: `bool`
- **Default**: `false`
- **Description**: Enable text compression for chunk_text field
- **Storage Savings**: 60-80% reduction for text content
- **Overhead**: Compression/decompression CPU cost
- **Use Case**: Large text volumes, storage-constrained environments
- **Example**: `SECONDBRAIN_TEXT_COMPRESSION_ENABLED=true`

### `SECONDBRAIN_TEXT_COMPRESSION_ALGORITHM`
- **Type**: `str`
- **Default**: `gzip`
- **Valid Values**: `gzip`, `brotli`, `zstd`
- **Trade-offs**:
  - `gzip`: Fastest compression/decompression
  - `brotli`: Best compression ratio, slower
  - `zstd`: Balanced speed/ratio
- **Example**: `SECONDBRAIN_TEXT_COMPRESSION_ALGORITHM=brotli`

---

## Logging Settings

### `SECONDBRAIN_LOG_LEVEL`
- **Type**: `str`
- **Default**: `INFO`
- **Valid Values**: `DEBUG`, `INFO`, `SUCCESS`, `WARNING`, `ERROR`, `CRITICAL`
- **Description**: Logging verbosity level
- **Usage**:
  ```bash
  SECONDBRAIN_LOG_LEVEL=DEBUG  # Verbose debugging
  SECONDBRAIN_LOG_LEVEL=INFO   # Standard (default)
  SECONDBRAIN_LOG_LEVEL=ERROR  # Errors only
  ```

### `SECONDBRAIN_LOG_FORMAT`
- **Type**: `str`
- **Default**: `rich`
- **Valid Values**: `rich`, `json`
- **Description**: Log output format
- **Options**:
  - `rich`: Pretty-printed terminal output (default)
  - `json`: Structured JSON for log aggregation systems
- **Example**: `SECONDBRAIN_LOG_FORMAT=json`

### `SECONDBRAIN_LOG_FILE`
- **Type**: `str | None`
- **Default**: `None` (stdout/stderr)
- **Description**: Path to log file
- **Behavior**: Enables rotating file handler when set
- **Example**: `SECONDBRAIN_LOG_FILE=/var/log/secondbrain/app.log`

---

## OpenTelemetry Settings

### `SECONDBRAIN_TRACING_ENABLED`
- **Type**: `bool`
- **Default**: `false`
- **Description**: Enable distributed tracing with OpenTelemetry
- **Purpose**: Monitor performance and trace requests across services
- **Example**: `SECONDBRAIN_TRACING_ENABLED=true`

### `SECONDBRAIN_TRACING_EXPORTER`
- **Type**: `str`
- **Default**: `console`
- **Valid Values**: `console`, `otlp`
- **Description**: Tracing exporter type
- **Options**:
  - `console`: Print spans to stdout (development)
  - `otlp`: Export via OTLP protocol (production)
- **Example**: `SECONDBRAIN_TRACING_EXPORTER=otlp`

### `SECONDBRAIN_TRACING_OTLP_ENDPOINT`
- **Type**: `str | None`
- **Default**: `None`
- **Description**: OTLP collector endpoint
- **Example**: `SECONDBRAIN_TRACING_OTLP_ENDPOINT=http://localhost:4317`

---

## Circuit Breaker Settings (Coming Soon)

### `SECONDBRAIN_CIRCUIT_BREAKER_ENABLED`
- **Type**: `bool`
- **Default**: `false`
- **Description**: Enable circuit breaker pattern for service resilience
- **Status**: Planned feature

### `SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD`
- **Type**: `int`
- **Default**: `5`
- **Description**: Failures before opening circuit
- **Status**: Planned feature

### `SECONDBRAIN_CIRCUIT_BREAKER_TIMEOUT`
- **Type**: `float`
- **Default**: `30.0`
- **Description**: Seconds before attempting recovery
- **Status**: Planned feature

---

## Example .env Files

### Minimal Configuration
```bash
# MongoDB
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=embeddings

# Embeddings
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_EMBEDDING_DIMENSIONS=384

# Chunking
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50
```

### Production Configuration
```bash
# MongoDB Atlas
SECONDBRAIN_MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true
SECONDBRAIN_MONGO_DB=production_db
SECONDBRAIN_MONGO_COLLECTION=document_embeddings

# Higher quality embeddings
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-mpnet-base-v2
SECONDBRAIN_EMBEDDING_DIMENSIONS=768
SECONDBRAIN_EMBEDDING_CACHE_SIZE=5000

# Optimized chunking
SECONDBRAIN_CHUNK_SIZE=2048
SECONDBRAIN_CHUNK_OVERLAP=100

# Rate limiting
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=20
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0

# Logging
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=json
SECONDBRAIN_LOG_FILE=/var/log/secondbrain/app.log

# Storage optimization
SECONDBRAIN_STORAGE_COMPRESSION_ENABLED=true
SECONDBRAIN_TEXT_COMPRESSION_ENABLED=true
SECONDBRAIN_TEXT_COMPRESSION_ALGORITHM=gzip
```

### Development Configuration
```bash
# Local MongoDB
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain_dev
SECONDBRAIN_MONGO_COLLECTION=test_embeddings

# Fast model for testing
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_EMBEDDING_DIMENSIONS=384
SECONDBRAIN_EMBEDDING_CACHE_SIZE=0  # Disable cache for testing

# Verbose logging
SECONDBRAIN_LOG_LEVEL=DEBUG
SECONDBRAIN_LOG_FORMAT=rich

# Smaller chunks for faster processing
SECONDBRAIN_CHUNK_SIZE=1024
SECONDBRAIN_CHUNK_OVERLAP=50

# Faster rate limits for testing
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=100
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=0.1
```

---

## Validation Rules

All configuration values are validated on startup. Common validation errors:

```
ValueError: chunk_overlap must be less than chunk_size
ValueError: embedding_batch_size must be between 1 and 100
ValueError: mongo_uri must start with 'mongodb://' or 'mongodb+srv://'
ValueError: embedding_dtype must be 'float32' or 'float64'
```

---

## Troubleshooting

### Configuration Not Loading
1. Verify `.env` file is in project root
2. Check environment variable names (case-insensitive, must have `SECONDBRAIN_` prefix)
3. Check for syntax errors in `.env` file

### MongoDB Connection Issues
1. Verify `SECONDBRAIN_MONGO_URI` format
2. Test connection: `mongosh "mongodb://localhost:27017"`
3. Check network/firewall settings

### Embedding Generation Slow
1. Reduce `SECONDBRAIN_EMBEDDING_BATCH_SIZE`
2. Switch to faster model (e.g., `all-MiniLM-L6-v2`)
3. Enable `SECONDBRAIN_EMBEDDING_CACHE_SIZE`

### High Memory Usage
1. Enable streaming: `SECONDBRAIN_STREAMING_ENABLED=true`
2. Reduce `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE`
3. Reduce `SECONDBRAIN_EMBEDDING_CACHE_SIZE`

---

## Related Documentation

- [Quick Start](quick-start.md) - Get started in 5 minutes
- [User Guide](../user-guide/index.md) - Complete usage guide
- [Architecture](../architecture/index.md) - System design
- [Async API](../developer-guide/async-api.md) - Asynchronous programming
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
