# Configuration Guide

Essential configuration for SecondBrain.

## Overview

SecondBrain uses environment-based configuration via:
1. `.env` file (recommended for local development)
2. Environment variables
3. Command-line arguments (where applicable)

All settings use the `SECONDBRAIN_` prefix.

## Quick Configuration

Create a `.env` file:

```bash
# Core settings (required)
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:local embedding
SECONDBRAIN_MODEL=embeddinggemma:latest

# Document processing
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50

# Search settings
SECONDBRAIN_DEFAULT_TOP_K=5
```

## Essential Settings

### MongoDB Connection

```bash
# Local MongoDB
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017

# MongoDB with authentication
SECONDBRAIN_MONGO_URI=mongodb://user:password@localhost:27017

# MongoDB Atlas (cloud)
SECONDBRAIN_MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net
```

### sentence-transformers Settings

```bash
# Local sentence-transformers
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:local embedding

# Remote sentence-transformers server
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=https://sentence-transformers.your-server.com
```

### Embedding Model

```bash
# Recommended model
SECONDBRAIN_MODEL=embeddinggemma:latest

# Alternative models
SECONDBRAIN_MODEL=nomic-embed-text:latest
SECONDBRAIN_MODEL=mxbai-embed-large:latest
```

⚠️ **Important**: Make sure to pull the model first:
```bash
sentence-transformers pull embeddinggemma:latest
```

## Document Processing

### Chunk Size

```bash
# Default (good for most documents)
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50

# Long technical documents
SECONDBRAIN_CHUNK_SIZE=8192
SECONDBRAIN_CHUNK_OVERLAP=200

# Short documents
SECONDBRAIN_CHUNK_SIZE=1024
SECONDBRAIN_CHUNK_OVERLAP=25
```

### File Size Limits

```bash
# Maximum file size (default: 100MB)
SECONDBRAIN_MAX_FILE_SIZE_BYTES=104857600
```

## Search Settings

```bash
# Number of results to return (default: 5)
SECONDBRAIN_DEFAULT_TOP_K=5

# Embedding dimensions (match your model)
SECONDBRAIN_EMBEDDING_DIMENSIONS=768  # For embeddinggemma
```

## Performance Settings

### Rate Limiting

```bash
# Conservative (slow networks)
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=5
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0

# Aggressive (local setup)
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=20
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0
```

### Multicore Processing

SecondBrain supports parallel document ingestion using multiple CPU cores:

```bash
# Set default number of worker processes (via environment)
SECONDBRAIN_MAX_WORKERS=4

# Or override per-command with CLI flag
secondbrain ingest /path/to/docs --cores 4
```

**Performance Tips:**

- **Use `--cores` for batch ingestion**: For directories with 10+ files, use 2-4 cores for best performance
- **Single files don't benefit**: For single document ingestion, core count has minimal impact
- **Balance cores with memory**: Each worker process uses ~100-200MB RAM. On 8GB systems, use 2-4 cores max
- **CPU-bound vs I/O-bound**: Text extraction benefits from multiple cores; embedding generation is I/O-bound and uses threading
- **Diminishing returns**: Beyond 4-6 cores, performance gains plateau due to memory bandwidth limits

**⚠️ Rate Limiting Warning:**

When using multiprocessing (`--cores > 1`), rate limiting is applied **per-process**, not globally. 
This means the effective rate limit is multiplied by the number of cores. For example, with 
`SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=10` and `--cores 4`, you'll get ~40 requests per window 
instead of 10. To maintain strict rate limiting, either:
- Use `--cores 1` (threading-based parallelism)
- Reduce `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS` proportionally (e.g., set to 2.5 for 4 cores)
- Accept higher API throughput for faster ingestion

**Platform Considerations:**

- **Windows:** Multiprocessing uses 'spawn' method. Worker functions must be at module level 
  (already satisfied). Some document types may have compatibility issues.
- **macOS/Linux:** Default 'fork' method works well for most use cases.

**Example Performance:**
| Files | Single Core | 4 Cores | Speedup |
|-------|-------------|---------|---------|
| 10    | ~2 min      | ~45s    | 2.7x    |
| 50    | ~10 min     | ~2.5 min| 4x      |
| 100   | ~20 min     | ~5 min  | 4x      |

### Caching

```bash
# Connection cache TTL (seconds)
SECONDBRAIN_CONNECTION_CACHE_TTL=60.0

# Health check cache TTL
SECONDBRAIN_HEALTH_CHECK_TTL=60
```

## Logging

```bash
# Rich terminal output (default)
SECONDBRAIN_LOG_FORMAT=rich

# JSON logging (production)
SECONDBRAIN_LOG_FORMAT=json
```

## Environment-Specific Config

### Development

```bash
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_LOG_FORMAT=rich
SECONDBRAIN_CONNECTION_CACHE_TTL=30.0
```

### Production

```bash
SECONDBRAIN_MONGO_URI=mongodb://user:pass@prod-cluster:27017
SECONDBRAIN_LOG_FORMAT=json
SECONDBRAIN_CONNECTION_CACHE_TTL=120.0
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=50
```

### Testing

```bash
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain_test
SECONDBRAIN_CONNECTION_CACHE_TTL=0.1
```

## Configuration Priority

Settings are loaded in this order (later overrides earlier):

1. Default values (in code)
2. `.env` file
3. Environment variables
4. Command-line arguments

## Validating Configuration

```bash
# Check if configuration is valid
secondbrain health

# View current configuration
secondbrain status
```

## Troubleshooting

### Configuration Not Applied

```bash
# Check environment variables
printenv | grep SECONDBRAIN

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

### Connection Issues

```bash
# Test MongoDB connection
mongosh mongodb://localhost:27017

# Test sentence-transformers connection
curl http://localhost:local embedding/api/tags
```

### Multicore Processing Issues

**ProcessPoolExecutor deadlocks:**
- Ensure worker functions are at module level (not class methods)
- On multi-threaded applications, use `spawn` method instead of `fork`
- Reduce core count if experiencing memory issues

**Memory exhaustion:**
- Lower `--cores` value (each worker uses ~100-200MB RAM)
- Reduce batch size with `--batch-size` option
- Monitor memory with `top` or `htop` during ingestion

**Slow performance:**
- Check if sentence-transformers is running on GPU (faster embeddings)
- Ensure MongoDB is on fast storage (SSD recommended)
- Verify network latency if using remote sentence-transformers/MongoDB

**Rate limiting issues:**
- Increase `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS` for local setups
- Reduce core count if hitting rate limits frequently
- Check sentence-transformers logs for request throttling

### Debugging Multiprocessing Issues

```bash
# Enable verbose logging
secondbrain ingest /path/to/docs --cores 2 --verbose

# Check worker process status
ps aux | grep python

# Monitor memory usage
watch -n 1 'ps -o rss= -p $(pgrep -f secondbrain)'
```

## Next Steps

- [Quick Start](./quick-start.md) - Get started quickly
- [User Guide](../user-guide/index.md) - Learn to use SecondBrain
- [Full Configuration Reference](../developer-guide/configuration.md) - Complete reference
- [Docker Setup](../developer-guide/docker.md) - Containerized deployment
