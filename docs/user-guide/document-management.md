# Document Management Guide

Managing ingested documents and chunks in SecondBrain.

## Listing Documents

### Basic Listing

List first 100 documents:

```bash
secondbrain ls
```

### Pagination

Control result sets with limit and offset:

```bash
# First 50 documents
secondbrain ls --limit 50

# Next 50 documents
secondbrain ls --limit 50 --offset 50
```

### List All Documents

Retrieve entire corpus:

```bash
secondbrain ls --all
```

Note: The `--all` flag ignores the `--limit` parameter and respects the internal `MAX_LIST_LIMIT`.

### Filtering

#### By Source File

View all chunks from a specific document:

```bash
secondbrain ls --source "./annual_report.pdf"
```

Useful for reviewing all pieces of a single file.

#### By Chunk ID

Retrieve specific chunk details:

```bash
secondbrain ls --chunk-id "abc123xyz"
```

Useful for debugging or referencing specific content sections.

### Understanding the Output

Listed results display:

| Field | Description |
|-------|-------------|
| `chunk_id` | Unique identifier for the chunk |
| `source` | Original file path |
| `page` | Source page number |
| `text_preview` | Beginning of chunk content |
| `created_at` | Ingestion timestamp |

## Deleting Documents

### Safety First

Deletion is **permanent**. There is no recycle bin or undo functionality.

Always preview before deleting:

```bash
# Preview what will be deleted
secondbrain ls --source "./old_document.pdf"
```

### Deletion Criteria

Choose one criterion per operation:

| Criterion | Flag | Use Case |
|-----------|------|----------|
| Source file | `--source` | Remove all chunks from a file |
| Specific chunk | `--chunk-id` | Remove single chunk |
| Everything | `--all` | Complete database reset |

### By Source

Remove all chunks originating from a file:

```bash
secondbrain delete --source "./report_q4_2024.pdf"
```

Prompts for confirmation unless `--yes` is provided.

### By Chunk ID

Target a specific chunk:

```bash
secondbrain delete --chunk-id "unique-chunk-identifier"
```

Useful for removing corrupted or obsolete entries.

### Delete Everything

Clear the entire vector store:

```bash
# With confirmation prompt
secondbrain delete --all

# Skip confirmation
secondbrain delete --all --yes
```

### Confirmation Patterns

```bash
# Default: requires Y/n response
secondbrain delete --source "./file.pdf"
# Output: Delete documents matching criteria? [y/N]:

# Skip with --yes flag
secondbrain delete --source "./file.pdf" --yes
# Executes immediately
```

## Viewing Statistics

### Database Status

Get overall vector store statistics:

```bash
secondbrain status
```

Reports include:

| Statistic | Description |
|-----------|-------------|
| Total chunks | Overall document count |
| Sources | Unique source files |
| Storage size | MongoDB collection size |
| Index status | Vector index health |
| Chunk distribution | Sizes across corpus |

### Service Health

Check MongoDB and embedding service connectivity:

```bash
secondbrain health
```

Health status indicates whether all required services are operational.

### Performance Metrics

View operation latencies:

```bash
secondbrain metrics
```

Metrics tracked:

- `embedding_generate` / `_async` - Synchronous and async embedding creation
- `storage_store` / `_batch` - Individual and bulk vector storage
- `storage_search` - Query execution latency

### Reset Metrics

Clear all collected metrics:

```bash
secondbrain metrics --reset
```

Useful for measuring specific operation windows.

## Bulk Operations

### Inventory Export

Generate complete document inventory:

```bash
secondbrain ls --all > inventory_$(date +%Y%m%d).txt
```

### Selective Cleanup

Remove documents older than a pattern:

```bash
# List all sources
secondbrain ls --all | grep "2023" | awk '{print $2}' | sort -u

# Pipe to delete (careful!)
secondbrain ls --all | grep "2023" | awk '{print $2}' | sort -u | \
  while read src; do
    secondbrain delete --source "$src" --yes
  done
```

### Archive and Reset

Archive current corpus:

```bash
# Export metadata
secondbrain ls --all > archive_metadata.txt

# Note: Actual content cannot be recovered without re-ingesting
```

## Common Tasks

### Remove Duplicate File Entry

When a file was ingested twice:

```bash
# Identify duplicates
secondbrain ls --source "./document.pdf" | wc -l

# Remove all instances
secondbrain delete --source "./document.pdf"
```

### Preserve Specific Source

Delete everything except one document:

```bash
# Step 1: Note current sources
secondbrain ls --all > all_sources.txt

# Step 2: Delete all
secondbrain delete --all --yes

# Step 3: Re-ingest preserved file
secondbrain ingest ./preserved_document.pdf
```

### Migrate to New Database

Transfer corpus to different MongoDB instance:

1. Dump original:

```bash
mongodump --uri="$MONGO_URI" --collection=embeddings
```

2. Restore to target:

```bash
mongorestore --uri="$NEW_MONGO_URI" dump/embeddings.bson
```

3. Update configuration:

```bash
export SECONDBRAIN_MONGO_URI="$NEW_MONGO_URI"
```