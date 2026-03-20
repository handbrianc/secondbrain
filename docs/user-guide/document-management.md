# Document Management Guide

Learn how to manage your document database with SecondBrain.

## Listing Documents

### Basic List

```bash
# Show all documents (summary)
secondbrain list
```

Output:
```
ID                                    Filename          Size    Chunks
-------------------------------------------------------------------
doc-a1b2c3d4e5f6                      report.pdf        45KB    12
doc-b2c3d4e5f6g7                      notes.md          8KB     3
doc-c3d4e5f6g7h8                      presentation.pptx 120KB   28
```

### Detailed List

```bash
# Show full document details
secondbrain list --details
```

Output:
```
ID: doc-a1b2c3d4e5f6
Filename: report.pdf
Size: 45KB
Chunks: 12
Type: pdf
Ingested: 2024-01-15 14:30:22
Metadata:
  author: John Doe
  department: Engineering
```

### Filter by File Type

```bash
# List only PDF documents
secondbrain list --file-type pdf

# List only markdown files
secondbrain list --file-type md
```

### Limit Results

```bash
# Show only recent documents
secondbrain list --limit 10

# Combine with details
secondbrain list --details --limit 5
```

### JSON Output

```bash
# Export document list as JSON
secondbrain list --format json
```

## Database Statistics

### Status Command

```bash
# View database statistics
secondbrain status
```

Output:
```
Database: secondbrain
Collection: embeddings
Total Documents: 150
Total Chunks: 2,340
Total Content Size: 45.2 MB
Vector Index Size: 12.8 MB
Average Chunk Size: 19,316 characters
```

### Verbose Status

```bash
# Detailed statistics
secondbrain status --verbose
```

Includes:
- Breakdown by file type
- Ingestion timeline
- Search performance metrics
- Index health

## Deleting Documents

### Delete Single Document

```bash
# Delete by ID
secondbrain delete doc-a1b2c3d4e5f6
```

You'll be prompted to confirm:
```
Delete document doc-a1b2c3d4e5f6 (report.pdf)? [y/N]: y
✓ Document deleted successfully
```

### Force Delete (Skip Confirmation)

```bash
# Delete without confirmation
secondbrain delete doc-a1b2c3d4e5f6 --force
```

### Delete All Documents

```bash
# WARNING: Delete all documents
secondbrain delete --all --force
```

**Warning**: This action cannot be undone!

### Batch Delete

```bash
# Delete multiple documents (manual)
secondbrain delete doc-1 --force
secondbrain delete doc-2 --force
secondbrain delete doc-3 --force
```

## Document Metadata

### Viewing Metadata

```bash
# See metadata for all documents
secondbrain list --details | grep -A 5 "Metadata:"
```

### Metadata Fields

Documents can have custom metadata:
- `filename`: Original file name
- `file_type`: Extension (pdf, md, etc.)
- `size`: File size in bytes
- `ingested_at`: Timestamp
- `custom fields`: Any user-defined metadata

## Maintenance

### Find Orphaned Chunks

```bash
# Check for database inconsistencies
secondbrain status --verbose
```

### Rebuild Index

```bash
# Re-ingest all documents to rebuild
secondbrain ingest ./documents/ --force
```

### Backup Database

```bash
# MongoDB backup
mongodump --db secondbrain --out ./backup/

# Restore from backup
mongorestore --db secondbrain ./backup/secondbrain/
```

## Search Within Results

### Filter by Content

After listing documents, you can search within specific files:

```bash
# First, get document ID
secondbrain list --file-type pdf

# Then search with context
secondbrain search "specific topic" --top-k 10
```

### Cross-Reference Documents

```bash
# Find related documents
secondbrain search "topic A" --top-k 5
secondbrain search "topic B" --top-k 5

# Compare results to find overlap
```

## Best Practices

### Regular Maintenance

```bash
# Weekly: Check database health
secondbrain status

# Monthly: Review and clean up
secondbrain list --details
```

### Document Organization

```bash
# Ingest by category
secondbrain ingest ./documents/research/
secondbrain ingest ./documents/projects/

# Keep track with metadata
```

### Version Control

For important documents:
1. Keep source files in version control
2. Track document IDs externally
3. Document ingestion history

## Troubleshooting

### Document Not Found

```bash
# Verify document exists
secondbrain list | grep "doc-id"

# Check for typos in ID
secondbrain list --details
```

### Duplicate Documents

```bash
# Re-ingest with --force to deduplicate
secondbrain ingest ./docs/ --force
```

### Missing Metadata

```bash
# Re-ingest to add missing metadata
secondbrain ingest ./docs/ --force
```

## Next Steps

- [Search Guide](search-guide.md) - Learn to query documents
- [CLI Reference](cli-reference.md) - Complete command reference
- [Troubleshooting](../getting-started/troubleshooting.md) - Common issues
