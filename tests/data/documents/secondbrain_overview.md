# SecondBrain - Local Document Intelligence CLI

## Overview

SecondBrain is a powerful local document intelligence CLI tool that enables semantic search over your documents using state-of-the-art embedding models and MongoDB vector search.

## Key Features

### Privacy-First Design
- All processing happens locally - no data leaves your machine
- No external API calls for embeddings or search
- Full control over your data and configuration

### Multi-Format Support
SecondBrain supports the following document formats:
- **PDF** - Portable Document Format
- **DOCX** - Microsoft Word documents
- **PPTX** - Microsoft PowerPoint presentations
- **XLSX** - Microsoft Excel spreadsheets
- **HTML** - Web pages and HTML documents
- **Markdown** - Markdown files (.md)
- **Images** - PNG, JPEG, TIFF, BMP, WebP with OCR
- **Audio** - WAV, MP3 with speech-to-text

### Smart Chunking
- Default chunk size: 4096 tokens
- Configurable chunk overlap for context preservation
- Word-boundary aware chunking to avoid cutting words
- Multicore processing for fast ingestion

### Semantic Search
- Uses sentence-transformers for embeddings
- MongoDB vector search with cosine similarity
- Configurable top-k results and similarity thresholds
- Returns relevant chunks with source metadata

## Architecture

### Main Components

1. **CLI Layer**
   - Built with Click for command-line interface
   - Commands: ingest, search, chat, ls, health, status

2. **Document Ingestor**
   - Multi-format parsing using Docling
   - Parallel processing with configurable cores
   - Progress tracking and error handling

3. **Embedding Engine**
   - sentence-transformers library
   - Local model: all-MiniLM-L6-v2 (default)
   - Caching layer for repeated queries

4. **Storage Layer**
   - MongoDB with vector search
   - Collection: chunks (default)
   - Index: embedding vector index

5. **Search Module**
   - Semantic query processing
   - Top-k result retrieval
   - Similarity ranking

6. **RAG Pipeline**
   - Query rewriting for better results
   - LLM-based answer generation
   - Context-aware responses

## Configuration

SecondBrain uses environment variables prefixed with `SECONDBRAIN_`:

### Core Configuration
```bash
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=chunks
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=200
```

### Performance Tuning
```bash
SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_RATE_LIMIT_RPS=10
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_THRESHOLD=5
```

### Logging
```bash
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=pretty
SECONDBRAIN_LOG_FILE=secondbrain.log
```

### Connection Settings
```bash
SECONDBRAIN_MONGO_CONNECT_TIMEOUT=5000
SECONDBRAIN_MONGO_SOCKET_TIMEOUT=10000
SECONDBRAIN_CONNECTION_CACHE_TTL=300
SECONDBRAIN_INDEX_READY_RETRY_COUNT=5
SECONDBRAIN_INDEX_READY_RETRY_DELAY=2.0
```

## CLI Commands

### Ingest Documents
```bash
# Basic ingestion
secondbrain ingest /path/to/documents/

# With options
secondbrain ingest /path/to/documents/ --cores 4 --verbose

# Specific collection
secondbrain ingest /path/to/documents/ --collection my_docs
```

### Search
```bash
# Basic search
secondbrain search "what is this about?"

# With options
secondbrain search "machine learning" --top-k 10 --threshold 0.5

# Show sources
secondbrain search "architecture" --show-sources
```

### Chat
```bash
# Interactive chat
secondbrain chat

# Single query
secondbrain chat "What is the default chunk size?"

# With session
secondbrain chat --session my-session
```

### Management
```bash
# List documents
secondbrain ls

# With details
secondbrain ls --details

# Database status
secondbrain status

# System health
secondbrain health
```

## Error Handling

### Circuit Breaker
- Automatic failure handling with self-recovery
- Configurable threshold and reset timeout
- Prevents cascade failures

### Rate Limiting
- Protects downstream services
- Configurable requests per second
- Queue-based request management

### Error Types
- `StorageConnectionError` - MongoDB connection issues
- `ValidationError` - Input validation failures
- `CircuitBreakerOpenError` - Circuit breaker triggered
- `RateLimitExceededError` - Rate limit exceeded

## Testing

### Test Profiles
```bash
# Fast tests (no integration)
pytest -m "not integration"

# Integration tests
pytest -m integration

# All tests
pytest
```

### Test Categories
- Unit tests with mocks
- Integration tests with services
- Property-based tests with Hypothesis
- Qualitative tests for safety and accuracy
- Quantitative tests for metrics

## Development

### Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Code Quality
```bash
ruff check .
ruff format .
mypy .
pytest
```

### Contributing
- Follow PEP 8 style guidelines
- Add type hints to all functions
- Write tests for new features
- Update documentation

## License

MIT License - See LICENSE file for details.
