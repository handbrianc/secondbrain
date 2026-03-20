# CLI Reference

Complete reference for all SecondBrain CLI commands.

## Global Options

```bash
secondbrain [GLOBAL OPTIONS] [COMMAND] [COMMAND OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--help` | Show help message | - |
| `--version` | Show version | - |
| `--verbose` | Enable verbose output | false |
| `--config` | Path to config file | `.env` |

## Commands

### `ingest`

Ingest documents into the vector database.

```bash
secondbrain ingest PATH [OPTIONS]
```

**Arguments:**
- `PATH` - Path to file or directory to ingest

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `--chunk-size` | Size of text chunks | 4096 |
| `--chunk-overlap` | Overlap between chunks | 200 |
| `--batch-size` | Batch size for processing | 10 |
| `--cores` | Number of CPU cores | 4 |
| `--force` | Re-ingest existing documents | false |
| `--verbose` | Show detailed progress | false |

**Examples:**
```bash
# Ingest a single file
secondbrain ingest document.pdf

# Ingest a directory
secondbrain ingest ./documents/

# Ingest with custom chunk size
secondbrain ingest ./docs/ --chunk-size 2048

# Ingest with 8 CPU cores
secondbrain ingest ./docs/ --cores 8

# Force re-ingestion
secondbrain ingest ./docs/ --force
```

### `search`

Perform semantic search queries.

```bash
secondbrain search QUERY [OPTIONS]
```

**Arguments:**
- `QUERY` - Natural language search query

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `--top-k` | Number of results | 5 |
| `--threshold` | Minimum similarity score | 0.0 |
| `--fields` | Fields to return | content |
| `--verbose` | Show timing info | false |

**Examples:**
```bash
# Simple search
secondbrain search "machine learning algorithms"

# Get 10 results
secondbrain search "python best practices" --top-k 10

# High-confidence results only
secondbrain search "data pipeline" --threshold 0.8

# Include metadata in results
secondbrain search "report" --fields content,metadata
```

### `list`

List ingested documents.

```bash
secondbrain list [OPTIONS]
```

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `--details` | Show full details | false |
| `--format` | Output format (table/json) | table |
| `--file-type` | Filter by file type | - |
| `--limit` | Maximum results | 100 |

**Examples:**
```bash
# List all documents (summary)
secondbrain list

# List with full details
secondbrain list --details

# Export as JSON
secondbrain list --format json

# Filter by file type
secondbrain list --file-type pdf
```

### `delete`

Delete documents from the database.

```bash
secondbrain delete DOCUMENT_ID [OPTIONS]
```

**Arguments:**
- `DOCUMENT_ID` - ID of document to delete

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `--force` | Skip confirmation | false |
| `--all` | Delete all documents | false |

**Examples:**
```bash
# Delete a single document
secondbrain delete doc-12345

# Delete without confirmation
secondbrain delete doc-12345 --force

# Delete all documents (warning!)
secondbrain delete --all --force
```

### `status`

Show database statistics.

```bash
secondbrain status [OPTIONS]
```

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `--verbose` | Show detailed stats | false |
| `--format` | Output format | table |

**Output:**
```
Database: secondbrain
Collection: embeddings
Total Documents: 150
Total Chunks: 2,340
Total Size: 45.2 MB
Index Size: 12.8 MB
```

### `health`

Check system health and connectivity.

```bash
secondbrain health [OPTIONS]
```

**Options:**
| Option | Description | Default |
|--------|-------------|---------|
| `--verbose` | Show detailed info | false |
| `--check-sentence-transformers` | Check service | true |
| `--check-mongo` | Check MongoDB | true |

**Output:**
```
✓ MongoDB: Connected (27017)
✓ sentence-transformers: Available (11434)
✓ Configuration: Valid
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Connection error |
| 4 | Document not found |
| 5 | Permission error |

## Environment Variables

All CLI options can be set via environment variables:

| Option | Environment Variable |
|--------|---------------------|
| `--chunk-size` | `SECONDBRAIN_CHUNK_SIZE` |
| `--cores` | `SECONDBRAIN_MAX_WORKERS` |
| `--verbose` | `SECONDBRAIN_VERBOSE` |

Example:
```bash
SECONDBRAIN_CHUNK_SIZE=2048 secondbrain ingest ./docs/
```

## Help

```bash
# Show all commands
secondbrain --help

# Show command-specific help
secondbrain ingest --help
secondbrain search --help
```
