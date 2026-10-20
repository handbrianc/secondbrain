# Troubleshooting Guide

Solutions for common issues encountered when running SecondBrain.

## Installation Issues

### Module Not Found Errors

**Symptom**: `ModuleNotFoundError: No module named 'secondbrain'`

**Solution**: Reinstall the package in development mode:

```bash
pip uninstall secondbrain
pip install -e .
```

### Dependency Conflicts

**Symptom**: `ERROR: Cannot install package due to conflicting dependencies`

**Solution**: Create a fresh virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -e .
```

## Qdrant Connection Issues

### Connection Refused

**Symptom**: `ConnectionRefusedError: [Errno 111] Connection refused`

**Solution**:

1. Verify Qdrant is running:

```bash
docker ps  # Look for the secondbrain-qdrant container
docker logs secondbrain-qdrant
```

1. Start Qdrant if not running:

```bash
secondbrain start --wait
```

1. Check the Qdrant URL is correct:

```bash
echo $SECONDBRAIN_QDRANT_URL
```

### Authentication Failed

**Symptom**: `AuthenticationFailed: Auth failed`

**Solution**: Verify the API key in your configuration matches your Qdrant server:

```
SECONDBRAIN_QDRANT_API_KEY=your-api-key
```

Ensure the key has the appropriate permissions on the collection.

### Database Not Ready

**Symptom**: `ConnectionError: Unable to connect to Qdrant` / collection not found

**Solution**: Wait for Qdrant to fully initialize:

```bash
secondbrain start --wait
secondbrain health
```

## Document Ingestion Issues

### Unsupported File Type

**Symptom**: `ValueError: Unsupported file type: .xyz`

**Solution**: SecondBrain supports the following formats:

```
pdf, docx, pptx, xlsx, html, htm, md, txt, asciidoc, adoc,
tex, csv, png, jpg, jpeg, tiff, tif, bmp, webp, wav, mp3,
m4a, aac, ogg, flac, vtt, xml, json
```

Consider converting your file to a supported format.

### File Too Large

**Symptom**: `ValueError: File exceeds maximum size of 100MB`

**Solution**: Split large files into smaller pieces, or adjust the limit:

```bash
export SECONDBRAIN_MAX_FILE_SIZE_BYTES=200000000  # 200MB
```

### Permission Denied

**Symptom**: `PermissionError: [Errno 13] Permission denied: '/path/to/file'`

**Solution**: Check file permissions:

```bash
ls -la /path/to/file
chmod 644 /path/to/file
```

### PDF Ingestion Uses Too Much Memory

**Symptom**: Ingesting a large PDF (hundreds of pages or more) balloons RAM,
swap starts thrashing, or the ingest process is OOM-killed on small hosts.

**Possible Causes**:

1. PDF backend: docling's default threaded docling-parse backend retains
   parsed pages natively — tens of MB per page on text-dense,
   word-fragmented PDFs (upstream docling issues #4705, #2209, #2779).
2. Whole-document conversion: the PDF converts as one unit with no page
   windowing, so peak memory grows with page count.
3. Worker retention: the ingest worker holds the conversion result and
   accumulates all chunks and embeddings before the parent stores anything.
4. Accelerator: `pdf_accelerator_device=auto` resolves to XPU on Intel GPUs
   whose memory is shared system RAM (~1.3 GB measured overhead), with an
   unbounded in-RAM SYCL JIT cache.

**Solutions**:

The defaults below already bound memory; change them only if a large PDF
still exceeds your host's budget.

1. Use the pypdfium PDF backend. This is the default; set `docling-parse`
   only to restore the legacy backend's behavior:

```bash
export SECONDBRAIN_PDF_BACKEND=pypdfium  # or docling-parse for legacy behavior
```

2. Convert oversized PDFs in page windows instead of as one unit. Default
   200 pages per conversion; `0` disables windowing; lower for tighter
   memory:

```bash
export SECONDBRAIN_PDF_MAX_PAGES_PER_CONVERT=200
```

3. Cap the pages docling buffers between conversion stages. Default 16:

```bash
export SECONDBRAIN_PDF_PIPELINE_QUEUE_MAX_SIZE=16
```

4. Pin the accelerator to CPU on small hosts to remove the XPU
   shared-memory overhead. Keep `auto` (the default) when the host has
   headroom — the GPU speeds up the layout model:

```bash
export SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu
```

5. Tune the low-memory warning threshold (default 2048 MiB). Warning only —
   it never fails ingestion:

```bash
export SECONDBRAIN_ACCELERATOR_MIN_FREE_RAM_MIB=2048
```

**Measured reference numbers** (6 GB RAM host with an Intel Arc iGPU,
docling 2.138.0, 1200-page / 9.6 MB text-layer PDF):

| Conversion path | Peak RSS | Outcome |
| --- | --- | --- |
| docling-parse backend (`SECONDBRAIN_PDF_BACKEND=docling-parse`), `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=auto` (XPU) | >3.7 GB within ~10–30 s, before finishing its first 4-page batch | grows unbounded; swap thrash / OOM on a 6 GB host |
| docling-parse backend, `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu` | >3.6 GB at ~4–6 s | same explosion — the backend, not the device, dominates |
| pypdfium backend, `cpu`, 50-page window | 2296 MiB | completed |
| pypdfium backend, `auto` (XPU), 50-page window | >3.6 GB at ~4 s | killed — XPU adds ≥1.3 GB (iGPU shares system RAM 1:1) |
| pypdfium backend, `cpu`, whole 1200-page document (`SECONDBRAIN_PDF_MAX_PAGES_PER_CONVERT=0`) | 2749 MiB peak, 2.2–2.7 GB plateau | completed in 968 s — bounded |

Book-like PDFs can skip docling entirely:
`SECONDBRAIN_PDF_STRUCTURE_PROBE_ENABLED=false` keeps every text-layer PDF
on the fast native text-extraction path (~1 s and ~300 MB for the reference
PDF), at the cost of structure-aware parsing. This trade-off knob already
exists and applies independently of the settings above.

## Search Issues

### No Results Returned

**Symptom**: Search returns zero results despite matching content

**Possible Causes**:

1. Documents haven't been ingested yet:

```bash
secondbrain ingest ./documents/ --recursive
```

1. Similarity threshold too high:

```bash
secondbrain search "query" --min-score 0.3
```

1. Wrong collection or Qdrant URL queried:

```bash
echo $SECONDBRAIN_QDRANT_URL
echo $SECONDBRAIN_QDRANT_COLLECTION
```

### Poor Search Relevance

**Symptom**: Results don't match query intent

**Solutions**:

1. Adjust chunk size for better semantic granularity:

```bash
export SECONDBRAIN_CHUNK_SIZE=2048  # Smaller chunks
```

1. Increase top-k for more candidate results:

```bash
secondbrain search "query" --top-k 50
```

1. Lower minimum score threshold:

```bash
secondbrain search "query" --min-score 0.3
```

## CLI Command Issues

### Command Not Recognized

**Symptom**: `Error: No such command 'command-name'`

**Solution**: Verify you're using the correct command syntax:

```bash
secondbrain --help
secondbrain ingest --help
```

### Invalid Arguments

**Symptom**: `Error: Invalid value for '--option': 'value'`

**Solution**: Check the command reference for valid option values:

```bash
secondbrain search --help
```

## Health Check Failures

### Service Unavailable

**Symptom**: `secondbrain health` reports unhealthy services

**Solution**:

1. Check Qdrant connectivity:

```bash
secondbrain health
```

1. Restart services:

```bash
secondbrain stop
secondbrain start --wait
```

## Performance Issues

### Slow Ingestion

**Symptom**: Document processing takes excessively long

**Solutions**:

1. Enable multicore processing:

```bash
secondbrain ingest ./docs --recursive --cores 4
```

1. Adjust batch size:

```bash
secondbrain ingest ./docs --batch-size 20
```

1. Disable text compression temporarily:

```bash
export SECONDBRAIN_TEXT_COMPRESSION_ENABLED=false
```

### High Memory Usage

**Symptom**: System runs out of memory during batch operations

**Solutions**:

1. Reduce streaming batch size:

```bash
export SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE=50
```

1. Limit worker processes:

```bash
export SECONDBRAIN_MAX_WORKERS=2
```

## Getting Help

If you encounter issues not covered here:

1. Check the [GitHub Issues](https://github.com/handbrianc/secondbrain/issues)
2. Review existing discussions
3. File a new issue with relevant logs and system information
