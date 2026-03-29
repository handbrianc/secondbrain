# SecondBrain

A local document intelligence CLI tool for semantic search and document management.

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-ruff-orange.svg)](https://github.com/astral-sh/ruff)

## Overview

SecondBrain is a powerful command-line tool that enables:

- **Semantic Search**: Find documents based on meaning, not just keywords
- **Document Ingestion**: Automatically process and index PDFs, Word docs, and more
- **Vector Storage**: Leverage MongoDB for efficient vector-based storage and retrieval
- **Local Processing**: All operations happen locally for privacy and security
- **RAG Pipeline**: Retrieval-Augmented Generation for intelligent document understanding

## Features

- 🚀 **Fast Ingestion**: Batch processing with GPU acceleration support
- 🔍 **Semantic Search**: Sentence transformer embeddings for accurate results
- 📄 **Multi-format Support**: PDF, DOCX, TXT, and more via Docling
- 🛡️ **Privacy-First**: Everything runs locally, no cloud dependencies
- 🔌 **Extensible**: MCP server integration for AI assistants
- 📊 **Rich Output**: Beautiful terminal UI with Rich library
- ⚡ **Async Support**: Full async/await API for high-performance applications

## Quick Start

```bash
# Install
pip install -e .

# Ingest a document
secondbrain ingest /path/to/document.pdf

# Search for information
secondbrain search "what is machine learning?"

# List all documents
secondbrain list
```

## Installation

### Prerequisites

- Python 3.11 or higher
- MongoDB 6.0+ (local or remote)
- GPU (optional, for faster embeddings)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/your-org/secondbrain.git
cd secondbrain

# Install with pip
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### Configuration

Create a `.env` file in your project root:

```env
# MongoDB connection
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=secondbrain

# Embedding model (optional, defaults to sentence-transformers/all-MiniLM-L6-v2)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Optional: Ollama for LLM integration
OLLAMA_BASE_URL=http://localhost:11434
```

## Usage

### Document Ingestion

```bash
# Ingest a single document
secondbrain ingest /path/to/document.pdf

# Ingest entire directory
secondbrain ingest /path/to/documents/ --recursive

# Custom chunking
secondbrain ingest /path/to/document.pdf --chunk-size 500 --chunk-overlap 50
```

### Semantic Search

```bash
# Basic search
secondbrain search "machine learning applications"

# Search with filters
secondbrain search "quarterly report" --collection finance --limit 5

# Export results
secondbrain search "project timeline" --format json --output results.json
```

### Document Management

```bash
# List all documents
secondbrain list

# Get document details
secondbrain info document-id

# Delete a document
secondbrain delete document-id

# Export all documents
secondbrain export --format json --output all-documents.json
```

## Architecture

SecondBrain is built with:

- **Docling**: Advanced document parsing and conversion
- **Sentence Transformers**: High-quality text embeddings
- **MongoDB + Motor**: Vector storage with async support
- **Click**: CLI framework with rich command structure
- **Rich**: Beautiful terminal output
- **Pydantic**: Data validation and settings management

See [Architecture Guide](docs/architecture/index.md) for detailed technical documentation.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint code
ruff check .
ruff format .

# Type checking
mypy .
```

See [Developer Guide](docs/developer-guide/index.md) for setup instructions and contribution guidelines.

## Documentation

- [Getting Started](docs/getting-started/index.md)
- [User Guide](docs/user-guide/index.md)
- [Developer Guide](docs/developer-guide/index.md)
- [API Reference](docs/api/index.md)
- [Architecture](docs/architecture/index.md)

## Integrations

- **MCP Server**: Connect with AI assistants like Cursor, Cline, and others
- **FastAPI/Flask**: Use the async API for web applications
- **Custom Scripts**: Python SDK for programmatic access

See [Examples](docs/examples/) for integration patterns.

## Security

SecondBrain prioritizes security:

- All data stays local
- No external API calls for document processing
- Secure credential management via python-dotenv
- Regular security audits with Bandit and Safety

See [Security Guide](docs/security/index.md) for details.

## Contributing

We welcome contributions! See [Contributing Guide](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE.md) file for details.

## Support

- 📖 Documentation: [docs/](docs/)
- 🐛 Issues: [GitHub Issues](https://github.com/your-org/secondbrain/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/your-org/secondbrain/discussions)

## Acknowledgments

- [Docling](https://github.com/DS4SD/docling) for document parsing
- [Sentence Transformers](https://www.sbert.net/) for embeddings
- [MongoDB](https://www.mongodb.com/) for vector storage
- [Rich](https://github.com/Textualize/rich) for terminal UI

---

Built with ❤️ using Python, Click, and MongoDB
