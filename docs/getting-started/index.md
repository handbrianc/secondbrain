# Getting Started

Welcome to SecondBrain! This section will help you get up and running.

## Quick Navigation

- [Installation](installation.md) - Set up SecondBrain
- [Quick Start](quick-start.md) - Your first 5 minutes
- [Configuration](configuration.md) - Configure your environment
- [Troubleshooting](troubleshooting.md) - Common issues
- [RAG Quickstart](rag-quickstart.md) - RAG pipeline setup

## What is SecondBrain?

SecondBrain is a local document intelligence CLI tool that enables:

- **Semantic Search**: Find documents by meaning, not keywords
- **Document Ingestion**: Process PDFs, Word docs, and more
- **Vector Storage**: MongoDB-based vector database
- **Privacy-First**: Everything runs locally

## Prerequisites

- Python 3.11+
- MongoDB 6.0+
- 4GB RAM minimum

## Quick Start Commands

```bash
# Install
pip install secondbrain

# Configure
echo "MONGODB_URI=mongodb://localhost:27017" > .env

# Ingest
secondbrain ingest my-document.pdf

# Search
secondbrain search "what is machine learning?"
```

## Next Steps

1. Read the [Installation Guide](installation.md)
2. Follow the [Quick Start Tutorial](quick-start.md)
3. Explore the [User Guide](../user-guide/index.md)
4. Check the [Developer Guide](../developer-guide/index.md)

## Support

- 📖 Documentation: [docs/](index.md)
- 🐛 Issues: [GitHub Issues](https://github.com/your-org/secondbrain/issues)
- 💬 Questions: [GitHub Discussions](https://github.com/your-org/secondbrain/discussions)
