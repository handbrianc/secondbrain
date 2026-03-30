# Error Handling Guide

**Version**: 1.0  
**Last Updated**: March 29, 2026

---

## Overview

This guide provides comprehensive documentation for error handling in SecondBrain, including error codes, troubleshooting steps, and recovery procedures.

---

## Error Code Reference

### SB001: MongoDB Connection Failed

| Field | Value |
|-------|-------|
| **Code** | SB001 |
| **Exception** | `StorageConnectionError` |
| **Severity** | Critical |
| **Description** | Cannot establish connection to MongoDB |

**Common Causes:**
- MongoDB service not running
- Incorrect `MONGODB_URI` in `.env`
- Network connectivity issues
- Authentication credentials invalid

**Resolution Steps:**

1. **Check MongoDB is running:**
   ```bash
   docker ps | grep mongo
   # or
   mongosh --eval "db.adminCommand('ping')"
   ```

2. **Verify connection string:**
   ```bash
   echo $SECONDBRAIN_MONGO_URI
   # Should be: mongodb://localhost:27017 or mongodb+srv://...
   ```

3. **Test connection manually:**
   ```bash
   mongosh "$SECONDBRAIN_MONGO_URI" --eval "db.adminCommand('ping')"
   ```

4. **Check authentication:**
   ```bash
   # If using auth, ensure username/password are correct
   # mongodb://username:password@host:27017/database
   ```

**Prevention:**
- Use Docker Compose for local development
- Add connection validation to startup checks
- Implement circuit breaker pattern

---

### SB002: Document Conversion Failed

| Field | Value |
|-------|-------|
| **Code** | SB002 |
| **Exception** | `DocumentExtractionError` |
| **Severity** | High |
| **Description** | Failed to extract text from document |

**Common Causes:**
- Unsupported file format
- Corrupted PDF/DOCX file
- Docling library incompatible with file version
- File permissions issue

**Resolution Steps:**

1. **Check file format:**
   ```bash
   file /path/to/document.pdf
   # Supported: PDF, DOCX, TXT, Markdown
   ```

2. **Verify file integrity:**
   ```bash
   # For PDFs
   pdftk /path/to/document.pdf dump_data | head
   
   # For DOCX (it's a ZIP)
   unzip -t /path/to/document.docx
   ```

3. **Try converting to PDF first:**
   ```bash
   # Convert DOCX to PDF, then ingest
   libreoffice --headless --convert-to pdf document.docx
   secondbrain ingest document.pdf
   ```

4. **Check file permissions:**
   ```bash
   ls -l /path/to/document.pdf
   # Ensure read permissions
   ```

**Prevention:**
- Validate file format before ingestion
- Add file size limits
- Implement retry with different parsers

---

### SB003: Embedding Generation Timeout

| Field | Value |
|-------|-------|
| **Code** | SB003 |
| **Exception** | `EmbeddingGenerationError` |
| **Severity** | High |
| **Description** | Embedding model took too long to generate embeddings |

**Common Causes:**
- Document chunk too large
- Model loading on first request
- Insufficient system memory
- GPU not available (falling back to CPU)

**Resolution Steps:**

1. **Reduce chunk size:**
   ```bash
   secondbrain ingest document.pdf --chunk-size 256
   ```

2. **Pre-load model:**
   ```bash
   # Run a small test to load model into memory
   secondbrain search "test" --limit 0
   ```

3. **Check memory availability:**
   ```bash
   free -h
   # Ensure at least 4GB available
   ```

4. **Enable GPU acceleration:**
   ```bash
   # Check if NVIDIA GPU available
   nvidia-smi
   
   # Set environment variable
   export SECONDBRAIN_USE_GPU=true
   ```

5. **Increase timeout:**
   ```python
   # In .env
   SECONDBRAIN_EMBEDDING_TIMEOUT=300  # 5 minutes
   ```

**Prevention:**
- Implement chunk size validation
- Add model warm-up on startup
- Use embedding cache

---

### SB004: Vector Storage Index Not Found

| Field | Value |
|-------|-------|
| **Code** | SB004 |
| **Exception** | `StorageError` |
| **Severity** | High |
| **Description** | MongoDB vector search index does not exist |

**Common Causes:**
- Index not created during setup
- Collection name mismatch
- MongoDB version < 6.0 (no vector support)

**Resolution Steps:**

1. **Check MongoDB version:**
   ```bash
   mongosh --eval "db.version()"
   # Must be >= 6.0
   ```

2. **Verify collection exists:**
   ```bash
   mongosh "$SECONDBRAIN_MONGO_URI"
   > use secondbrain
   > show collections
   ```

3. **Create vector index:**
   ```python
   # Run this Python script
   from pymongo import MongoClient
   
   client = MongoClient("mongodb://localhost:27017")
   db = client.secondbrain
   collection = db.embeddings
   
   # Create vector index
   collection.create_index([
       ("embedding", "vector")
   ])
   ```

4. **Check index exists:**
   ```bash
   mongosh
   > use secondbrain
   > db.embeddings.getIndexes()
   ```

**Prevention:**
- Add index creation to initialization
- Validate index existence on startup

---

### SB005: Ollama LLM Unreachable

| Field | Value |
|-------|-------|
| **Code** | SB005 |
| **Exception** | `ServiceUnavailableError` |
| **Severity** | Medium |
| **Description** | Cannot connect to Ollama LLM server |

**Common Causes:**
- Ollama service not running
- Incorrect `OLLAMA_BASE_URL`
- Model not downloaded
- Network/firewall blocking

**Resolution Steps:**

1. **Check Ollama service:**
   ```bash
   curl http://localhost:11434/api/tags
   # Should return list of available models
   ```

2. **Verify URL configuration:**
   ```bash
   echo $SECONDBRAIN_OLLAMA_BASE_URL
   # Should be: http://localhost:11434
   ```

3. **Pull required model:**
   ```bash
   ollama pull llama2
   # or whatever model is configured
   ```

4. **Test model:**
   ```bash
   ollama run llama2 "Hello"
   ```

5. **Check firewall:**
   ```bash
   # Ensure port 11434 is open
   lsof -i :11434
   ```

**Prevention:**
- Add Ollama health check to startup
- Implement circuit breaker
- Cache responses locally

---

### SB006: Circuit Breaker Open

| Field | Value |
|-------|-------|
| **Code** | SB006 |
| **Exception** | `ServiceUnavailableError` |
| **Severity** | Medium |
| **Description** | Circuit breaker is open, requests blocked |

**Common Causes:**
- Service has been failing repeatedly
- Too many consecutive failures
- Recovery timeout not elapsed

**Resolution Steps:**

1. **Check circuit breaker status:**
   ```python
   from secondbrain.utils.circuit_breaker import CircuitBreaker
   
   cb = CircuitBreaker("mongodb")
   print(cb.state)  # OPEN, HALF_OPEN, CLOSED
   ```

2. **Wait for recovery timeout:**
   ```bash
   # Default is 60 seconds
   # Wait and retry
   sleep 60
   ```

3. **Manually reset (if confident):**
   ```python
   from secondbrain.utils.circuit_breaker import reset_circuit_breaker
   reset_circuit_breaker("mongodb")
   ```

4. **Check underlying service:**
   ```bash
   # Verify MongoDB is actually healthy
   mongosh --eval "db.adminCommand('ping')"
   ```

**Prevention:**
- Implement proper error handling
- Add fallback mechanisms
- Monitor failure rates

---

### SB007: Memory Limit Exceeded

| Field | Value |
|-------|-------|
| **Code** | SB007 |
| **Exception** | `RuntimeError` |
| **Severity** | Critical |
| **Description** | Process exceeded configured memory limit |

**Common Causes:**
- Large document ingestion
- Insufficient system memory
- Memory leak in processing pipeline
- Too many concurrent workers

**Resolution Steps:**

1. **Reduce worker count:**
   ```bash
   secondbrain ingest document.pdf --workers 1
   ```

2. **Reduce chunk size:**
   ```bash
   secondbrain ingest document.pdf --chunk-size 256
   ```

3. **Check memory usage:**
   ```bash
   top -stats pid,command,mem
   # Find memory-hungry processes
   ```

4. **Increase memory limit:**
   ```bash
   # In .env
   SECONDBRAIN_MEMORY_LIMIT_GB=16
   ```

5. **Process in batches:**
   ```bash
   # Split large document
   pdfseparate large.pdf page-%d.pdf
   for f in page-*.pdf; do
     secondbrain ingest "$f"
   done
   ```

**Prevention:**
- Add memory monitoring
- Implement streaming processing
- Set appropriate worker limits

---

### SB008: Path Traversal Detected

| Field | Value |
|-------|-------|
| **Code** | SB008 |
| **Exception** | `ValidationError` |
| **Severity** | High |
| **Description** | Attempted to access files outside allowed directory |

**Common Causes:**
- Malicious file path input
- Accidental use of `../` in path
- Symlink attack

**Resolution Steps:**

1. **Validate input path:**
   ```bash
   # Check for path traversal attempts
   echo "$INPUT_PATH" | grep -E '\.\./|\.\\.\\'
   ```

2. **Use absolute paths:**
   ```bash
   cd /allowed/base/dir
   realpath "$INPUT_PATH"
   ```

3. **Sanitize filename:**
   ```python
   from pathlib import Path
   
   base = Path("/allowed/dir")
   user_path = Path(user_input)
   resolved = (base / user_path).resolve()
   
   if not str(resolved).startswith(str(base)):
       raise ValidationError("Path traversal detected")
   ```

4. **Check symlinks:**
   ```bash
   readlink -f "$INPUT_PATH"
   ```

**Prevention:**
- Always validate and sanitize paths
- Use allowlists for file types
- Implement sandboxing

---

## Troubleshooting FAQ

### Q: Why does my document ingestion fail with "Document conversion failed"?

**A:** This typically means the file format is unsupported or the file is corrupted. Try:
1. Convert to PDF first
2. Check file integrity with `file` command
3. Try a different document

### Q: How do I debug embedding generation issues?

**A:** Enable verbose logging:
```bash
secondbrain ingest document.pdf --verbose
```

Check if the model is loading:
```bash
python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('all-MiniLM-L6-v2'); print('Model loaded')"
```

### Q: MongoDB keeps disconnecting during long operations

**A:** This is likely a network timeout. Solutions:
1. Increase MongoDB timeout settings
2. Use connection pooling
3. Implement retry logic
4. Check network stability

### Q: Circuit breaker keeps opening

**A:** This indicates a persistent service failure. Check:
1. Service health (MongoDB, Ollama)
2. Resource availability (memory, CPU)
3. Network connectivity
4. Authentication credentials

### Q: How do I recover from a failed ingestion?

**A:** 
1. Check logs for specific error
2. Clean up partial data:
   ```bash
   secondbrain delete --by-path /path/to/document
   ```
3. Retry with adjusted parameters

---

## Error Recovery Procedures

### Automatic Recovery

SecondBrain implements automatic recovery for many errors:

1. **Connection Errors**: Circuit breaker with exponential backoff
2. **Embedding Failures**: Retry with reduced chunk size
3. **Timeout Errors**: Automatic retry with increased timeout

### Manual Recovery

For errors that require manual intervention:

1. **Identify the error code** from logs
2. **Consult this guide** for resolution steps
3. **Apply the fix**
4. **Retry the operation**
5. **Report persistent issues** to support

---

## Logging and Monitoring

### Log Levels

- **DEBUG**: Detailed debugging information
- **INFO**: Normal operational messages
- **WARNING**: Potential issues (circuit breaker opening)
- **ERROR**: Operation failures
- **CRITICAL**: System failures (service unavailable)

### Enable Verbose Logging

```bash
# CLI
secondbrain --verbose ingest document.pdf

# Environment variable
export SECONDBRAIN_LOG_LEVEL=DEBUG
```

### Structured Logging

Logs are available in JSON format for easier parsing:
```bash
export SECONDBRAIN_LOG_FORMAT=json
```

Example JSON log entry:
```json
{
  "timestamp": "2026-03-29T12:00:00Z",
  "level": "ERROR",
  "logger": "secondbrain.ingestor",
  "message": "Document conversion failed",
  "error_code": "SB002",
  "file": "document.pdf",
  "traceback": "..."
}
```

---

## Reporting New Errors

If you encounter an error not covered in this guide:

1. **Collect information:**
   - Error code and message
   - Full traceback
   - Steps to reproduce
   - System information (OS, Python version)

2. **Create an issue:**
   - Include all collected information
   - Label as "bug" or "documentation"
   - Provide suggested fix if known

3. **Temporary workaround:**
   - Document what you tried
   - Note any workarounds discovered

---

## Appendix: Exception Hierarchy

```
SecondBrainError (base)
├── ConfigError
├── ValidationError
├── ServiceError
│   ├── StorageConnectionError (SB001)
│   ├── ServiceUnavailableError (SB005, SB006)
│   │   └── SentenceTransformersUnavailableError
│   └── StorageError (SB004)
├── DocumentExtractionError (SB002)
├── EmbeddingError
│   └── EmbeddingGenerationError (SB003)
├── CLIValidationError (SB008)
└── UnsupportedFileError
```

---

**Document Version**: 1.0  
**Maintained By**: Security Team  
**Review Frequency**: Quarterly
