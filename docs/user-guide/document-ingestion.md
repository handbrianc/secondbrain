# Document Ingestion

Learn how to ingest documents into SecondBrain.

## Supported Formats

SecondBrain supports a wide range of document formats:

### Text Documents
- **PDF** (.pdf) - Portable Document Format
- **Word** (.docx) - Microsoft Word documents
- **PowerPoint** (.pptx) - Microsoft PowerPoint presentations
- **Excel** (.xlsx) - Microsoft Excel spreadsheets
- **HTML** (.html, .htm) - Web pages
- **Markdown** (.md) - Markdown files
- **Text** (.txt) - Plain text files

### Media Files
- **Images** (.jpg, .png, .tiff) - Requires OCR
- **Audio** (.mp3, .wav) - Requires transcription

## Basic Ingestion

### Ingest a Directory

```bash
secondbrain ingest ./documents/
```

This will recursively process all supported files in the directory.

### Ingest a Single File

```bash
secondbrain ingest report.pdf
```

## Advanced Options

### Custom Chunking

Adjust chunk size and overlap for your document type:

```bash
# For long technical documents
secondbrain ingest ./papers/ --chunk-size 8192 --chunk-overlap 200

# For short documents
secondbrain ingest ./notes/ --chunk-size 1024 --chunk-overlap 50
```

### Batch Processing

Process multiple documents in parallel:

```bash
# Process 10 documents at a time
secondbrain ingest ./documents/ --batch-size 10
```

### Verbose Mode

Get detailed progress and timing information:

```bash
secondbrain ingest ./documents/ --verbose
```

## Chunking Strategy

### How Chunking Works

1. Documents are split into chunks based on `chunk_size`
2. Chunks overlap by `chunk_overlap` tokens for context
3. Each chunk is embedded separately
4. Metadata is preserved for each chunk

### Choosing Chunk Size

| Document Type | Recommended Chunk Size |
|--------------|------------------------|
| Short notes | 512-1024 tokens |
| Articles | 2048-4096 tokens |
| Technical docs | 4096-8192 tokens |
| Books/Papers | 8192+ tokens |

### Choosing Chunk Overlap

| Use Case | Recommended Overlap |
|----------|---------------------|
| General | 50-100 tokens |
| Technical | 100-200 tokens |
| Narrative | 200-500 tokens |

## Processing Pipeline

```
File → Text Extraction → Chunking → Embedding → Storage
```

### Step 1: Text Extraction

- PDF: Extract text and metadata
- DOCX: Extract text, headings, and structure
- HTML: Strip tags and extract content
- Images: OCR (if enabled)
- Audio: Transcription (if enabled)

### Step 2: Chunking

- Split text into overlapping chunks
- Preserve document metadata
- Generate unique chunk IDs

### Step 3: Embedding

- Send chunks to Ollama
- Generate vector embeddings
- Apply rate limiting

### Step 4: Storage

- Store vectors in MongoDB
- Index for fast retrieval
- Preserve metadata

## Duplicate Detection

SecondBrain automatically detects duplicate documents using:

1. Text hashing
2. Content comparison
3. Metadata matching

Duplicates are skipped with a warning.

## Error Handling

### Common Errors

**File too large:**
```
Error: File exceeds maximum size (100MB)
```
**Solution:** Split file or increase `SECONDBRAIN_MAX_FILE_SIZE_BYTES`

**Unsupported format:**
```
Error: Unsupported file format: .xyz
```
**Solution:** Convert to supported format

**OCR required:**
```
Warning: Image file requires OCR configuration
```
**Solution:** Configure OCR engine or skip image files

## Performance Tips

1. **Use batch processing** for large directories
2. **Adjust chunk size** for your document type
3. **Enable verbose mode** to monitor progress
4. **Use parallel processing** with `--batch-size`

## Programmatic Ingestion

For Python API usage:

```python
from secondbrain.client import SecondBrainClient

client = SecondBrainClient()

# Ingest directory
client.ingest("./documents/")

# Ingest with custom options
client.ingest(
    "./papers/",
    chunk_size=2048,
    chunk_overlap=100,
    batch_size=10
)
```

See [Async API Guide](../developer-guide/async-api.md) for async examples.

## Related Documentation

- [Quick Start](../getting-started/quick-start.md) - Get started
- [Configuration](../getting-started/configuration.md) - Chunk settings
- [Search Guide](./search-guide.md) - Search ingested documents