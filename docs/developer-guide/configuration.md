# Configuration Reference

Detailed reference for all SecondBrain configuration options.

## Environment Variable Prefix

All SecondBrain configuration uses the `SECONDBRAIN_` prefix:

```bash
export SECONDBRAIN_<SETTING_NAME>=<value>
```

## Categories

Configuration options are organized by functional area:

- [Core](#core-settings)
- [MongoDB](#mongodb-settings)
- [Embedding](#embedding-settings)
- [LLM](#llm-settings)
- [RAG](#rag-settings)
- [Processing](#processing-settings)
- [Search](#search-settings)
- [Performance](#performance-settings)
- [Storage](#storage-optimization)

---

## Core Settings

### LOG_LEVEL

Logging verbosity level.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_LOG_LEVEL` |
| Default | `INFO` |
| Options | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

### LOG_FORMAT

Output format for log messages.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_LOG_FORMAT` |
| Default | `pretty` |
| Options | `pretty`, `json` |

---

## MongoDB Settings

### MONGO_URI

MongoDB connection URI.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_MONGO_URI` |
| Default | `mongodb://localhost:27017` |
| Validation | Must start with `mongodb://` or `mongodb+srv://` |

Examples:

```bash
# Local
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017

# With authentication
SECONDBRAIN_MONGO_URI=mongodb://user:password@localhost:27017

# Atlas cluster
SECONDBRAIN_MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net
```

### MONGO_DB

Database name.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_MONGO_DB` |
| Default | `secondbrain` |

### MONGO_COLLECTION

Collection name for embeddings.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_MONGO_COLLECTION` |
| Default | `embeddings` |

---

## Embedding Settings

### EMBEDDING_PROVIDER

Embedding service provider type.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_PROVIDER` |
| Default | `openai` |

Supports OpenAI or any OpenAI-compatible API (Ollama, LM Studio, vLLM).

### EMBEDDING_MODEL

Model identifier for embeddings.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_MODEL` |
| Default | `text-embedding-3-small` |

Common models:

- OpenAI: `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`
- Ollama/LM Studio: `mxbai-embed-large`, `all-MiniLM-L6-v2`

### EMBEDDING_DIMENSIONS

Vector dimensionality.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_DIMENSIONS` |
| Default | `1536` |
| Constraint | Must be positive integer |

Must match your embedding model's actual dimensions:

| Model | Dimensions |
|-------|------------|
| text-embedding-3-small | 1536 |
| text-embedding-3-large | 3072 |
| all-MiniLM-L6-v2 | 384 |
| mxbai-embed-large | 1024 |

### EMBEDDING_API_KEY

API key for embedding provider.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_API_KEY` |
| Default | `None` |

Set to API key for commercial providers. Self-hosted models may not require one.

### EMBEDDING_API_BASE

Custom endpoint base URL.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_API_BASE` |
| Default | `None` |

Used for self-hosted endpoints:

```bash
SECONDBRAIN_EMBEDDING_API_BASE=http://localhost:11434/v1
```

### EMBEDDING_CACHE_SIZE

LRU cache size for embeddings.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_CACHE_SIZE` |
| Default | `1000` |
| Range | 0 to unlimited |
| Memory | ~1.5MB per 1000 embeddings (384 dims × 4 bytes) |

Set to `0` to disable caching.

### EMBEDDING_BATCH_SIZE

Batch size for embedding generation.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_BATCH_SIZE` |
| Default | `20` |
| Range | 1-100 |

---

## LLM Settings

Used for RAG chat functionality.

### LLM_PROVIDER

LLM provider type.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_LLM_PROVIDER` |
| Default | `openai` |
| Options | `openai`, `anthropic` |

### LLM_MODEL

Model identifier for chat completions.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_LLM_MODEL` |
| Default | `gpt-4o-mini` |

### OPENAI_BASE_URL

OpenAI-compatible API base URL.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_OPENAI_BASE_URL` |
| Default | `None` |

For Ollama, LM Studio, Groq, Azure OpenAI, etc.

### LLM_TEMPERATURE

Generation temperature.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_LLM_TEMPERATURE` |
| Default | `0.1` |
| Range | 0.0-2.0 |

Lower values produce more deterministic outputs.

### LLM_MAX_TOKENS

Maximum tokens in response.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_LLM_MAX_TOKENS` |
| Default | `2048` |

### LLM_TIMEOUT

Request timeout in seconds.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_LLM_TIMEOUT` |
| Default | `120` |

---

## RAG Settings

### RAG_CONTEXT_WINDOW

Recent message count kept in conversation context.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RAG_CONTEXT_WINDOW` |
| Default | `5` |

### RAG_MAX_RETRIES

Maximum retry attempts for LLM generation.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RAG_MAX_RETRIES` |
| Default | `3` |

### RAG_MAX_CONTEXT_CHARS

Maximum total characters for RAG context.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RAG_MAX_CONTEXT_CHARS` |
| Default | `8000` |
| Range | 1000-500000 |

### RAG_CHUNK_PREVIEW_CHARS

Maximum characters per chunk in RAG context.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RAG_CHUNK_PREVIEW_CHARS` |
| Default | `500` |
| Range | 100-10000 |

Constraint: Must be less than `RAG_MAX_CONTEXT_CHARS`.

### RAG_SYSTEM_PROMPT

System prompt for RAG chat.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RAG_SYSTEM_PROMPT` |
| Default | (Built-in instruction set) |

---

## Processing Settings

### CHUNK_SIZE

Target chunk size in characters.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_CHUNK_SIZE` |
| Default | `4096` |
| Constraint | Must be positive integer |

### CHUNK_OVERLAP

Overlap between adjacent chunks.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_CHUNK_OVERLAP` |
| Default | `50` |
| Constraint | Must be non-negative and less than `CHUNK_SIZE` |

### SUPPORTED_EXTENSIONS

Comma-separated list of supported file extensions.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_SUPPORTED_EXTENSIONS` |
| Default | Comprehensive list of common formats |

Without leading dots, comma-separated.

### MAX_FILE_SIZE_BYTES

Maximum file size in bytes.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_MAX_FILE_SIZE_BYTES` |
| Default | `104857600` (100MB) |

---

## Search Settings

### DEFAULT_TOP_K

Default number of search results.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_DEFAULT_TOP_K` |
| Default | `20` |

### MIN_SIMILARITY_THRESHOLD

Global minimum similarity score (constant, not env var).

| Detail | Value |
|--------|-------|
| Constant | `DEFAULT_MIN_SIMILARITY_THRESHOLD` |
| Value | `0.46` |

Can be overridden per-query with `--min-score` flag.

---

## Performance Settings

### MAX_WORKERS

Worker process count for parallel processing.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_MAX_WORKERS` |
| Default | `None` (auto-detect CPU count) |

### STREAMING_ENABLED

Enable streaming chunk processing.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_STREAMING_ENABLED` |
| Default | `true` |

### STREAMING_CHUNK_BATCH_SIZE

Chunk batch size for streaming.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE` |
| Default | `100` |
| Range | 1-200 |

### RATE_LIMIT_ENABLED

Enable request rate limiting.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RATE_LIMIT_ENABLED` |
| Default | `true` |

### RATE_LIMIT_MAX_REQUESTS

Requests per rate limit window.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS` |
| Default | `10` |

### RATE_LIMIT_WINDOW_SECONDS

Rate limit window duration.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS` |
| Default | `1.0` |

### INDEX_READY_RETRY_COUNT

Retries for vector index initialization.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_INDEX_READY_RETRY_COUNT` |
| Default | `15` |

### CIRCUIT_BREAKER_ENABLED

Enable circuit breaker pattern.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_CIRCUIT_BREAKER_ENABLED` |
| Default | `true` |

---

## Storage Optimization

### STORAGE_COMPRESSION_ENABLED

Enable MongoDB collection compression.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_STORAGE_COMPRESSION_ENABLED` |
| Default | `true` |

Enables zstd compression, reducing storage by 40-60%.

### TEXT_COMPRESSION_ENABLED

Enable text content compression.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_TEXT_COMPRESSION_ENABLED` |
| Default | `false` |

Opt-in feature using gzip/brotli/zstd.

### TEXT_COMPRESSION_ALGORITHM

Compression algorithm.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_TEXT_COMPRESSION_ALGORITHM` |
| Default | `gzip` |
| Options | `gzip`, `brotli`, `zstd` |

### EMBEDDING_DTYPE

Embedding storage precision.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_DTYPE` |
| Default | `float32` |
| Options | `float32`, `float64` |

float32 recommended — 50% smaller storage with acceptable precision.

### EMBEDDING_STORAGE_FORMAT

Vector storage format.

| Detail | Value |
|--------|-------|
| Env Var | `SECONDBRAIN_EMBEDDING_STORAGE_FORMAT` |
| Default | `array` |
| Options | `array`, `binary` |

!!! Warning
    `binary` format is deprecated and incompatible with vector search. Use `array`.