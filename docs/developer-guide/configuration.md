# Configuration Guide

Advanced configuration options for SecondBrain.

## Environment Variables

### Core Configuration

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=secondbrain

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=cuda  # or cpu
EMBEDDING_BATCH_SIZE=32

# Chunking
CHUNK_SIZE=500
CHUNK_OVERLAP=50

# Performance
MAX_WORKERS=4
BATCH_SIZE=100

# Logging
LOG_LEVEL=INFO
LOG_FILE=secondbrain.log
```

### Optional Configuration

```env
# Ollama LLM
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2

# OpenTelemetry
OTEL_SERVICE_NAME=secondbrain
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# GPU
CUDA_VISIBLE_DEVICES=0
TORCH_NUM_THREADS=4
```

## Configuration Classes

### Settings Model

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "secondbrain"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 500
    chunk_overlap: int = 50
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Custom Configuration

```python
from secondbrain.config import SecondBrainConfig

config = SecondBrainConfig(
    mongodb_uri="mongodb://localhost:27017",
    embedding_model="sentence-transformers/all-mpnet-base-v2",
    chunk_size=1000,
    chunk_overlap=100,
    enable_gpu=True
)
```

## MongoDB Configuration

### Connection String

```env
# Local
MONGODB_URI=mongodb://localhost:27017

# With authentication
MONGODB_URI=mongodb://user:password@localhost:27017

# Replica set
MONGODB_URI=mongodb://host1:27017,host2:27017,host3:27017

# Atlas
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net
```

### Connection Pooling

```python
from motor.motor_asyncio import AsyncMongoClient

client = AsyncMongoClient(
    os.getenv("MONGODB_URI"),
    maxPoolSize=50,
    minPoolSize=10,
    maxIdleTimeMS=300000,
    serverSelectionTimeoutMS=5000
)
```

## Embedding Model Configuration

### Model Selection

```python
# Sentence Transformers models
models = {
    "all-MiniLM-L6-v2": 384,      # Fast, small
    "all-mpnet-base-v2": 768,      # Better quality
    "multi-qa-mpnet-base-dot-v1": 768,  # Optimized for QA
}

# Set model
os.environ["EMBEDDING_MODEL"] = "all-mpnet-base-v2"
```

### GPU Configuration

```python
import torch

# Check GPU availability
if torch.cuda.is_available():
    device = "cuda"
    torch.cuda.set_device(0)
else:
    device = "cpu"
```

## Logging Configuration

### Basic Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("secondbrain.log"),
        logging.StreamHandler()
    ]
)
```

### Advanced Logging

```python
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "formatters": {
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "detailed",
            "level": "INFO"
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "detailed",
            "filename": "secondbrain.log",
            "level": "DEBUG"
        }
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"]
    }
}

logging.config.dictConfig(LOGGING_CONFIG)
```

## Performance Tuning

### Batch Processing

```env
# Ingestion
BATCH_SIZE=100
MAX_WORKERS=4

# Search
SEARCH_BATCH_SIZE=32
MAX_CONCURRENT_SEARCHES=10
```

### Memory Management

```python
# Limit memory usage
import torch
torch.set_num_threads(4)

# Clear cache
torch.cuda.empty_cache()
```

## OpenTelemetry Configuration

```env
# Enable tracing
OTEL_SERVICE_NAME=secondbrain
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
```

## Security Configuration

### Authentication

```env
# MongoDB authentication
MONGODB_USERNAME=secondbrain
MONGODB_PASSWORD=secure_password

# JWT (if enabled)
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
```

### TLS/SSL

```env
# Enable TLS
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net?ssl=true
MONGODB_TLS_CA_FILE=/path/to/ca.pem
```

## Configuration Validation

```python
from pydantic import ValidationError

try:
    config = SecondBrainConfig()
    config.validate()
except ValidationError as e:
    print(f"Invalid configuration: {e}")
```

## See Also

- [Getting Started](../getting-started/configuration.md)
- [Development Setup](development.md)
- [Async API](async-api.md)
