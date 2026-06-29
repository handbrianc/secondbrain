# Configuration Guide

SecondBrain uses environment variables prefixed with `SECONDBRAIN_` for all configuration. This follows 12-factor app principles for consistent, production-ready settings management.

## Quick Configuration

Create a `.env` file in your project root:

```bash
# Required: MongoDB connection
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=embeddings

# Embedding provider
SECONDBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECONDBRAIN_EMBEDDING_API_KEY=your-api-key

# Document processing
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50
SECONDBRAIN_DEFAULT_TOP_K=20
```

## Configuration Loading Order

SecondBrain loads configuration in the following priority order (highest to lowest):

1. Environment variables
2. `.env` file values
3. Hardcoded defaults

During testing (`PYTEST_CURRENT_TEST` is set), configuration additionally loads from `.env.test` with test-specific defaults.

## Core Settings

### MongoDB Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection URI |
| `SECONDBRAIN_MONGO_DB` | `secondbrain` | Database name |
| `SECONDBRAIN_MONGO_COLLECTION` | `embeddings` | Collection for vector storage |

### Embedding Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_EMBEDDING_PROVIDER` | `openai` | Provider type (openai or compatible) |
| `SECONDBRAIN_EMBEDDING_MODEL` | `text-embedding-3-small` | Model name |
| `SECONDBRAIN_EMBEDDING_DIMENSIONS` | `1536` | Vector dimensionality |
| `SECONDBRAIN_EMBEDDING_API_KEY` | `None` | API key for provider |
| `SECONDBRAIN_EMBEDDING_API_BASE` | `None` | Custom endpoint base URL |
| `SECONDBRAIN_EMBEDDING_CACHE_SIZE` | `1000` | LRU cache size (0 disables) |
| `SECONDBRAIN_EMBEDDING_BATCH_SIZE` | `20` | Batch size (1-100) |

### LLM Configuration (for RAG chat)

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_LLM_PROVIDER` | `openai` | Provider type (openai, anthropic) |
| `SECONDBRAIN_LLM_MODEL` | `gpt-4o-mini` | Model name |
| `SECONDBRAIN_LLM_TEMPERATURE` | `0.1` | Generation temperature (0.0-2.0) |
| `SECONDBRAIN_LLM_MAX_TOKENS` | `2048` | Maximum response tokens |
| `SECONDBRAIN_LLM_TIMEOUT` | `120` | Request timeout in seconds |
| `SECONDBRAIN_OPENAI_BASE_URL` | `None` | OpenAI-compatible API base URL |

### Document Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_CHUNK_SIZE` | `4096` | Target chunk size in characters |
| `SECONDBRAIN_CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `SECONDBRAIN_SUPPORTED_EXTENSIONS` | (comprehensive list) | Comma-separated file extensions |
| `SECONDBRAIN_MAX_FILE_SIZE_BYTES` | `104857600` | Maximum file size (100MB) |

### Search Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_DEFAULT_TOP_K` | `20` | Default number of search results |
| `MIN_SCORE` | `0.46` | Minimum similarity threshold (constant) |

## Advanced Settings

### RAG/Pipeline Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_RAG_CONTEXT_WINDOW` | `5` | Recent messages in conversation context |
| `SECONDBRAIN_RAG_MAX_RETRIES` | `3` | Maximum LLM retry attempts |
| `SECONDBRAIN_RAG_MAX_CONTEXT_CHARS` | `8000` | Maximum context characters |
| `SECONDBRAIN_RAG_CHUNK_PREVIEW_CHARS` | `500` | Per-chunk preview length |
| `SECONDBRAIN_STREAMING_ENABLED` | `true` | Enable streaming processing |
| `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE` | `100` | Streaming batch size (1-200) |

### Performance Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_MAX_WORKERS` | `None` | Worker processes (auto-detect if unset) |
| `SECONDBRAIN_RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS` | `10` | Requests per window |
| `SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS` | `1.0` | Rate limit window duration |
| `SECONDBRAIN_INDEX_READY_RETRY_COUNT` | `15` | Index check retries |

### Storage Optimization

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_STORAGE_COMPRESSION_ENABLED` | `true` | Enable zstd compression |
| `SECONDBRAIN_TEXT_COMPRESSION_ENABLED` | `false` | Enable text compression |
| `SECONDBRAIN_TEXT_COMPRESSION_ALGORITHM` | `gzip` | Algorithm: gzip, brotli, zstd |
| `SECONDBRAIN_EMBEDDING_DTYPE` | `float32` | Storage precision |
| `SECONDBRAIN_EMBEDDING_STORAGE_FORMAT` | `array` | Storage format (array recommended) |

## Configuration Validation

On startup, SecondBrain validates configuration values. Invalid configurations raise errors:

```python
# chunk_overlap must be less than chunk_size
# embedding_dimensions must be positive
# embedding_batch_size must be between 1 and 100
```

## Example Production Configuration

```bash
# Production .env.example
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain_prod
SECONDBRAIN_MONGO_COLLECTION=embeddings_v2

SECONDBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECONDBRAIN_EMBEDDING_API_KEY=$OPENAI_API_KEY
SECONDBRAIN_EMBEDDING_DIMENSIONS=1536
SECONDBRAIN_EMBEDDING_BATCH_SIZE=20

SECONDBRAIN_LLM_MODEL=gpt-4o-mini
SECONDBRAIN_LLM_PROVIDER=openai
SECONDBRAIN_LLM_MAX_TOKENS=2048
SECONDBRAIN_LLM_TIMEOUT=120

SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50
SECONDBRAIN_DEFAULT_TOP_K=20

SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true

SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=json
```