# Document Management

Manage your document collection in SecondBrain.

## List Documents

### Basic List

```bash
# List all documents
secondbrain list
```

### Detailed View

```bash
# Show metadata
secondbrain list --verbose
```

### Filter

```bash
# By collection
secondbrain list --collection "research"

# By format
secondbrain list --format pdf
```

## View Document

### Get Details

```bash
# View document info
secondbrain info <document-id>
```

### View Content

```bash
# Show document content
secondbrain info <document-id> --show-content
```

## Delete Documents

### Single Document

```bash
# Delete by ID
secondbrain delete <document-id>

# Confirm deletion
secondbrain delete <document-id> --confirm
```

### Multiple Documents

```bash
# Delete by collection
secondbrain delete --collection "old-docs" --confirm-all

# Delete by pattern
secondbrain delete --pattern "*.tmp" --confirm-all
```

## Collections

### Create Collection

```bash
# Documents are automatically organized
# Create custom collection
secondbrain ingest doc.pdf --collection "my-collection"
```

### List Collections

```bash
# Show all collections
secondbrain collections list
```

### Manage Collection

```bash
# Add to collection
secondbrain collection add <doc-id> --collection "name"

# Remove from collection
secondbrain collection remove <doc-id> --collection "name"
```

## Export

### Export All

```bash
# Export to JSON
secondbrain export --format json --output all-documents.json

# Export to CSV
secondbrain export --format csv --output documents.csv
```

### Export Collection

```bash
# Export specific collection
secondbrain export --collection "research" --format json --output research.json
```

### Export with Content

```bash
# Include full content
secondbrain export --format json --output docs.json --include-content
```

## Import

### Import JSON

```bash
# Import from export
secondbrain import --input documents.json
```

### Import with Options

```bash
# Specify collection
secondbrain import --input docs.json --collection "imported"
```

## Statistics

### Collection Stats

```bash
# Show statistics
secondbrain stats
```

### Document Count

```bash
# Count documents
secondbrain stats --count
```

### Storage Usage

```bash
# Show storage usage
secondbrain stats --storage
```

## Troubleshooting

### Document Not Found

**Solution**: Verify document ID with `secondbrain list`

### Delete Permission Denied

**Solution**: Use `--confirm` flag to confirm deletion

### Export Fails

**Solutions**:
1. Check output directory exists
2. Verify write permissions
3. Check disk space

## See Also

- [Document Ingestion](document-ingestion.md)
- [Search Guide](search-guide.md)
- [CLI Reference](cli-reference.md)
