# Document Ingestion

Learn how to add documents to SecondBrain.

## Supported Formats

- PDF (.pdf)
- Word (.docx)
- Text (.txt)
- Markdown (.md)
- And more via Docling

## Basic Ingestion

### Single File

```bash
secondbrain ingest document.pdf
```

### Multiple Files

```bash
secondbrain ingest doc1.pdf doc2.pdf doc3.txt
```

### Directory

```bash
# Non-recursive
secondbrain ingest ./documents/

# Recursive (all subdirectories)
secondbrain ingest ./documents/ --recursive
```

## Advanced Options

### Custom Chunking

```bash
# Smaller chunks
secondbrain ingest document.pdf --chunk-size 250 --chunk-overlap 25

# Larger chunks
secondbrain ingest document.pdf --chunk-size 1000 --chunk-overlap 100
```

### Metadata

```bash
# Add custom metadata
secondbrain ingest document.pdf --metadata '{"author": "John", "tags": ["research"]}'
```

### Collection

```bash
# Add to collection
secondbrain ingest document.pdf --collection "research-papers"
```

## Batch Ingestion

### Ingest Entire Library

```bash
secondbrain ingest ./library/ --recursive --batch-size 100
```

### Progress Tracking

```bash
secondbrain ingest ./documents/ --verbose
```

## Best Practices

### Document Preparation

1. Use clean, well-structured documents
2. Remove unnecessary formatting
3. Ensure text is selectable (not scanned images)

### Chunking Strategy

- **Small chunks** (250-500): Better for precise queries
- **Large chunks** (500-1000): Better for context understanding
- **Overlap** (50-100): Helps maintain context across chunks

### Metadata

Add useful metadata for filtering:
- Author
- Date
- Tags
- Source

## Troubleshooting

### File Not Supported

**Solution**: Check format is supported. Convert unsupported formats to PDF or TXT.

### Parsing Errors

**Solution**: Ensure file is not corrupted. Try opening in native application.

### Slow Ingestion

**Solutions**:
- Enable GPU acceleration
- Increase batch size
- Use multiple workers

## See Also

- [Search Guide](search-guide.md)
- [Document Management](document-management.md)
- [Examples](../examples/README.md)
