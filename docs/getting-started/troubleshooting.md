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

## MongoDB Connection Issues

### Connection Refused

**Symptom**: `ConnectionRefusedError: [Errno 111] Connection refused`

**Solution**:

1. Verify MongoDB is running:

```bash
docker ps  # For Docker MongoDB
mongod --version  # For local MongoDB
```

2. Start MongoDB if not running:

```bash
secondbrain start --wait
```

3. Check the connection URI is correct:

```bash
echo $SECONDBRAIN_MONGO_URI
```

### Authentication Failed

**Symptom**: `AuthenticationFailed: Auth failed`

**Solution**: Verify credentials in your connection string:

```
mongodb://username:password@host:27017/database
```

Ensure the user has appropriate roles on the database.

### Database Not Ready

**Symptom**: `ServerSelectionTimeoutError: Unable to connect to MongoDB`

**Solution**: Wait for MongoDB to fully initialize:

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
vtt, xml, json
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

## Search Issues

### No Results Returned

**Symptom**: Search returns zero results despite matching content

**Possible Causes**:

1. Documents haven't been ingested yet:

```bash
secondbrain ingest ./documents/ --recursive
```

2. Similarity threshold too high:

```bash
secondbrain search "query" --min-score 0.3
```

3. Wrong collection or database queried:

```bash
echo $SECONDBRAIN_MONGO_DB
echo $SECONDBRAIN_MONGO_COLLECTION
```

### Poor Search Relevance

**Symptom**: Results don't match query intent

**Solutions**:

1. Adjust chunk size for better semantic granularity:

```bash
export SECONDBRAIN_CHUNK_SIZE=2048  # Smaller chunks
```

2. Increase top-k for more candidate results:

```bash
secondbrain search "query" --top-k 50
```

3. Lower minimum score threshold:

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

1. Check MongoDB connectivity:

```bash
secondbrain health
```

2. Restart services:

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

2. Adjust batch size:

```bash
secondbrain ingest ./docs --batch-size 20
```

3. Disable text compression temporarily:

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

2. Limit worker processes:

```bash
export SECONDBRAIN_MAX_WORKERS=2
```

## Getting Help

If you encounter issues not covered here:

1. Check the [GitHub Issues](https://github.com/your-username/secondbrain/issues)
2. Review existing discussions
3. File a new issue with relevant logs and system information