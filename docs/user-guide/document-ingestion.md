# Document Ingestion Guide

Learn how to add documents to your SecondBrain vector database.

## Supported Formats

SecondBrain supports a wide range of document formats:

### Documents
- **PDF** (.pdf) - Text extraction with layout preservation
- **Word** (.docx) - Full formatting support
- **PowerPoint** (.pptx) - Slide-by-slide extraction
- **Excel** (.xlsx) - Cell data with formatting

### Web & Text
- **HTML** (.html, .htm) - Content extraction, strips tags
- **Markdown** (.md) - Preserves structure
- **Text** (.txt) - Plain text

### Media
- **Images** (.png, .jpg, .jpeg) - OCR extraction (requires Tesseract)
- **Audio** (.wav, .mp3) - Transcription (requires Whisper)

## Basic Ingestion

### Ingest a Single File

```bash
secondbrain ingest document.pdf
```

### Ingest a Directory

```bash
secondbrain ingest ./documents/
```

All supported files in the directory will be processed recursively.

## Advanced Options

### Chunk Configuration

Documents are split into chunks for embedding:

```bash
# Smaller chunks for better precision
secondbrain ingest ./docs/ --chunk-size 1024 --chunk-overlap 100

# Larger chunks for better context
secondbrain ingest ./docs/ --chunk-size 8192 --chunk-overlap 500
```

| Parameter | Description | Recommended Range |
|-----------|-------------|-------------------|
| `--chunk-size` | Characters per chunk | 512 - 8192 |
| `--chunk-overlap` | Overlap between chunks | 50 - 500 |

### Performance Tuning

```bash
# Use more CPU cores (default: 4)
secondbrain ingest ./docs/ --cores 8

# Process in larger batches
secondbrain ingest ./docs/ --batch-size 20

# Disable rate limiting (development only)
SECONDBRAIN_RATE_LIMIT_ENABLED=false secondbrain ingest ./docs/
```

### Re-ingestion

By default, SecondBrain skips existing documents:

```bash
# Force re-ingestion of all documents
secondbrain ingest ./docs/ --force
```

Useful when:
- Changing chunk configuration
- Updating embedding model
- Fixing corrupted documents

## Best Practices

### Optimal Chunk Size

| Use Case | Chunk Size | Overlap |
|----------|------------|---------|
| Q&A tasks | 512-1024 | 100-200 |
| General search | 2048-4096 | 200-300 |
| Full document context | 4096-8192 | 300-500 |

### Directory Organization

```
documents/
├── research/
│   ├── papers/
│   └── notes/
├── projects/
│   ├── project-a/
│   └── project-b/
└── personal/
```

Ingest by category:
```bash
secondbrain ingest ./documents/research/ --chunk-size 2048
secondbrain ingest ./documents/projects/ --chunk-size 4096
```

### Large Datasets

For large document collections:

```bash
# Process in stages
secondbrain ingest ./docs/part1/ --cores 8
secondbrain ingest ./docs/part2/ --cores 8

# Monitor progress
secondbrain status
```

## Monitoring Progress

### Verbose Mode

```bash
secondbrain ingest ./docs/ --verbose
```

Output:
```
Processing: document1.pdf (45KB)
  - Extracted 12,345 characters
  - Created 4 chunks
  - Generated embeddings
  ✓ Complete (2.3s)

Processing: document2.docx (89KB)
  ...
```

### Progress Tracking

```bash
# Check ingestion status
secondbrain status

# List recently added documents
secondbrain list --limit 10
```

## Error Handling

### Failed Documents

If a document fails to process:

```bash
# Continue processing other documents
secondbrain ingest ./docs/  # Skips failed files

# See detailed errors
secondbrain ingest ./docs/ --verbose
```

Common errors:
- **Corrupted file**: Try repairing or re-saving
- **Unsupported format**: Convert to supported format
- **Permission denied**: Check file permissions

### Retry Strategy

```bash
# Re-ingest only failed documents
secondbrain ingest ./failed-docs/ --force
```

## Examples

### Ingest Research Papers

```bash
# Optimize for academic papers
secondbrain ingest ./papers/ \
  --chunk-size 2048 \
  --chunk-overlap 200 \
  --cores 4
```

### Ingest Project Documentation

```bash
# Larger chunks for technical docs
secondbrain ingest ./project-docs/ \
  --chunk-size 4096 \
  --chunk-overlap 300 \
  --batch-size 15
```

### Continuous Ingestion

```bash
# Watch directory for new files (requires watchman)
watchman watch ./documents/
# Then run ingestion periodically
while true; do
  secondbrain ingest ./documents/
  sleep 3600  # Every hour
done
```

## Next Steps

- [Search Guide](search-guide.md) - Learn to query your documents
- [Document Management](document-management.md) - Manage your database
- [CLI Reference](cli-reference.md) - Complete command reference
