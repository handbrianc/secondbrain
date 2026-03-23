# SecondBrain Documentation

Welcome to the comprehensive documentation for SecondBrain - your local document intelligence CLI for semantic search and conversational Q&A.

## What is SecondBrain?

SecondBrain is a powerful command-line tool that transforms your documents into a searchable knowledge base:

- **📥 Ingest** documents in multiple formats (PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, audio)
- **🧠 Generate embeddings** using local sentence-transformers models
- **💾 Store vectors** in MongoDB for efficient retrieval
- **🔍 Search semantically** with natural language queries
- **💬 Chat interactively** with your documents using local LLMs

## Quick Links

### For New Users

| Guide | Description | Time |
|-------|-------------|------|
| [Getting Started](getting-started/index.md) | Installation and setup overview | 5 min read |
| [Quick Start](getting-started/quick-start.md) | Get running in 5 minutes | 5 min |
| [Installation Guide](getting-started/installation.md) | Detailed installation steps | 10 min |
| [Configuration](getting-started/configuration.md) | Essential configuration options | 10 min |

### For Users

| Guide | Description |
|-------|-------------|
| [User Guide](user-guide/index.md) | Complete usage reference |
| [CLI Reference](user-guide/cli-reference.md) | All commands and options |
| [Document Ingestion](user-guide/document-ingestion.md) | How to add documents |
| [Semantic Search](user-guide/search-guide.md) | Finding documents |
| [Conversational Q&A](user-guide/conversational-qa.md) | Multi-turn chat with docs |
| [Document Management](user-guide/document-management.md) | List, delete, and organize |

### For Developers

| Guide | Description |
|-------|-------------|
| [Developer Guide](developer-guide/index.md) | Development setup and workflows |
| [Development Setup](developer-guide/development.md) | Get started with code |
| [Testing Guide](developer-guide/TESTING.md) | Test structure and strategies |
| [Code Standards](developer-guide/code-standards.md) | Coding guidelines |
| [Contributing](developer-guide/contributing.md) | How to contribute |
| [Async API](developer-guide/async-api.md) | Asynchronous programming |
| [Docker Setup](developer-guide/docker.md) | Containerized deployment |
| [Building](developer-guide/building.md) | Create distributable binaries |

### Architecture & Technical

| Guide | Description |
|-------|-------------|
| [Architecture Overview](architecture/index.md) | System design and components |
| [Data Flow](architecture/DATA_FLOW.md) | Processing pipelines |
| [Schema Reference](architecture/SCHEMA.md) | Database structure |
| [SBOM Analysis](architecture/SBOM_ANALYSIS.md) | Dependency inventory |
| [License Risk Report](architecture/LICENSE-RISK-REPORT.md) | License compliance |

### Examples & Code

| Resource | Description |
|----------|-------------|
| [Examples Overview](examples/README.md) | All code examples |
| [Basic Usage](examples/basic_usage/) | Simple CLI-style examples |
| [Advanced](examples/advanced/) | Custom chunking, batch processing |
| [Integrations](examples/integrations/) | Flask and FastAPI examples |

### Reference

| Resource | Description |
|----------|-------------|
| [Troubleshooting](getting-started/troubleshooting.md) | Common issues and solutions |
| [Migration Guide](migration.md) | Schema migration strategies |
| [Security Guide](developer-guide/security.md) | Security best practices |
| [Changelog](developer-guide/changelog.md) | Version history |
| [License](LICENSE.md) | MIT License terms |

## Getting Started

### 1. Installation

```bash
# Install SecondBrain
pip install -e ".[dev]"

# Start services
docker-compose up -d  # MongoDB
sentence-transformers serve  # Embedding service

# Verify installation
secondbrain --help
```

### 2. Configuration

Create a `.env` file:

```bash
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_CHUNK_SIZE=4096
```

### 3. First Steps

```bash
# Ingest documents
secondbrain ingest /path/to/documents/

# Search semantically
secondbrain search "what is this about?"

# Interactive chat
secondbrain chat
```

## Key Concepts

### Document Processing

SecondBrain processes documents through a pipeline:

1. **Parsing**: Extract text from various formats using Docling
2. **Chunking**: Split text into manageable chunks with overlap
3. **Embedding**: Generate vector representations using sentence-transformers
4. **Storage**: Store vectors and metadata in MongoDB

### Semantic Search

Semantic search finds documents based on meaning, not keywords:

```bash
# Natural language queries
secondbrain search "best practices for error handling"

# Adjust result count
secondbrain search "machine learning" --top-k 10

# Filter by confidence
secondbrain search "data pipelines" --threshold 0.8
```

### Conversational Q&A

Chat with your documents using local LLMs:

```bash
# Start interactive chat
secondbrain chat

# Single query
secondbrain chat "Explain the architecture"

# With session management
secondbrain chat --session research-project
```

## Configuration Overview

All settings use `SECONDBRAIN_` prefix:

| Category | Key Settings |
|----------|--------------|
| **MongoDB** | `MONGO_URI`, `MONGO_DB`, `MONGO_COLLECTION` |
| **Embeddings** | `LOCAL_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `CHUNK_SIZE` |
| **Performance** | `MAX_WORKERS`, `BATCH_SIZE`, `RATE_LIMIT_ENABLED` |
| **Resilience** | `CIRCUIT_BREAKER_ENABLED`, `FAILURE_THRESHOLD` |
| **Logging** | `LOG_LEVEL`, `LOG_FORMAT`, `VERBOSE` |

See [Configuration Reference](getting-started/configuration.md) for complete options.

## Common Workflows

### Daily Use

```bash
# Add new documents
secondbrain ingest ./new-docs/

# Search for information
secondbrain search "relevant topic"

# Review results
secondbrain ls --details

# Chat for deeper understanding
secondbrain chat
```

### Development

```bash
# Run tests
pytest -m "not integration"

# Check code quality
ruff check . && ruff format . && mypy .

# Run with debug logging
SECONDBRAIN_LOG_LEVEL=DEBUG secondbrain ingest ./docs/
```

### Production

```bash
# Health check
secondbrain health --verbose

# Monitor status
secondbrain status

# Security scan
./scripts/security_scan.sh all
```

## Need Help?

- **Troubleshooting**: See [Troubleshooting Guide](getting-started/troubleshooting.md)
- **Bug Reports**: [GitHub Issues](https://github.com/your-username/secondbrain/issues)
- **Questions**: [GitHub Discussions](https://github.com/your-username/secondbrain/discussions)
- **Contributing**: [Contributing Guide](developer-guide/contributing.md)

## Next Steps

1. **New to SecondBrain?** Start with [Quick Start](getting-started/quick-start.md)
2. **Ready to use?** Jump to [User Guide](user-guide/index.md)
3. **Want to contribute?** Read [Developer Guide](developer-guide/index.md)
4. **Need examples?** Check [Examples Directory](examples/README.md)
