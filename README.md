# SecondBrain - Local Document Intelligence CLI

A local document intelligence CLI tool that ingests documents, generates embeddings using Ollama, and stores vectors in MongoDB for semantic search.

## Documentation

- **[Full Documentation](docs/)** - Complete documentation index
- **[Quick Start](#quick-start)** - Get started in 5 minutes
- **[Development Guide](docs/guide/DEVELOPMENT.md)** - Development setup and workflow
- **[Configuration](docs/guide/CONFIGURATION.md)** - Full configuration reference
- **[Async Guide](docs/guide/ASYNC.md)** - Asynchronous API usage
- **[Docker Setup](docs/guide/DOCKER.md)** - Containerized deployment
- **[Building](docs/guide/BUILDING.md)** - Create distributable binaries

## Quick Start

### Prerequisites

- Python 3.11+
- MongoDB 8.0+ (via Docker or local)
- Ollama (via Docker or local)

### Installation

```bash
# Start services (Docker)
docker-compose up -d  # MongoDB
ollama serve          # Ollama (macOS/Linux)

# Install SecondBrain
pip install -e ".[dev]"

# Verify
secondbrain --help
```

### Basic Usage

```bash
# Ingest documents
secondbrain ingest /path/to/documents/

# Search semantically
secondbrain search "what is this about?"

# List documents
secondbrain list

# Check health
secondbrain health
```

## Features

- **Multi-format ingestion**: PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, audio
- **Semantic search**: Natural language queries with cosine similarity
- **Async support**: Full async API for embedding generation and storage
- **Rate limiting**: Protects Ollama API from overload
- **12-factor app**: Environment-driven configuration

## CLI Reference

| Command | Description |
|---------|-------------|
| `ingest` | Add documents to the vector database |
| `search` | Perform semantic search queries |
| `list` | List ingested documents/chunks |
| `delete` | Remove documents |
| `status` | Display database statistics |
| `health` | Check service health |

```bash
# See all options
secondbrain --help
secondbrain ingest --help
secondbrain search --help
```

## Configuration

Key environment variables (see [Full Config](docs/guide/CONFIGURATION.md)):

```bash
# .env file
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_OLLAMA_URL=http://localhost:11434
SECONDBRAIN_MODEL=embeddinggemma:latest
SECONDBRAIN_CHUNK_SIZE=4096
```

## Development

### Quality Checks

```bash
# Linting and formatting
ruff check . && ruff format .

# Type checking
mypy .

# Tests
pytest

# All checks
ruff check . && ruff format --check . && mypy . && pytest
```

### Performance Tips

- Use `--batch-size` for parallel processing
- Adjust `chunk_size` for your document types
- Enable verbose mode for timing info: `--verbose`

## Architecture

See the [Architecture Documentation](docs/architecture/DATA_FLOW.md) for:
- High-level system architecture
- Component details and responsibilities
- Data flow diagrams
- Processing pipelines
- Performance considerations
- Error handling strategies

And [Schema Reference](docs/architecture/SCHEMA.md) for database structure.

## License

This project is licensed under the MIT License. See [LICENSE.md](docs/LICENSE.md) for details.

