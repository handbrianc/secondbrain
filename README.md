# SecondBrain - Local Document Intelligence CLI

A powerful local document intelligence CLI tool that enables semantic search over your documents using state-of-the-art embedding models and MongoDB vector search.

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Why SecondBrain?

- **🔒 Privacy-First**: All processing happens locally - no data leaves your machine
- **📄 Multi-Format Support**: PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio
- **🚀 Fast & Scalable**: Multicore ingestion, async API, and optimized vector search
- **🎯 Semantic Search**: Natural language queries with intelligent relevance ranking
- **🛠️ Production-Ready**: Circuit breaker, rate limiting, structured logging, and OpenTelemetry tracing
- **🐳 Docker Support**: Easy deployment with MongoDB and sentence-transformers services

## Quick Start

Get up and running in 5 minutes:

```bash
# 1. Install SecondBrain
pip install -e ".[dev]"

# 2. Start services (Docker)
docker-compose up -d  # MongoDB
sentence-transformers serve  # Embedding service

# 3. Ingest your first documents
secondbrain ingest /path/to/documents/

# 4. Search semantically
secondbrain search "what is this about?"
```

## Features

### Document Processing
- **Multi-format ingestion**: Automatically parse PDF, Word, PowerPoint, Excel, HTML, Markdown, and more
- **Smart chunking**: Configurable chunk sizes with overlap for context preservation
- **Multicore processing**: Parallel document ingestion with configurable CPU cores
- **Async support**: Full async API for high-throughput scenarios

### Search & Retrieval
- **Semantic search**: Natural language queries using cosine similarity
- **Configurable results**: Adjust top-k, similarity thresholds, and returned fields
- **Conversational Q&A**: Multi-turn chat with context-aware responses using local LLMs
- **Session management**: Persistent conversation sessions with history

### Production Features
- **Circuit breaker**: Automatic failure handling with self-recovery
- **Rate limiting**: Protect downstream services from overload
- **Structured logging**: JSON logs with configurable verbosity
- **OpenTelemetry**: Distributed tracing for observability
- **Health checks**: Comprehensive service connectivity validation

### Developer Experience
- **Type-safe**: Full type hints with mypy strict mode
- **Well-tested**: Comprehensive test suite with unit, integration, and property-based tests
- **Secure**: Integrated vulnerability scanning and SBOM generation
- **Extensible**: Clean architecture with pluggable components

## Documentation

| Section | Description |
|---------|-------------|
| [Getting Started](docs/getting-started/index.md) | Installation, quick start, and configuration |
| [User Guide](docs/user-guide/index.md) | Complete usage guide for all features |
| [CLI Reference](docs/user-guide/cli-reference.md) | All commands and options |
| [Developer Guide](docs/developer-guide/index.md) | Development setup and workflows |
| [Architecture](docs/architecture/index.md) | System design and data flow |
| [Examples](docs/examples/README.md) | Practical code examples |

## CLI Commands

```bash
# Ingest documents
secondbrain ingest /path/to/documents/ --cores 4

# Semantic search
secondbrain search "machine learning best practices" --top-k 10

# Interactive chat with your documents
secondbrain chat
# Or single query: secondbrain chat "What is the architecture?"

# List documents
secondbrain ls --details

# Check system health
secondbrain health

# View database statistics
secondbrain status
```

Run `secondbrain --help` for full command reference.

## Configuration

SecondBrain uses environment variables prefixed with `SECONDBRAIN_`:

```bash
# Core configuration
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_CHUNK_SIZE=4096

# Performance tuning
SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true

# Logging
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=pretty
```

See [Configuration Reference](docs/getting-started/configuration.md) for complete options.

## Development

### Setup

```bash
# Clone and setup
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Quality Checks

```bash
# Linting and formatting
ruff check . && ruff format .

# Type checking
mypy .

# Run tests
pytest -m "not integration"  # Fast tests
pytest                         # All tests including integration
```

### Test Profiles

| Profile | Command | Use Case |
|---------|---------|----------|
| Fast | `pytest -m "not integration"` | Pre-commit, quick feedback |
| Integration | `pytest -m integration` | Service testing |
| Full | `pytest` | Complete validation |

See [Testing Guide](docs/developer-guide/TESTING.md) for details.

### Security Scanning

```bash
# Full security scan
./scripts/security_scan.sh all

# Individual checks
./scripts/security_scan.sh audit   # Dependency vulnerabilities
./scripts/security_scan.sh bandit  # Code security
./scripts/security_scan.sh sbom    # Generate SBOM
```

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Documents  │ ──▶ │   Ingestor   │ ──▶ │  Chunking    │
└─────────────┘     └──────────────┘     └──────────────┘
                                                   │
                                                   ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Search    │ ◀── │   MongoDB    │ ◀── │  Embeddings  │
└─────────────┘     └──────────────┘     └──────────────┘
```

Key components:
- **CLI Layer**: Click-based command interface
- **Document Ingestor**: Multi-format parsing with Docling
- **Embedding Engine**: sentence-transformers for vector generation
- **Storage Layer**: MongoDB with vector search
- **Resilience**: Circuit breaker and rate limiting

See [Architecture Documentation](docs/architecture/index.md) for details.

## Examples

Practical examples in [docs/examples/](docs/examples/README.md):

- **Basic Usage**: Simple CLI-style examples
- **Advanced**: Custom chunking, batch processing, async workflows
- **Integrations**: Flask and FastAPI REST APIs
- **Scripts**: Utility scripts for bulk operations

## Contributing

Contributions are welcome! See [Contributing Guide](docs/developer-guide/contributing.md) for details.

### Quick Contribution Ideas
- Fix bugs or typos
- Improve documentation
- Add tests for edge cases
- Suggest new features via issues

## License

MIT License - See [LICENSE](docs/LICENSE.md) for details.

## Support

- **Documentation**: [docs/index.md](docs/index.md)
- **Troubleshooting**: [Troubleshooting Guide](docs/getting-started/troubleshooting.md)
- **Bug Reports**: [GitHub Issues](https://github.com/your-username/secondbrain/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-username/secondbrain/discussions)
