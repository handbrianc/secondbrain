# Document Management

Manage your ingested documents in SecondBrain.

## Listing Documents

### List All Documents

```bash
secondbrain list
```

Shows a summary of all ingested documents.

### List with Details

```bash
secondbrain list --details
```

Shows detailed information including:
- Document ID
- Source file path
- Number of chunks
- Ingestion timestamp
- File type

## Deleting Documents

### Delete Single Document

```bash
secondbrain delete <document-id>
```

You'll be prompted to confirm before deletion.

### Delete Without Confirmation

```bash
secondbrain delete <document-id> --force
```

### Delete Multiple Documents

```bash
# Delete each one individually
secondbrain delete doc-12345
secondbrain delete doc-67890
```

## Viewing Document Status

### Database Statistics

```bash
secondbrain status
```

Shows:
- Total documents
- Total chunks
- Database size
- Index statistics

### Health Check

```bash
secondbrain health
```

Verifies:
- MongoDB connectivity
- sentence-transformers availability
- Configuration validity

## Organizing Documents

### Best Practices

1. **Use descriptive file names** - Easier to identify documents
2. **Group by project** - Organize into directories
3. **Use consistent formats** - Prefer PDF/DOCX over images
4. **Regular cleanup** - Remove outdated documents

### Document Naming

Recommended naming convention:
```
project-name_document-type_date.pdf
example-project_report_2024-03-01.pdf
```

## Batch Operations

### Process Multiple Directories

```bash
# Ingest multiple directories
secondbrain ingest ./project-a/
secondbrain ingest ./project-b/
```

### Batch Deletion Script

```bash
#!/bin/bash
# delete-old-docs.sh

# List documents older than X days and delete
secondbrain list --details | grep "2024-01" | awk '{print $1}' | while read id; do
    secondbrain delete $id --force
done
```

## Monitoring

### Verbose Ingestion

```bash
secondbrain ingest ./documents/ --verbose
```

Shows progress and timing for each document.

### Check Progress

```bash
# Monitor database growth
secondbrain status
```

## Troubleshooting

### Document Not Found

**Problem:** Can't find a document in search results

**Solutions:**
1. Verify it was ingested: `secondbrain list`
2. Check ingestion logs for errors
3. Re-ingest if necessary

### Duplicate Documents

**Problem:** Same document appears multiple times

**Solutions:**
1. SecondBrain has built-in duplicate detection
2. Check if files have different metadata
3. Delete duplicates manually

### Corrupted Documents

**Problem:** Document shows errors

**Solutions:**
1. Delete and re-ingest
2. Check file integrity
3. Try converting to different format

## Related Documentation

- [Document Ingestion](./document-ingestion.md) - Add documents
- [Search Guide](./search-guide.md) - Search documents
- [CLI Reference](./cli-reference.md) - All commands