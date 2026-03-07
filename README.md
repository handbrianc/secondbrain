# SecondBrain - Local Document Intelligence CLI

A local document intelligence CLI tool that ingests documents, generates embeddings using Ollama, and stores vectors in MongoDB for semantic search.

## Documentation

- **[Full Documentation](docs/)** - Complete documentation index
- **[Development Guide](docs/guide/DEVELOPMENT.md)** - Development setup and workflow
- **[Code Standards](docs/guide/CODE_STANDARDS.md)** - Coding guidelines
- **[Contributing](docs/guide/CONTRIBUTING.md)** - How to contribute
- **[Architecture](docs/architecture/SCHEMA.md)** - Database schema reference

## Features

- **Multi-format document ingestion**: Supports PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, LaTeX, CSV, Images, Audio, and more
- **Semantic embeddings**: Uses Ollama with `embeddinggemma:latest` model
- **Vector storage**: MongoDB-backed storage with cosine similarity search
- **CLI-first**: Single executable, no server required
- **12-factor app**: Environment-driven configuration

## Installation

### Quick Start with Docker

#### macOS (Ollama installed locally)

```bash
# Clone and start MongoDB
docker-compose up -d

# Start Ollama locally
ollama serve
```

#### Linux / Windows (Ollama via Docker)

```bash
# Clone and run with Docker Compose
docker-compose up -d

# Verify services
docker ps
```

### Local Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd secondbrain

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Verify installation
secondbrain --help
```

## Requirements

- Python 3.11+
- MongoDB (via Docker or local installation)
- Ollama (via Docker or local installation)

## Docker Setup

### macOS (Ollama installed locally)

If you have Ollama installed locally (via `brew install ollama`), only start MongoDB:

```bash
# Start MongoDB only
docker-compose up -d

# Start Ollama locally
ollama serve

# Verify services
docker-compose ps
ollama list
```

### Linux / Windows (Ollama via Docker)

```bash
# Start MongoDB and Ollama
docker-compose up -d

# Or start them separately:
docker-compose up -d mongodb        # MongoDB only
docker-compose -f docker-compose.ollama.yml up -d  # Ollama only

# Verify Ollama is running
curl http://localhost:11434/api/tags

# Stop services
docker-compose down
```

### Manual Docker Setup

```bash
# Run MongoDB (8.0+ required for vector search)
docker run -d --name mongodb -p 27017:27017 mongo:8.0
docker run -d --name mongodb -p 27017:27017 mongo:7.0

# Run Ollama
docker run -d --name ollama -p 11434:11434 ollama/ollama

# Pull embedding model (first time only)
docker exec ollama ollama pull embeddinggemma:latest
```

## Configuration

Configure SecondBrain using environment variables:

| Variable | Default | Description |
|-----------|---------|-------------|
| `SECONDBRAIN_MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection URI |
| `SECONDBRAIN_MONGO_DB` | `secondbrain` | Database name |
| `SECONDBRAIN_MONGO_COLLECTION` | `embeddings` | Collection name for embeddings |
| `SECONDBRAIN_OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `SECONDBRAIN_MODEL` | `embeddinggemma:latest` | Embedding model to use |
| `SECONDBRAIN_CHUNK_SIZE` | `4096` | Chunk size for document splitting |
| `SECONDBRAIN_CHUNK_OVERLAP` | `50` | Chunk overlap for splitting |
| `SECONDBRAIN_DEFAULT_TOP_K` | `5` | Default number of search results |
| `SECONDBRAIN_LOG_FORMAT` | `rich` | Log format: `rich` or `json` |
| `SECONDBRAIN_HEALTH_CHECK_TTL` | `60` | Service check cache TTL in seconds |

### Using .env File

Create a `.env` file in the project root:

```bash
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_OLLAMA_URL=http://localhost:11434
SECONDBRAIN_MODEL=embeddinggemma:latest
```

## CLI Commands

### Ingest Documents

```bash
# Ingest a single document
secondbrain ingest document.pdf

# Ingest all files in a directory
secondbrain ingest /path/to/documents/

# Recursive ingestion
secondbrain ingest /path/to/documents/ --recursive

# Specify chunk parameters
secondbrain ingest document.pdf --chunk-size 1024 --chunk-overlap 100

# Verbose output
secondbrain ingest document.pdf --verbose
```

### Async Support

SecondBrain includes full async support for embeddings and storage operations:

```python
# Async embedding generation
from secondbrain.embedding import EmbeddingGenerator

generator = EmbeddingGenerator()

# Single async embedding
embedding = await generator.generate_async("your text here")

# Batch async embeddings
embeddings = await generator.generate_batch_async(["text1", "text2"])
```

```python
# Async connection validation
from secondbrain.embedding import EmbeddingGenerator

generator = EmbeddingGenerator()
is_available = await generator.validate_connection_async(force=False)
```

```bash
# CLI commands support async operations internally
# All CLI commands can be called with --verbose for async timing info
secondbrain search "query" --verbose
```

### Semantic Search

```bash
# Search with natural language query
secondbrain search "what is the project about"

# Limit results
secondbrain search "query" --top-k 10

# Filter by source file
secondbrain search "query" --source document.pdf

# Filter by file type
secondbrain search "query" --file-type pdf

# JSON output
secondbrain search "query" --format json
```

### List Documents

```bash
# List all documents
secondbrain list

# List by source file
secondbrain list --source document.pdf

# List by chunk ID
secondbrain list --chunk-id <uuid>

# Pagination
secondbrain list --page 2 --per-page 50
```

### Delete Documents

```bash
# Delete by source file
secondbrain delete --source document.pdf

# Delete by chunk ID
secondbrain delete --chunk-id <uuid>

# Delete all documents
secondbrain delete --all
```

### Status

```bash
# Show database statistics
secondbrain status
```

### Health Check

```bash
# Check health status (text format)
secondbrain health

# Check health status (JSON format)
secondbrain health --output json

# Verbose output for health check
secondbrain health --verbose
```

## Development Setup

### Performance Optimizations

SecondBrain includes several performance optimizations:

```bash
# Batch processing for document ingestion
secondbrain ingest /path/to/documents/ --batch-size 20

# Adjust chunk size for optimal processing
secondbrain ingest document.pdf --chunk-size 2048 --chunk-overlap 100
```

**Built-in Optimizations:**
- **Connection caching** - Service checks are cached (default 60s TTL)
- **Rate limiting** - Protects Ollama API from overload
- **Batch processing** - Parallel file processing with `--batch-size`
- **Async support** - Full async API for embedding generation

### Code Quality Tools

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linting
ruff check .

# Run formatting
ruff format .

# Run type checking
mypy .

# Run all checks
ruff check . && ruff format --check . && mypy .
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=secondbrain --cov-report=html

# Run specific test file
pytest tests/test_embedding.py

# Run tests with verbose output
pytest -v

# Run tests matching a pattern
pytest -k "test_pattern"
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run all hooks manually
pre-commit run --all-files
```

### Security Scanning

```bash
# Run security scan
bandit -r secondbrain/

# Check dependencies for vulnerabilities
safety check
```

### Run All Quality Checks

```bash
# Run linting, formatting check, and type checking
ruff check . && ruff format --check . && mypy .
```

## Building

### Single Executable

```bash
# Build single executable using Docker
docker build -t secondbrain:latest .

# Or run directly with Python
pyinstaller --onefile src/secondbrain/cli/__init__.py
```

## Data Flow

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   User CLI   │────▶│   Document Ingest│────▶│   Embedding Gen  │────▶│   MongoDB Store  │
│  (firstbrain)│     │    (docling)     │     │  (ollama API)    │     │(vector search)   │
└──────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘
          │                                                                   │
          │                                                                   ▼
          │                                                          ┌──────────────────┐
          │                                                          │   User Query     │
          │                                                          │   (semantic)     │
          │                                                                   │
          │                                                                   ▼
          │                                                          ┌──────────────────┐
          │                                                          │   Searcher       │
          │                                                          │   (cosine sim)   │
          └───────────────────────────────────────────────────────────────────────┘
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   secondbrain   │     │     MongoDB     │
│   CLI Tool      │────▶│  (vector store) │
│                 │     │                 │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│     Ollama      │
│ (embeddinggemma)│
└─────────────────┘
```

## License

MIT

