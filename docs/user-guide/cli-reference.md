# CLI Reference

Complete command reference for SecondBrain CLI.

## Commands

### secondbrain

Main CLI entry point.

```bash
secondbrain [OPTIONS] COMMAND [ARGS]
```

### secondbrain ingest

Ingest documents into the knowledge base.

```bash
secondbrain ingest PATHS... [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--recursive, -r` | Process directories recursively | False |
| `--chunk-size` | Chunk size in tokens | 500 |
| `--chunk-overlap` | Overlap between chunks | 50 |
| `--collection` | Add to collection | - |
| `--metadata` | Custom metadata (JSON) | - |
| `--verbose, -v` | Verbose output | False |

**Examples:**

```bash
# Ingest single file
secondbrain ingest document.pdf

# Ingest directory recursively
secondbrain ingest ./docs/ --recursive

# Custom chunking
secondbrain ingest doc.pdf --chunk-size 250 --chunk-overlap 25
```

### secondbrain search

Search documents semantically.

```bash
secondbrain search QUERY [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--limit, -l` | Max results | 10 |
| `--format, -f` | Output format (text/json/csv) | text |
| `--collection` | Filter by collection | - |
| `--output, -o` | Output file | - |
| `--verbose, -v` | Verbose output | False |

**Examples:**

```bash
# Basic search
secondbrain search "machine learning"

# JSON output
secondbrain search "neural networks" --format json

# Export results
secondbrain search "AI" --limit 20 --output results.json
```

### secondbrain list

List all documents.

```bash
secondbrain list [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--verbose, -v` | Show details | False |
| `--collection` | Filter by collection | - |
| `--format, -f` | Output format | table |

**Examples:**

```bash
# List all
secondbrain list

# Detailed view
secondbrain list --verbose

# By collection
secondbrain list --collection "research"
```

### secondbrain info

Get document information.

```bash
secondbrain info DOCUMENT_ID [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--show-content` | Show document content | False |

**Examples:**

```bash
# Get info
secondbrain info doc-123

# Show content
secondbrain info doc-123 --show-content
```

### secondbrain delete

Delete documents.

```bash
secondbrain delete DOCUMENT_ID [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--confirm` | Confirm deletion | False |
| `--collection` | Delete by collection | - |
| `--pattern` | Delete by pattern | - |

**Examples:**

```bash
# Delete single
secondbrain delete doc-123 --confirm

# Delete collection
secondbrain delete --collection "temp" --confirm-all
```

### secondbrain export

Export documents.

```bash
secondbrain export [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--format, -f` | Output format | json |
| `--output, -o` | Output file | - |
| `--collection` | Export collection | - |
| `--include-content` | Include content | False |

**Examples:**

```bash
# Export all
secondbrain export --format json --output docs.json

# Export collection
secondbrain export --collection "research" --output research.json
```

### secondbrain import

Import documents.

```bash
secondbrain import --input FILE [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--input, -i` | Input file | Required |
| `--collection` | Import to collection | - |

**Examples:**

```bash
# Import
secondbrain import --input docs.json
```

### secondbrain collections

Manage collections.

```bash
secondbrain collections COMMAND [ARGS]
```

**Subcommands:**

- `list` - List all collections
- `add` - Add document to collection
- `remove` - Remove document from collection

### secondbrain config

Manage configuration.

```bash
secondbrain config [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--validate` | Validate configuration |
| `--show` | Show current config |

### secondbrain health-check

Check system health.

```bash
secondbrain health-check
```

## Global Options

| Option | Description |
|--------|-------------|
| `--version` | Show version |
| `--help, -h` | Show help |
| `--verbose, -v` | Verbose output |
| `--quiet, -q` | Quiet mode |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Connection error |
| 4 | Document not found |

## See Also

- [Getting Started](../getting-started/index.md)
- [User Guide](index.md)
- [Configuration](../getting-started/configuration.md)
