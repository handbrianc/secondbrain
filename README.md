# SecondBrain - Local Document Intelligence CLI

A local document intelligence CLI tool that ingests documents, generates embeddings using Ollama, and stores vectors in MongoDB for semantic search.

## Features

- **Multi-format document ingestion**: Supports PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, LaTeX, CSV, Images, Audio, and more
- **Semantic embeddings**: Uses Ollama with `embeddinggemma:latest` model
- **Vector storage**: MongoDB-backed storage with cosine similarity search
- **CLI-first**: Single executable, no server required
- **12-factor app**: Environment-driven configuration

## Installation

### Quick Start with Docker

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

### Using Docker Compose

```bash
# Start services
docker-compose up -d

# Verify Ollama is running
curl http://localhost:11434/api/tags

# Stop services
docker-compose down
```

### Manual Docker Setup

```bash
# Run MongoDB
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
| `SECONDBRAIN_CHUNK_SIZE` | `512` | Chunk size for document splitting |
| `SECONDBRAIN_CHUNK_OVERLAP` | `50` | Chunk overlap for splitting |
| `SECONDBRAIN_DEFAULT_TOP_K` | `5` | Default number of search results |

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

## Development Setup

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

## Building

### Single Executable

```bash
# Build single executable using Docker
docker build -t secondbrain:latest .

# Or run directly with Python
pyinstaller --onefile src/secondbrain/cli/__init__.py
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   secondbrain  │     │     MongoDB    │
│   CLI Tool      │────▶│  (vector store)│
│                 │     │                 │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│     Ollama      │
│ (embeddinggemma) │
└─────────────────┘
```

## License

MIT
