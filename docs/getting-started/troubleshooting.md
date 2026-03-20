# Troubleshooting Guide

Common issues and solutions for SecondBrain.

## MongoDB Connection Issues

### Error: "MongoServerSelectionError: connect ECONNREFUSED"

**Cause**: MongoDB is not running or unreachable.

**Solution**:
```bash
# Check if MongoDB is running
docker ps | grep mongo  # Docker
brew services list | grep mongodb  # macOS Homebrew

# Start MongoDB
docker-compose up -d  # Docker
brew services start mongodb-community  # macOS
```

### Error: "Authentication failed"

**Cause**: Incorrect MongoDB credentials.

**Solution**:
```bash
# Verify credentials in .env
cat .env | grep SECONDBRAIN_MONGO_URI

# Test connection
mongosh "mongodb://localhost:27017" -u your_user -p your_password
```

## sentence-transformers Issues

### Error: "Connection refused to sentence-transformers API"

**Cause**: sentence-transformers service is not running.

**Solution**:
```bash
# Check if service is running
curl http://localhost:11434/api/tags

# Start sentence-transformers
sentence-transformers serve

# Pull required model if not present
sentence-transformers pull embeddinggemma:latest
```

### Error: "Model not found"

**Cause**: Required embedding model is not downloaded.

**Solution**:
```bash
# List available models
sentence-transformers list

# Pull the model
sentence-transformers pull embeddinggemma:latest

# Or specify a different model in .env
SECONDBRAIN_MODEL=all-MiniLM-L6-v2
```

## Ingestion Issues

### Error: "File format not supported"

**Cause**: Attempting to ingest an unsupported file type.

**Supported formats**:
- PDF (.pdf)
- Word (.docx)
- PowerPoint (.pptx)
- Excel (.xlsx)
- HTML (.html, .htm)
- Markdown (.md)
- Text (.txt)
- Images (.png, .jpg, .jpeg) - requires OCR
- Audio (.wav, .mp3) - requires transcription

**Solution**: Convert file to supported format or install required dependencies.

### Error: "Permission denied"

**Cause**: Insufficient file system permissions.

**Solution**:
```bash
# Check file permissions
ls -la /path/to/documents/

# Fix permissions if needed
chmod +r /path/to/documents/*
```

### Error: "No documents found in directory"

**Cause**: Directory is empty or contains no supported files.

**Solution**:
```bash
# Check directory contents
ls -la /path/to/documents/

# Verify file extensions
find /path/to/documents/ -type f -name "*.pdf" -o -name "*.docx"
```

## Search Issues

### Error: "No results found"

**Cause**: 
- No documents in database
- Query is too specific
- Embedding model mismatch

**Solution**:
```bash
# Check if documents exist
secondbrain list

# Try a broader search
secondbrain search "general topic"

# Verify embedding dimensions match
cat .env | grep SECONDBRAIN_EMBEDDING_DIMENSIONS
```

### Error: "Vector dimension mismatch"

**Cause**: Query embedding dimensions don't match stored embeddings.

**Solution**:
```bash
# Ensure same model is used for ingestion and search
cat .env | grep SECONDBRAIN_MODEL

# Re-ingest with correct model if needed
SECONDBRAIN_MODEL=all-MiniLM-L6-v2 secondbrain ingest ./docs/
```

## Performance Issues

### Slow ingestion

**Causes**:
- Large documents
- Small chunk size
- Rate limiting enabled

**Solutions**:
```bash
# Increase chunk size
SECONDBRAIN_CHUNK_SIZE=8192 secondbrain ingest ./docs/

# Increase workers (if system has resources)
SECONDBRAIN_MAX_WORKERS=8 secondbrain ingest ./docs/

# Disable rate limiting (development only)
SECONDBRAIN_RATE_LIMIT_ENABLED=false secondbrain ingest ./docs/
```

### Slow search

**Causes**:
- Large database
- High top-k value
- No indexes

**Solutions**:
```bash
# Limit results
secondbrain search "query" --top-k 10

# Check database size
secondbrain status
```

## Configuration Issues

### Error: "Invalid configuration"

**Cause**: Malformed .env file or invalid environment variables.

**Solution**:
```bash
# Check .env syntax
cat .env

# Validate with SecondBrain
secondbrain health --verbose

# Reset to defaults (backup first!)
cp .env .env.backup
rm .env
cp .env.example .env
```

### Environment variables not loading

**Cause**: .env file not in working directory or not loaded.

**Solution**:
```bash
# Ensure .env is in current directory
pwd
ls -la .env

# Or specify explicitly
export $(cat .env | xargs)
secondbrain ingest ./docs/
```

## Docker-Specific Issues

### Container won't start

**Solution**:
```bash
# Check Docker logs
docker-compose logs mongo

# Remove and recreate containers
docker-compose down
docker-compose up -d

# Check Docker resources
docker system df
```

### Port conflicts

**Solution**:
```bash
# Check what's using the port
lsof -i :27017  # MongoDB
lsof -i :11434  # sentence-transformers

# Change port in docker-compose.yml or stop conflicting service
```

## Logging & Debugging

### Enable verbose logging

```bash
# CLI flag
secondbrain ingest ./docs/ --verbose

# Environment variable
SECONDBRAIN_VERBOSE=true secondbrain ingest ./docs/

# Debug log level
SECONDBRAIN_LOG_LEVEL=DEBUG secondbrain ingest ./docs/
```

### Check logs

```bash
# Docker logs
docker-compose logs -f mongo
docker-compose logs -f sentence-transformers

# Application logs (if configured to file)
tail -f /path/to/logs/secondbrain.log
```

## Getting More Help

If you can't find your issue here:

1. **Check logs**: Enable verbose/debug logging
2. **Verify setup**: Run `secondbrain health` to check services
3. **Review documentation**: [Configuration Guide](configuration.md)
4. **Search issues**: [GitHub Issues](https://github.com/your-repo/issues)
5. **Open an issue**: Include error message, logs, and reproduction steps

## Common Error Codes

| Error | Likely Cause | Solution |
|-------|--------------|----------|
| ECONNREFUSED | Service not running | Start the service |
| AUTH_FAILED | Wrong credentials | Check .env credentials |
| NOT_FOUND | Resource missing | Verify path/resource exists |
| TIMEOUT | Service slow/unreachable | Check service health |
| INVALID_FORMAT | Wrong file type | Use supported format |
