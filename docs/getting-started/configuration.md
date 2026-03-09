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
SECONDBRAIN_OLLAMA_URL=http://localhost:11434
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

### Ollama Settings

```bash
# Local Ollama
SECONDBRAIN_OLLAMA_URL=http://localhost:11434

# Remote Ollama server
SECONDBRAIN_OLLAMA_URL=https://ollama.your-server.com
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
ollama pull embeddinggemma:latest
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

# Test Ollama connection
curl http://localhost:11434/api/tags
```

## Next Steps

- [Quick Start](./quick-start.md) - Get started quickly
- [User Guide](../user-guide/index.md) - Learn to use SecondBrain
- [Full Configuration Reference](../developer-guide/configuration.md) - Complete reference
- [Docker Setup](../developer-guide/docker.md) - Containerized deployment
