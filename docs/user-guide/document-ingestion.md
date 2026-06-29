# Document Ingestion Guide

Comprehensive guide to ingesting documents into SecondBrain's vector database.

## Overview

The `ingest` command parses supported file types, splits content into chunks, generates embeddings, and stores vectors in MongoDB.

## Supported File Types

SecondBrain supports the following document formats:

### Documents

| Format | Extensions | Notes |
|--------|------------|-------|
| PDF | `.pdf` | Text and tables extracted via Docling |
| Word | `.docx` | Full text and paragraph extraction |
| PowerPoint | `.pptx` | Slide text and bullet points |
| Excel | `.xlsx` | Tabular data preservation |
| HTML | `.html`, `.htm` | Web page content extraction |
| Markdown | `.md` | Plain text with formatting preserved |
| Plain Text | `.txt` | UTF-8 text files |
| ASCII Doc | `.asciidoc`, `.adoc` | AsciiDoctor format |
| LaTeX | `.tex` | TeX document format |
| CSV | `.csv` | Structured tabular data |
| XML | `.xml` | Markup document format |
| JSON | `.json` | Structured JSON data |

### Images (with OCR)

| Format | Extensions | OCR Engine |
|--------|------------|------------|
| PNG | `.png` | Docling/Tesseract |
| JPEG | `.jpg`, `.jpeg` | Docling/Tesseract |
| TIFF | `.tiff`, `.tif` | Docling/Tesseract |
| BMP | `.bmp` | Docling/Tesseract |
| WebP | `.webp` | Docling/Tesseract |

### Audio/Video

| Format | Extensions | Processing |
|--------|------------|------------|
| WAV | `.wav` | Transcription |
| MP3 | `.mp3` | Transcription |
| WebVTT | `.vtt` | Subtitle extraction |

## Chunking Configuration

Documents are split into overlapping chunks to enable granular retrieval.

### Default Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 4096 | Target chunk size in characters |
| `chunk_overlap` | 50 | Overlap between consecutive chunks |

### Tuning Guidelines

#### Small Chunks (< 1024 chars)

Best for: Precise fact extraction, Q&A, dense content

```bash
secondbrain ingest ./facts/ --chunk-size 512 --chunk-overlap 50
```

#### Medium Chunks (1024-2048 chars)

Best for: General purpose, balanced precision/recall

```bash
secondbrain ingest ./general/ --chunk-size 1536 --chunk-overlap 100
```

#### Large Chunks (> 2048 chars)

Best for: Preserving context, narrative content

```bash
secondbrain ingest ./books/ --chunk-size 4096 --chunk-overlap 200
```

### Chunk Size Constraints

- `chunk_overlap` must be less than `chunk_size`
- Chunk sizes are targets; actual chunks may vary slightly

## Parallel Processing

### Automatic Core Detection

By default, SecondBrain auto-detects available CPU cores:

```bash
secondbrain ingest ./large_corpus/ --recursive
```

### Manual Core Specification

Specify explicit core count:

```bash
secondbrain ingest ./papers/ --recursive --cores 4
```

### How Parallelism Works

| Cores | Behavior |
|-------|----------|
| 1 | ThreadPoolExecutor with configurable batch size |
| 2+ | Parallel file processing with progress tracking |

## Batch Processing

Control memory usage via batch sizing:

```bash
# Conservative batching
secondbrain ingest ./docs/ --batch-size 5

# Aggressive batching
secondbrain ingest ./docs/ --batch-size 50
```

Lower batch sizes reduce memory pressure; higher sizes improve throughput.

## Progressive File Selection

### Non-Recursive Mode

Ingests files directly in the specified directory:

```bash
secondbrain ingest ./documents/
# Processes: documents/file1.pdf, documents/file2.docx, ...
```

### Recursive Mode

Descends into all subdirectories:

```bash
secondbrain ingest ./documents/ --recursive
# Processes: documents/a/file1.pdf, documents/b/file2.pdf, ...
```

Files are filtered to supported extensions automatically.

## Ingestion Output

Successful ingestion reports:

```
Successfully ingested 10 files
```

Warnings for failures:

```
Failed: 2 files
```

Check logs for details on failed files.

## Performance Considerations

### Optimizing Throughput

1. **Parallel processing**: Use `--cores` for I/O-bound workloads
2. **Larger batches**: Increase `--batch-size` for faster sequential processing
3. **Disable compression**: Temporary speed boost at cost of storage

```bash
export SECONDBRAIN_TEXT_COMPRESSION_ENABLED=false
```

### Managing Memory

1. **Reduce batch size**: Lower memory footprint
2. **Streaming mode**: Enabled by default for memory efficiency

```bash
export SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE=50
```

### Network-Bound Scenarios

For remote embedding providers:

```bash
secondbrain ingest ./docs/ --batch-size 10
# Allows rate limiting adjustments between batches
```

## Incremental Ingestion

Re-running ingestion on previously processed files:

- Creates duplicate chunks if not cleaned first
- Use `delete` to remove stale entries first:

```bash
# Remove previous version
secondbrain delete --source "./updated_document.pdf"

# Re-ingest
secondbrain ingest ./updated_document.pdf
```

## Troubleshooting Ingestion

### Files Skipped Without Error

Verify the file extension is supported:

```bash
secondbrain ingest ./samples/ --recursive -v
```

### Out of Memory During Large Batch

1. Reduce batch size:

```bash
secondbrain ingest ./huge/ --batch-size 2
```

2. Process directory in smaller chunks:

```bash
mkdir /tmp/part1 /tmp/part2
mv half_of_files/* /tmp/part1/
# Process each part separately
```

### Embedding Rate Limits Exceeded

Configure rate limiting:

```bash
export SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=5
export SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0
```