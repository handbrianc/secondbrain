# Quick Start Guide

Get up and running with SecondBrain in 5 minutes.

## Step 1: Installation

```bash
# Production
pip install -e "."

# Development
pip install -e ".[dev]"

# Start services (Docker)
docker-compose up -d

# Alternative: Start sentence-transformers locally
# sentence-transformers serve
```

> **Choose Your Installation Profile**: See [Dependency Installation Guide](DEPENDENCIES.md) for detailed options and external service requirements.

## Step 2: Configure

Create a `.env` file in your project root:

```bash
# MongoDB
MONGODB_INITDB_ROOT_USERNAME=your_username
MONGODB_INITDB_ROOT_PASSWORD=your_strong_password
SECONDBRAIN_MONGO_URI=mongodb://your_username:your_strong_password@localhost:27017

# Sentence Transformers
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:11434
SECONDBRAIN_LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2

# Chunk size
SECONDBRAIN_CHUNK_SIZE=4096
```

**⚠️ Security Note**: Enable MongoDB authentication for production use. See [MongoDB Authentication Setup](mongodb-authentication.md) for detailed setup instructions.

## Step 3: Ingest Documents

```bash
secondbrain ingest /path/to/documents/

# Custom options
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
secondbrain search "what is this about?"

# Limit results
secondbrain search "machine learning" --top-k 10

# Verbose output
secondbrain search "data pipelines" --verbose
```

## Step 5: Manage Documents

```bash
secondbrain ls
secondbrain ls --details

# Delete a document
secondbrain delete <document-id>

# Check database status
secondbrain status
```

## Example Workflow

```bash
secondbrain ingest ./research-papers/
secondbrain search "neural network architectures"
secondbrain ls --details
secondbrain delete doc-12345
```

## Async API (Advanced)

For programmatic usage:

```python
import asyncio
from secondbrain.client import SecondBrainClient

async def main():
    client = SecondBrainClient()
    
    await client.ingest("./documents/")
    results = await client.search("semantic query")
    for result in results:
        print(result)
    
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
