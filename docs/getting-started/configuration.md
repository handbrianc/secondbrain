# Configuration

Configure SecondBrain for your environment.

## Environment Variables

Create a `.env` file in your project root:

```env
# MongoDB Connection
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=secondbrain

# Embedding Model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=cuda  # or cpu

# Chunking
CHUNK_SIZE=500
CHUNK_OVERLAP=50

# Performance
MAX_WORKERS=4
BATCH_SIZE=100

# Logging
LOG_LEVEL=INFO
```

## MongoDB Configuration

### Local MongoDB

```env
MONGODB_URI=mongodb://localhost:27017
```

### MongoDB Atlas

```env
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/secondbrain
```

### With Authentication

```env
MONGODB_URI=mongodb://username:password@localhost:27017
MONGODB_DB=secondbrain
```

## Embedding Models

### Available Models

```env
# Fast (384 dimensions)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Better quality (768 dimensions)
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2

# Optimized for QA
EMBEDDING_MODEL=sentence-transformers/multi-qa-mpnet-base-dot-v1
```

### GPU Acceleration

```env
# Enable GPU
EMBEDDING_DEVICE=cuda

# Set GPU (if multiple)
CUDA_VISIBLE_DEVICES=0
```

## Chunking Configuration

```env
# Token-based chunking
CHUNK_SIZE=500
CHUNK_OVERLAP=50

# Character-based chunking
CHUNK_SIZE=1000
CHUNK_OVERLAP=100
```

## Logging

```env
# Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log to file
LOG_FILE=secondbrain.log

# Log format
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

## Advanced Configuration

### Python Configuration

```python
from secondbrain.config import SecondBrainConfig

config = SecondBrainConfig(
    mongodb_uri="mongodb://localhost:27017",
    embedding_model="sentence-transformers/all-mpnet-base-v2",
    chunk_size=1000,
    chunk_overlap=100,
    enable_gpu=True,
    max_workers=8
)
```

### CLI Options

```bash
# Override config with CLI
secondbrain search "query" \
  --limit 20 \
  --format json \
  --verbose
```

## Validation

```bash
# Check configuration
secondbrain config --validate

# Show current config
secondbrain config --show
```

## Troubleshooting

### Connection Issues

```env
# Increase timeout
MONGODB_URI=mongodb://localhost:27017?serverSelectionTimeoutMS=5000

# Enable SSL
MONGODB_URI=mongodb://localhost:27017?ssl=true
```

### Performance Issues

```env
# Increase batch size
BATCH_SIZE=200

# Increase workers
MAX_WORKERS=8
```

## See Also

- [Installation](installation.md)
- [Quick Start](quick-start.md)
- [Developer Configuration](../developer-guide/configuration.md)
