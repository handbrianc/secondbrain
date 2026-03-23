# User Guide

Comprehensive usage guide for SecondBrain.

## Overview

This section covers how to use SecondBrain for common tasks:

- [CLI Commands](cli-reference.md) - All available commands
- [Document Ingestion](document-ingestion.md) - Adding documents
- [Semantic Search](search-guide.md) - Finding documents
- [Document Management](document-management.md) - Listing and deleting
- [Conversational Q&A](conversational-qa.md) - Multi-turn conversations

## Quick Navigation

### Common Tasks

| Task | Command | Guide |
|------|---------|-------|
| Add documents | `secondbrain ingest` | [Ingestion Guide](document-ingestion.md) |
| Search | `secondbrain search` | [Search Guide](search-guide.md) |
| Chat with docs | `secondbrain chat` | [Conversational Q&A](conversational-qa.md) |
| List documents | `secondbrain ls` | [Document Management](document-management.md) |
| Delete documents | `secondbrain delete` | [Document Management](document-management.md) |
| Check health | `secondbrain health` | [CLI Reference](cli-reference.md) |

### Document Formats

SecondBrain supports:

**Documents:**
- PDF (.pdf)
- Word (.docx)
- PowerPoint (.pptx)
- Excel (.xlsx)

**Web & Text:**
- HTML (.html, .htm)
- Markdown (.md)
- Text (.txt)

**Media (requires additional setup):**
- Images (.png, .jpg, .jpeg) - OCR for text extraction
- Audio (.wav, .mp3) - Transcription to text

See [Document Ingestion](document-ingestion.md) for format-specific details.

## Core Workflows

### 1. Ingesting Documents

```bash
# Ingest a single file
secondbrain ingest document.pdf

# Ingest a directory
secondbrain ingest ./documents/

# Ingest with custom settings
secondbrain ingest ./docs/ --chunk-size 2048 --cores 4
```

### 2. Searching Documents

```bash
# Simple semantic search
secondbrain search "machine learning best practices"

# Limit results
secondbrain search "error handling" --top-k 10

# High-confidence results only
secondbrain search "data pipeline" --threshold 0.8
```

### 3. Interactive Chat

```bash
# Start interactive chat
secondbrain chat

# Single query
secondbrain chat "What is the architecture?"

# With session management
secondbrain chat --session research-project
```

### 4. Managing Documents

```bash
# List all documents
secondbrain ls

# List with full details
secondbrain ls --details

# Filter by file type
secondbrain ls --file-type pdf

# Delete a document
secondbrain delete <document-id>
```

## Advanced Topics

### Async API

For programmatic usage in Python:

```python
import asyncio
from secondbrain.client import SecondBrainClient

async def main():
    client = SecondBrainClient()
    
    # Ingest documents
    await client.ingest("./documents/")
    
    # Search
    results = await client.search("semantic query")
    
    await client.close()

asyncio.run(main())
```

See [Async Guide](../developer-guide/async-api.md) for details.

### Configuration

All CLI options can be set via environment variables:

```bash
SECONDBRAIN_CHUNK_SIZE=2048 secondbrain ingest ./docs/
```

See [Configuration Guide](../getting-started/configuration.md) for complete options.

### Examples

Practical examples are available in the [examples directory](../examples/README.md):

- **Basic Usage**: Simple CLI-style examples
- **Advanced**: Custom chunking, batch processing, async workflows
- **Integrations**: Flask and FastAPI REST APIs

## Related Documentation

- [Getting Started](../getting-started/index.md) - New users
- [CLI Reference](cli-reference.md) - Command details
- [Configuration](../getting-started/configuration.md) - Setup options
- [Developer Guide](../developer-guide/index.md) - For contributors
- [Troubleshooting](../getting-started/troubleshooting.md) - Common issues
