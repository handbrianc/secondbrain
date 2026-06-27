# SecondBrain - Local Document Intelligence CLI

A powerful local document intelligence CLI tool that enables semantic search over your documents using state-of-the-art embedding models and MongoDB vector search.

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Why SecondBrain?

- **🔒 Privacy-First**: Document parsing, chunking, and storage happen locally - embeddings go to your configured API endpoint
- **📄 Multi-Format Support**: PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio
- **🚀 Fast & Scalable**: Multicore ingestion, async API, and optimized vector search
- **🎯 Semantic Search**: Natural language queries with intelligent relevance ranking
- **🛠️ Production-Ready**: Circuit breaker, rate limiting, structured logging, and OpenTelemetry tracing
- **🐳 Docker Support**: Easy deployment with MongoDB and OpenAI-compatible embedding services (Ollama, LM Studio, vLLM)

## Quick Start

Get up and running in 5 minutes:

```bash
# 1. Clone and setup
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# 2. Start external services (Docker)
docker-compose up -d  # MongoDB + embedding service

# 3. Install SecondBrain
# For production use:
pip install -e "."
# For development:
pip install -e ".[dev]"

# 4. Ingest your first documents
secondbrain ingest /path/to/documents/

# 5. Search semantically
secondbrain search "what is this about?"
```

> **Choose Your Installation Profile**: See [Dependency Installation Guide](docs/getting-started/DEPENDENCIES.md) for detailed options (runtime, development, qualitative testing, observability).

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
| [MongoDB Authentication](docs/getting-started/mongodb-authentication.md) | **REQUIRED**: Setup MongoDB authentication for production |
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
# Core configuration (with MongoDB authentication)
MONGODB_INITDB_ROOT_USERNAME=your_username
MONGODB_INITDB_ROOT_PASSWORD=your_strong_password
SECONDBRAIN_MONGO_URI=mongodb://your_username:your_strong_password@localhost:27017
SECONDBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECONDBRAIN_CHUNK_SIZE=4096

# Performance tuning
SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true

# Logging
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=pretty
```

**⚠️ Security Note**: Enable MongoDB authentication for production deployments. See [MongoDB Authentication Setup](docs/getting-started/mongodb-authentication.md) for detailed instructions.

See [Configuration Reference](docs/getting-started/configuration.md) for complete options.

## Development

### Setup

```bash
# Clone and setup
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
python -m venv venv
source venv/bin/activate

# Install with development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

> **What's included in dev dependencies?** See [Dependency Installation Guide](docs/getting-started/DEPENDENCIES.md#development-dependencies) for the complete list of testing, linting, security, and documentation tools.

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

### Test Environment Configuration

**Quick Setup**:
```bash
# 1. Create test environment file
cp .env.test .env.test.local  # Customize as needed

# 2. Start test services
docker-compose -f docker-compose.test.yml up -d

# 3. Run tests (automatically uses .env.test)
pytest
```

**Environment Variables**:
Test configuration is automatically loaded from `.env.test` when running pytest. Key variables:

- `SECONDBRAIN_MONGO_URI` - Test MongoDB connection (default: localhost:27018)
- `SECONDBRAIN_MONGO_DB` - Test database name (default: secondbrain_test)
- `SECONDBRAIN_MONGO_COLLECTION` - Test collection (default: test_embeddings)
- `SECONDBRAIN_LOG_LEVEL` - Logging verbosity (default: DEBUG)
- `OTEL_TRACING_ENABLED=false` - Disable tracing for faster tests
- `SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=false` - Disable for faster tests

See `.env.test` for complete list of test environment variables.

### Qualitative Testing

Qualitative testing evaluates safety, factual accuracy, and robustness beyond metrics:

**Test Categories:**
- **Safety**: PII detection, dangerous topic filtering, harmful content prevention
- **Factual Accuracy**: Claim verification, hallucination detection, source attribution
- **Citation Quality**: Format compliance, source linking, reference completeness
- **Robustness**: Edge cases, adversarial queries, ambiguous input handling
- **LLM Judge**: Automated quality and safety evaluation

**Commands:**
```bash
# Run all qualitative tests
pytest tests/test_qualitative/ -v

# Run by category
pytest -m "safety" tests/test_qualitative/ -v
pytest -m "factual" tests/test_qualitative/ -v
pytest -m "robustness" tests/test_qualitative/ -v
pytest -m "llm_judge" tests/test_qualitative/ -v
```

**Quick Start:** `pip install -e ".[qualitative]"` then run tests above.

See [Qualitative Testing Framework](tests/test_qualitative/README.md) for details.

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
- **Embedding Engine**: OpenAI-compatible API for vector generation
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
