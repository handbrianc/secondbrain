# SecondBrain Documentation

Welcome to the SecondBrain documentation. This is your complete guide to using and contributing to the project.

## What is SecondBrain?

SecondBrain is a local document intelligence CLI tool that:
- **Ingests documents** in multiple formats (PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, audio)
- **Generates embeddings** using sentence-transformers's local AI models
- **Stores vectors** in MongoDB for efficient semantic search
- **Provides both sync and async APIs** for flexibility

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Start services
docker-compose up -d  # MongoDB
sentence-transformers serve          # sentence-transformers

# Run the CLI
secondbrain --help
```

## Documentation Navigation

### For New Users

| Section | Description |
|---------|-------------|
| [Getting Started](getting-started/index.md) | Installation, quick start, and basic configuration |
| [User Guide](user-guide/index.md) | Complete usage guide for all features |
| [CLI Reference](api-reference/cli.md) | All CLI commands and options |

### For Developers

| Section | Description |
|---------|-------------|
| [Developer Guide](developer-guide/index.md) | Development setup, workflows, and contributions |
| [Architecture](architecture/index.md) | System design and data flow |
| [API Reference](api-reference/index.md) | Code-level API documentation |

### Quick Links

- [Installation Guide](getting-started/installation.md) - Detailed installation steps
- [Quick Start Guide](getting-started/quick-start.md) - Get started in 5 minutes
- [Configuration Guide](getting-started/configuration.md) - Essential configuration
- [Document Ingestion](user-guide/document-ingestion.md) - How to add documents
- [Semantic Search](user-guide/search-guide.md) - How to search
- [Development Setup](developer-guide/development.md) - Get started with development
- [Docker Setup](developer-guide/docker.md) - Containerized deployment
- [Async API Guide](developer-guide/async-api.md) - Asynchronous programming

## Examples

For practical usage examples, see the [examples directory](../docs/examples/README.md):

- **Basic Usage**: Simple CLI-style examples
- **Advanced**: Custom chunking, batch processing, async workflows
- **Integrations**: Flask and FastAPI REST APIs
- **Scripts**: Utility scripts for bulk operations

## Configuration

All modules use environment-based configuration. See [Configuration Guide](getting-started/configuration.md) for details.

Key environment variables:
- `SECONDBRAIN_MONGO_URI`: MongoDB connection string
- `SECONDBRAIN_SENTENCE_TRANSFORMERS_URL`: sentence-transformers API URL
- `SECONDBRAIN_MODEL`: Embedding model name
- `SECONDBRAIN_CHUNK_SIZE`: Text chunk size

## Contributing

We welcome contributions! See [Contributing Guide](developer-guide/contributing.md) for details.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE.md) for details.
