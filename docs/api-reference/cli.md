# CLI Reference

Complete command-line interface reference for SecondBrain.

## Overview

SecondBrain provides a Click-based CLI with the following commands:

| Command | Description |
|---------|-------------|
| `ingest` | Add documents to the vector database |
| `search` | Perform semantic search queries |
| `list` | List ingested documents/chunks |
| `delete` | Remove documents |
| `status` | Display database statistics |
| `health` | Check service health |

## Main Entry Point

::: secondbrain.cli
    options:
        members:
            - main
            - cli
            - handle_cli_errors

## Commands

### `ingest`

Add documents to the vector database.

```bash
secondbrain ingest PATH [OPTIONS]
```

**Options:**
- `--chunk-size INTEGER` - Chunk size in tokens (default: 4096)
- `--chunk-overlap INTEGER` - Chunk overlap in tokens (default: 50)
- `--batch-size INTEGER` - Batch size for parallel processing
- `--verbose` - Enable verbose output
- `--help` - Show help message

**Examples:**
```bash
# Ingest a directory
secondbrain ingest ./documents/

# Ingest with custom chunking
secondbrain ingest ./papers/ --chunk-size 2048

# Verbose batch processing
secondbrain ingest ./reports/ --batch-size 10 --verbose
```

### `search`

Perform semantic search queries.

```bash
secondbrain search QUERY [OPTIONS]
```

**Options:**
- `--top-k INTEGER` - Number of results to return (default: 5)
- `--verbose` - Enable verbose output
- `--help` - Show help message

**Examples:**
```bash
# Simple search
secondbrain search "what is this about?"

# Get more results
secondbrain search "machine learning" --top-k 10

# Verbose output
secondbrain search "data pipelines" --verbose
```

### `list`

List ingested documents.

```bash
secondbrain list [OPTIONS]
```

**Options:**
- `--details` - Show detailed information
- `--help` - Show help message

### `delete`

Remove documents from the database.

```bash
secondbrain delete DOCUMENT_ID [OPTIONS]
```

**Options:**
- `--force` - Skip confirmation prompt
- `--help` - Show help message

### `status`

Display database statistics.

```bash
secondbrain status [OPTIONS]
```

### `health`

Check service health.

```bash
secondbrain health [OPTIONS]
```

## Related Documentation

- [Quick Start](../getting-started/quick-start.md) - Get started quickly
- [User Guide](../user-guide/index.md) - Complete usage guide
- [Configuration](../getting-started/configuration.md) - Setup options

## Related Documentation

- [User Guide](../user-guide/index.md) - Usage guide
- [Getting Started](../getting-started/quick-start.md) - Quick start
- [Configuration](../getting-started/configuration.md) - Configuration guide
