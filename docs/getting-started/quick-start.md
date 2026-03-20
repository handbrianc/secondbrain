# Quick Start Guide

Get up and running with SecondBrain in 5 minutes.

## Step 1: Installation

```bash
# Install SecondBrain
pip install -e ".[dev]"

# Start services (Docker)
docker-compose up -d  # MongoDB
sentence-transformers serve          # sentence-transformers
```

## Step 2: Configure

Create a `.env` file in your project root:

```bash
# Core settings
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:11434
SECONDBRAIN_MODEL=embeddinggemma:latest

# Optional: adjust chunk size
SECONDBRAIN_CHUNK_SIZE=4096
```

## Step 3: Ingest Documents

```bash
# Ingest a directory of documents
secondbrain ingest /path/to/documents/

# Ingest with custom options
secondbrain ingest /path/to/documents/ \
  --chunk-size 2048 \
  --batch-size 10 \
  --verbose
```

Supported formats:
- PDF (.pdf)
- Word (.docx)
- PowerPoint (.pptx)
- Excel (.xlsx)
- HTML (.html, .htm)
- Markdown (.md)
- Text (.txt)
- Images (requires OCR)
- Audio (requires transcription)

## Step 4: Search

```bash
# Simple semantic search
secondbrain search "what is this about?"

# Limit results
secondbrain search "machine learning" --top-k 10

# Search with verbose output
secondbrain search "data pipelines" --verbose
```

## Step 5: Manage Documents

```bash
# List all documents
secondbrain ls

# List with details
secondbrain ls --details

# Delete a document
secondbrain delete <document-id>

# Check database status
secondbrain status
```

## Example Workflow

```bash
# 1. Ingest research papers
secondbrain ingest ./research-papers/

# 2. Search for relevant content
secondbrain search "neural network architectures"

# 3. List results
secondbrain ls --details

# 4. Delete outdated documents
secondbrain delete doc-12345
```

## Async API (Advanced)

For programmatic usage:

```python
import asyncio
from secondbrain.client import SecondBrainClient

async def main():
    client = SecondBrainClient()
    
    # Ingest documents
    await client.ingest("./documents/")
    
    # Search
    results = await client.search("semantic query")
    for result in results:
        print(result)
    
    # Close client
    await client.close()

asyncio.run(main())
```

See [Async Guide](../developer-guide/async-api.md) for details.

## Next Steps

- [Configuration Guide](configuration.md) - Deep dive into configuration
- [User Guide](../user-guide/index.md) - Complete usage reference
- [CLI Reference](../user-guide/cli-reference.md) - All commands and options
- [Developer Guide](../developer-guide/index.md) - If you want to contribute

## Common Commands

| Command | Description |
|---------|-------------|
| `secondbrain --help` | Show all commands |
| `secondbrain ingest --help` | Ingest options |
| `secondbrain search --help` | Search options |
| `secondbrain health` | Check system health |
| `secondbrain status` | Database statistics |
