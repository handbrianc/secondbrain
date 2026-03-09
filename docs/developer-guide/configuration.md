# Configuration Reference

Complete configuration guide for SecondBrain using environment variables and Pydantic Settings.

## Overview

SecondBrain uses a 12-factor app approach with environment-based configuration. All settings are validated using Pydantic Settings and can be configured via:

1. Environment variables
2. `.env` file in the project root
3. Command-line arguments (where applicable)

## Environment Variables

All configuration options use the `SECONDBRAIN_` prefix.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection URI |
| `SECONDBRAIN_MONGO_DB` | `secondbrain` | Database name |
| `SECONDBRAIN_MONGO_COLLECTION` | `embeddings` | Collection name for embeddings |
| `SECONDBRAIN_OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `SECONDBRAIN_MODEL` | `embeddinggemma:latest` | Embedding model to use |

### Document Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_CHUNK_SIZE` | `4096` | Chunk size for document splitting (tokens) |
| `SECONDBRAIN_CHUNK_OVERLAP` | `50` | Chunk overlap for splitting (tokens) |
| `SECONDBRAIN_MAX_FILE_SIZE_BYTES` | `104857600` | Maximum file size (100MB) |

### Search Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_DEFAULT_TOP_K` | `5` | Default number of search results |
| `SECONDBRAIN_EMBEDDING_DIMENSIONS` | `768` | Dimensionality of embedding vectors |

### Performance Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS` | `10` | Max requests per rate limit window |
| `SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS` | `1.0` | Rate limit window in seconds |
| `SECONDBRAIN_CONNECTION_CACHE_TTL` | `60.0` | Connection validation cache TTL (seconds) |
| `SECONDBRAIN_INDEX_READY_RETRY_COUNT` | `15` | Max retries for index ready check |
| `SECONDBRAIN_INDEX_READY_RETRY_DELAY` | `1.0` | Delay between index retries (seconds) |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_LOG_FORMAT` | `rich` | Log format: `rich` or `json` |
| `SECONDBRAIN_HEALTH_CHECK_TTL` | `60` | Service check cache TTL (seconds) |

## Using .env File

Create a `.env` file in the project root:

```bash
# Core Settings
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=embeddings
SECONDBRAIN_OLLAMA_URL=http://localhost:11434
SECONDBRAIN_MODEL=embeddinggemma:latest

# Document Processing
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50
SECONDBRAIN_MAX_FILE_SIZE_BYTES=104857600

# Search Settings
SECONDBRAIN_DEFAULT_TOP_K=5
SECONDBRAIN_EMBEDDING_DIMENSIONS=768

# Performance
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=10
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0
SECONDBRAIN_CONNECTION_CACHE_TTL=60.0

# Logging
SECONDBRAIN_LOG_FORMAT=rich
SECONDBRAIN_HEALTH_CHECK_TTL=60
```

## Configuration Validation

SecondBrain validates all configuration at startup. Common validation errors:

### MongoDB URI Validation

Must start with `mongodb://` or `mongodb+srv://`:

```bash
# Invalid
SECONDBRAIN_MONGO_URI=postgres://localhost:27017  # Error!

# Valid
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net
```

### Ollama URL Validation

Must have valid HTTP/HTTPS scheme and host:

```bash
# Invalid
SECONDBRAIN_OLLAMA_URL=localhost:11434  # Missing scheme!

# Valid
SECONDBRAIN_OLLAMA_URL=http://localhost:11434
SECONDBRAIN_OLLAMA_URL=https://ollama.example.com
```

### Chunk Size Validation

Chunk size must be positive and greater than chunk overlap:

```bash
# Invalid
SECONDBRAIN_CHUNK_SIZE=0  # Must be positive!
SECONDBRAIN_CHUNK_SIZE=100
SECONDBRAIN_CHUNK_OVERLAP=200  # Must be < chunk_size!

# Valid
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50
```

## Environment-Specific Configuration

### Development

```bash
# .env.development
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_LOG_FORMAT=rich
SECONDBRAIN_CONNECTION_CACHE_TTL=30.0  # Shorter cache for dev
```

### Production

```bash
# .env.production
SECONDBRAIN_MONGO_URI=mongodb://user:pass@prod-cluster.mongodb.net:27017
SECONDBRAIN_OLLAMA_URL=https://ollama.prod.example.com
SECONDBRAIN_LOG_FORMAT=json  # Structured logging for production
SECONDBRAIN_CONNECTION_CACHE_TTL=120.0  # Longer cache for production
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=20  # Higher limit for production
```

### Testing

```bash
# .env.test
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain_test
SECONDBRAIN_MONGO_COLLECTION=test_embeddings
SECONDBRAIN_CONNECTION_CACHE_TTL=0.1  # Minimal cache for tests
```

## Advanced Configuration

### Custom Embedding Dimensions

If using a different embedding model:

```bash
# For embeddinggemma:latest (768 dimensions)
SECONDBRAIN_EMBEDDING_DIMENSIONS=768

# For other models (check model documentation)
SECONDBRAIN_EMBEDDING_DIMENSIONS=384   # Smaller model
SECONDBRAIN_EMBEDDING_DIMENSIONS=1024  # Larger model
```

⚠️ **Important**: The embedding dimensions must match your model's output. Mismatch will cause vector search to fail.

### Custom Chunking Strategies

For different document types:

```bash
# For long technical documents
SECONDBRAIN_CHUNK_SIZE=8192
SECONDBRAIN_CHUNK_OVERLAP=200

# For short social media posts
SECONDBRAIN_CHUNK_SIZE=512
SECONDBRAIN_CHUNK_OVERLAP=50

# For code files
SECONDBRAIN_CHUNK_SIZE=2048
SECONDBRAIN_CHUNK_OVERLAP=100
```

### Rate Limiting Tuning

Adjust based on your infrastructure:

```bash
# Conservative (slow network)
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=5
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0

# Aggressive (fast local setup)
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=20
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0

# Production with dedicated Ollama server
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=50
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0
```

## Configuration in Code

Access configuration programmatically:

```python
from secondbrain.config import get_config

# Get configuration instance
config = get_config()

# Access settings
print(f"MongoDB URI: {config.mongo_uri}")
print(f"Chunk size: {config.chunk_size}")
print(f"Default top-k: {config.default_top_k}")

# Validate configuration
try:
    config = get_config()
    print("Configuration is valid")
except ValueError as e:
    print(f"Configuration error: {e}")
```

## Configuration Priority

Configuration is loaded in this order (later sources override earlier):

1. Default values (in code)
2. `.env` file
3. Environment variables
4. Command-line arguments (where applicable)

Example:
```bash
# .env file
SECONDBRAIN_CHUNK_SIZE=2048

# Environment variable (overrides .env)
export SECONDBRAIN_CHUNK_SIZE=4096

# Result: chunk_size = 4096
```

## Troubleshooting

### Configuration Not Being Applied

**Problem**: Changes to `.env` file not taking effect

**Solutions**:
1. Restart the application
2. Check for environment variable conflicts:
   ```bash
   printenv | grep SECONDBRAIN
   ```
3. Clear Python cache:
   ```bash
   find . -type d -name __pycache__ -exec rm -rf {} +
   ```

### Invalid Configuration Errors

**Problem**: Configuration validation errors at startup

**Solutions**:
1. Check error message for specific field
2. Verify format matches requirements
3. Check for typos in variable names

### Connection Failures

**Problem**: Cannot connect to MongoDB or Ollama despite correct config

**Solutions**:
1. Verify services are running
2. Check firewall rules
3. Test connection manually:
   ```bash
   # Test MongoDB
   mongosh mongodb://localhost:27017

   # Test Ollama
   curl http://localhost:114../api-reference/index.mdtags
   ```

## Next Steps

- [Docker Setup](./docker.md) - Containerized deployment
- [Development Guide](./development.md) - Development workflow
- [Architecture](../architecture/SCHEMA.md) - Database schema
