# Getting Started with SecondBrain

Welcome to SecondBrain - your local document intelligence CLI for semantic search and conversational Q&A.

## What is SecondBrain?

SecondBrain is a command-line tool that transforms your documents into a searchable knowledge base:

- **Ingest documents** in multiple formats (PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, audio)
- **Generate embeddings** using local sentence-transformers models
- **Store vectors** in MongoDB for efficient semantic search
- **Chat interactively** with your documents using local LLMs

## Quick Start

### Prerequisites

- **Python 3.11+** - Check with `python --version`
- **MongoDB 8.0+** - Via Docker or local installation
- **sentence-transformers** - Via Docker or local installation

### Installation

```bash
# Install SecondBrain
# For production: pip install -e "."
# For development: pip install -e ".[dev]"
pip install -e ".[dev]"

# Start services (Docker)
docker-compose up -d  # MongoDB
sentence-transformers serve  # sentence-transformers (macOS/Linux)

# Verify installation
secondbrain --help
```

> **Choose Your Installation Profile**: See [Dependency Installation Guide](installation.md#choose-your-installation-profile) for detailed options.

### First Steps

```bash
# Ingest your first documents
secondbrain ingest /path/to/your/documents/

# Search semantically
secondbrain search "what is this about?"

# List your documents
secondbrain ls

# Start interactive chat
secondbrain chat
```

## Documentation Navigation

### For New Users
- [Installation Guide](installation.md) - Detailed installation steps
- [Quick Start](quick-start.md) - Get started in 5 minutes
- [Configuration](configuration.md) - Essential configuration options
- [MongoDB Authentication](mongodb-authentication.md) - **REQUIRED** for production
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

### For Users
- [User Guide](../user-guide/index.md) - Complete usage guide
- [CLI Reference](../user-guide/cli-reference.md) - All CLI commands
- [Conversational Q&A](../user-guide/conversational-qa.md) - Multi-turn chat

### For Developers
- [Developer Guide](../developer-guide/index.md) - Development setup and workflows
- [Architecture](../architecture/index.md) - System design and data flow
- [API Reference](../api/index.md) - Code-level API documentation

## Key Features

### Multi-Format Document Support

SecondBrain automatically parses and extracts text from:
- **Documents**: PDF, DOCX, PPTX, XLSX
- **Web**: HTML, Markdown, Text
- **Media**: Images (OCR), Audio (transcription)

### Semantic Search

Search by meaning, not keywords:
```bash
secondbrain search "best practices for error handling"
```

### Conversational Q&A

Chat with your documents:
```bash
secondbrain chat
# Interactive mode with context-aware responses
```

### Production-Ready Features

- **Multicore ingestion** - Parallel document processing
- **Async API** - High-throughput programmatic access
- **Circuit breaker** - Automatic failure handling
- **Rate limiting** - Protect downstream services
- **OpenTelemetry** - Distributed tracing

## Configuration

Create a `.env` file in your project root:

```bash
# MongoDB Authentication (REQUIRED for production)
MONGODB_INITDB_ROOT_USERNAME=your_username
MONGODB_INITDB_ROOT_PASSWORD=your_strong_password

# MongoDB Connection (must match credentials above)
SECONDBRAIN_MONGO_URI=mongodb://your_username:your_strong_password@localhost:27017
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
SECONDBRAIN_CHUNK_SIZE=4096

# Optional performance tuning
SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_RATE_LIMIT_ENABLED=true
```

**⚠️ Security Note**: Enable MongoDB authentication for production deployments. See [MongoDB Authentication Setup](mongodb-authentication.md) for detailed instructions.

See [Configuration Reference](configuration.md) for complete options.

## Next Steps

1. **Complete Installation**: Follow the [Installation Guide](installation.md)
2. **Quick Tutorial**: Work through the [Quick Start](quick-start.md)
3. **Configure Authentication**: Set up MongoDB authentication with [MongoDB Auth Guide](mongodb-authentication.md)
4. **Configure Settings**: Set up your environment with [Configuration Guide](configuration.md)
5. **Explore Features**: Read the [User Guide](../user-guide/index.md)
6. **Check Examples**: See practical examples in [docs/examples/](../examples/README.md)

## Need Help?

- **Troubleshooting**: [Troubleshooting Guide](troubleshooting.md)
- **Documentation**: [Full Documentation](../index.md)
- **Bug Reports**: [GitHub Issues](https://github.com/your-username/secondbrain/issues)
- **Questions**: [GitHub Discussions](https://github.com/your-username/secondbrain/discussions)
