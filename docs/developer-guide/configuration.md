# Configuration Reference

Complete configuration reference for SecondBrain developers.

## Configuration Loading Order

1. **Environment variables** (highest priority)
2. **`.env` file** in working directory
3. **Default values** (lowest priority)

## Environment Variables

### Core Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SECONDBRAIN_MONGO_URI` | str | `mongodb://localhost:27017` | MongoDB connection string |
| `SECONDBRAIN_MONGO_DB` | str | `secondbrain` | Database name |
| `SECONDBRAIN_MONGO_COLLECTION` | str | `embeddings` | Collection name |

### Embedding Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SECONDBRAIN_SENTENCE_TRANSFORMERS_URL` | str | `http://localhost:11434` | sentence-transformers API URL |
| `SECONDBRAIN_MODEL` | str | `all-MiniLM-L6-v2` | Embedding model name |
| `SECONDBRAIN_EMBEDDING_DIMENSIONS` | int | `384` | Vector dimensions |
| `SECONDBRAIN_EMBEDDING_CACHE_SIZE` | int | `1000` | Cache size |

### Processing Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SECONDBRAIN_CHUNK_SIZE` | int | `4096` | Chunk size in characters |
| `SECONDBRAIN_CHUNK_OVERLAP` | int | `200` | Chunk overlap |
| `SECONDBRAIN_MAX_WORKERS` | int | `4` | Parallel workers |
| `SECONDBRAIN_BATCH_SIZE` | int | `10` | Batch size for embedding |

### Rate Limiting

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SECONDBRAIN_RATE_LIMIT_ENABLED` | bool | `true` | Enable rate limiting |
| `SECONDBRAIN_RATE_LIMIT_REQUESTS_PER_SECOND` | float | `10.0` | Max requests/sec |

### Circuit Breaker

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SECONDBRAIN_CIRCUIT_BREAKER_ENABLED` | bool | `true` | Enable circuit breaker |
| `SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | int | `5` | Failure threshold |
| `SECONDBRAIN_CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | float | `60.0` | Recovery timeout (s) |

### Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SECONDBRAIN_LOG_LEVEL` | str | `INFO` | Log level |
| `SECONDBRAIN_LOG_FORMAT` | str | `pretty` | Log format (pretty/json) |
| `SECONDBRAIN_VERBOSE` | bool | `false` | Verbose output |

## Configuration Validation

All configuration is validated using Pydantic:

```python
from secondbrain.config import SecondBrainConfig

config = SecondBrainConfig()
config.validate()  # Raises ValidationError if invalid
```

## Example .env File

```bash
# Core
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=embeddings

# Embedding
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:11434
SECONDBRAIN_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_EMBEDDING_DIMENSIONS=384

# Processing
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=200
SECONDBRAIN_MAX_WORKERS=4

# Logging
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=pretty
```

## Next Steps

- [Getting Started](../getting-started/configuration.md) - User configuration
- [Development Setup](development.md) - Development workflow
