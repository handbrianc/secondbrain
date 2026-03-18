# CLI Reference

Complete reference for SecondBrain CLI commands.

## Overview

SecondBrain provides a comprehensive CLI for document management and semantic search.

## Commands

### `ingest`

Add documents to the vector database.

```bash
secondbrain ingest PATH [OPTIONS]
```

**Options:**
- `PATH` - Path to file or directory (required)
- `--chunk-size INTEGER` - Chunk size in tokens (default: 4096)
- `--chunk-overlap INTEGER` - Chunk overlap in tokens (default: 50)
- `--batch-size INTEGER` - Batch size for parallel processing
- `--verbose` - Enable verbose output with timing info
- `--help` - Show help message

**Examples:**
```bash
# Ingest a single file
secondbrain ingest document.pdf

# Ingest a directory
secondbrain ingest ./documents/

# Custom chunking
secondbrain ingest ./papers/ --chunk-size 2048 --chunk-overlap 100

# Batch processing with verbose output
secondbrain ingest ./reports/ --batch-size 10 --verbose
```

**Supported Formats:**
- PDF (.pdf)
- Word (.docx)
- PowerPoint (.pptx)
- Excel (.xlsx)
- HTML (.html, .htm)
- Markdown (.md)
- Text (.txt)
- Images (OCR required)
- Audio (transcription required)

### `search`

Perform semantic search queries.

```bash
secondbrain search QUERY [OPTIONS]
```

**Options:**
- `QUERY` - Search query in natural language (required)
- `--top-k INTEGER` - Number of results to return (default: 5)
- `--verbose` - Enable verbose output with scores
- `--help` - Show help message

**Examples:**
```bash
# Simple search
secondbrain search "what is this about?"

# Get more results
secondbrain search "machine learning algorithms" --top-k 10

# Verbose output with scores
secondbrain search "data processing pipelines" --verbose
```

### `list`

List ingested documents.

```bash
secondbrain list [OPTIONS]
```

**Options:**
- `--details` - Show detailed information including chunks
- `--help` - Show help message

**Examples:**
```bash
# List all documents
secondbrain list

# Show detailed information
secondbrain list --details
```

### `delete`

Remove documents from the database.

```bash
secondbrain delete DOCUMENT_ID [OPTIONS]
```

**Options:**
- `DOCUMENT_ID` - ID of document to delete (required)
- `--force` - Skip confirmation prompt
- `--help` - Show help message

**Examples:**
```bash
# Delete with confirmation
secondbrain delete doc-12345

# Delete without confirmation
secondbrain delete doc-12345 --force
```

### `status`

Display database statistics.

```bash
secondbrain status [OPTIONS]
```

**Output:**
- Total documents
- Total chunks
- Database size
- Index statistics

### `health`

Check service health.

```bash
secondbrain health [OPTIONS]
```

**Checks:**
- MongoDB connectivity
- sentence-transformers availability
- Configuration validity

## Global Options

- `--version` - Show version
- `--verbose` - Enable verbose output
- `--help` - Show help message

## Exit Codes

- `0` - Success
- `1` - General error
- `2` - Configuration error
- `3` - Service unavailable

## Related Documentation

- [Quick Start](../getting-started/quick-start.md) - Get started quickly
- [User Guide](../user-guide/index.md) - Complete usage guide
- [Configuration](../getting-started/configuration.md) - Setup options