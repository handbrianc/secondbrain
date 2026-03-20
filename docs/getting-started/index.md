# Getting Started

Welcome to SecondBrain - your local document intelligence CLI for semantic search.

## What is SecondBrain?

SecondBrain is a command-line tool that:
- **Ingests documents** in multiple formats (PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, audio)
- **Generates embeddings** using sentence-transformers's local AI models
- **Stores vectors** in MongoDB for efficient semantic search
- **Provides both sync and async APIs** for flexibility

## Quick Start

### Prerequisites

- Python 3.11+
- MongoDB 8.0+ (via Docker or local installation)
- sentence-transformers (via Docker or local installation)

### Installation

```bash
# Install with dependencies
pip install -e ".[dev]"

# Start services
docker-compose up -d  # MongoDB
sentence-transformers serve          # sentence-transformers (macOS/Linux)

# Verify installation
secondbrain --help
```

### First Steps

```bash
# Ingest your first documents
secondbrain ingest /path/to/your/documents/

# Search semantically
secondbrain search "what is this about?"

# List your documents
secondbrain ls
```

## Documentation Navigation

### For New Users
- [Installation Guide](installation.md) - Detailed installation steps
- [Quick Start](quick-start.md) - Get started in 5 minutes
- [Configuration](configuration.md) - Essential configuration options

### For Users
- [User Guide](../user-guide/index.md) - Complete usage guide
- [CLI Reference](../user-guide/cli-reference.md) - All CLI commands

### For Developers
- [Developer Guide](../developer-guide/index.md) - Development setup and workflows
- [Architecture](../architecture/index.md) - System design and data flow
- [API Reference](../api/index.md) - Code-level API documentation

## Next Steps

1. Read the [Quick Start Guide](quick-start.md) for a 5-minute introduction
2. Configure your environment using [Configuration Guide](configuration.md)
3. Explore the [User Guide](../user-guide/index.md) for detailed usage
4. Check out the [examples directory](../examples/README.md) for practical code examples

## Need Help?

- [Troubleshooting](troubleshooting.md) - Frequently asked questions and common issues
- [Contributing](../developer-guide/contributing.md) - How to contribute
- [Report an Issue](https://github.com/your-repo/issues) - Bug reports and feature requests
