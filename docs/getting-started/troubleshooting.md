# Troubleshooting Guide

This guide covers common issues and their solutions when working with SecondBrain.

## Installation Issues

### Python Version Compatibility

**Error**: `Python 3.11+ is required`

**Solution**:
```bash
# Check Python version
python --version

# Install Python 3.11+ if needed
# Ubuntu/Debian
sudo apt-get install python3.11 python3.11-venv python3.11-dev

# macOS
brew install python@3.11
```

### MongoDB Connection Issues

**Error**: `MongoServerSelectionError: connect ECONNREFUSED`

**Solutions**:

1. **Verify MongoDB is running**:
   ```bash
   # Check Docker container
   docker ps | grep mongo
   
   # Start MongoDB via Docker
   docker-compose up -d mongo
   ```

2. **Check connection string**:
   ```bash
   # Default URI
   echo $SECONDBRAIN_MONGO_URI
   # Should be: mongodb://localhost:27017
   ```

3. **Test connection manually**:
   ```bash
   mongosh "mongodb://localhost:27017"
   ```

### sentence-transformers Service Issues

**Error**: `Connection refused to sentence-transformers API`

**Solutions**:

1. **Start sentence-transformers service**:
   ```bash
   # Using Docker
   docker-compose up -d sentence-transformers
   
   # Or locally (if installed)
   sentence-transformers serve
   ```

2. **Verify service is running**:
   ```bash
   curl http://localhost:8000/health
   ```

3. **Check service logs**:
   ```bash
   docker logs sentence-transformers
   ```

## Runtime Issues

### Circuit Breaker Opens Frequently

**Symptom**: `CircuitBreakerError: Circuit is open for service`

**Causes**:
- MongoDB or sentence-transformers service unavailability
- Network issues
- Service overload

**Solutions**:

1. **Check service health**:
   ```bash
   secondbrain health
   ```

2. **Wait for recovery**:
   - Circuit breaker automatically recovers after timeout (default: 30s)
   - Monitor logs for recovery attempts

3. **Adjust circuit breaker thresholds** (if services are slow but healthy):
   ```python
   # In your configuration
   SECONDBRAIN_CB_FAILURE_THRESHOLD=10
   SECONDBRAIN_CB_RECOVERY_TIMEOUT=60
   ```

4. **Restart services**:
   ```bash
   docker-compose restart
   ```

### Slow Ingestion Performance

**Symptom**: Document ingestion takes longer than expected

**Solutions**:

1. **Enable multicore processing**:
   ```bash
   secondbrain ingest /path/to/docs --cores 4
   ```

2. **Set environment variable**:
   ```bash
   export SECONDBRAIN_MAX_WORKERS=4
   ```

3. **Check system resources**:
   ```bash
   # Monitor CPU and memory
   top
   htop
   ```

4. **Adjust chunk size** for large documents:
   ```bash
   secondbrain ingest /path/to/docs --chunk-size 8192
   ```

### Search Returns No Results

**Symptom**: Search queries return empty results

**Solutions**:

1. **Verify documents are ingested**:
   ```bash
   secondbrain list
   ```

2. **Check embedding service**:
   ```bash
   secondbrain health --verbose
   ```

3. **Test with simple query**:
   ```bash
   secondbrain search "test"
   ```

4. **Verify embedding dimension** matches model:
   - sentence-transformers/all-MiniLM-L6-v2: 384 dimensions
   - sentence-transformers/all-mpnet-base-v2: 768 dimensions

## Logging and Debugging

### Enable Verbose Logging

```bash
# CLI
secondbrain ingest /path/to/docs --verbose

# Environment variable
export SECONDBRAIN_LOG_LEVEL=DEBUG
```

### Structured JSON Logging

```bash
export SECONDBRAIN_LOG_FORMAT=json
```

Output example:
```json
{"level": "INFO", "message": "Document ingested", "doc_id": "doc-123", "timestamp": "2024-01-01T00:00:00Z"}
```

### View Application Logs

```bash
# Docker logs
docker-compose logs -f secondbrain

# Local logs (if configured)
tail -f /var/log/secondbrain/app.log
```

## Security Scanning Issues

### pip-audit Vulnerabilities Found

**Solution**:
```bash
# Run security scan
./scripts/security_scan.sh audit

# Update vulnerable packages
pip install --upgrade <package-name>

# Or regenerate requirements
pip freeze > requirements.txt
```

### SBOM Generation Fails

**Error**: `cyclonedx-py command not found`

**Solution**:
```bash
# Install cyclonedx-bom
pip install cyclonedx-bom

# Or use security scan script
./scripts/security_scan.sh sbom
```

## Testing Issues

### Tests Fail with Timeout

**Solution**:
```bash
# Increase timeout
pytest --timeout=120

# Or skip slow tests
pytest -m "not slow"
```

### Integration Tests Fail

**Symptom**: Tests requiring MongoDB or sentence-transformers fail

**Solutions**:

1. **Ensure services are running**:
   ```bash
   docker-compose up -d
   ```

2. **Run only unit tests**:
   ```bash
   pytest -m "not integration"
   ```

3. **Run integration tests separately**:
   ```bash
   pytest -m integration
   ```

## Database Issues

### Database Lock Errors

**Error**: `MongoError: Locking issue`

**Solution**:
```bash
# Restart MongoDB
docker-compose restart mongo

# Or reset database (development only!)
docker-compose down -v
docker-compose up -d
```

### Out of Memory Errors

**Symptom**: `MongoMemoryError` or `OutOfMemoryError`

**Solutions**:

1. **Increase Docker memory**:
   ```bash
   # Edit docker-compose.yml
   services:
     mongo:
       mem_limit: 2g
   ```

2. **Clear old documents**:
   ```bash
   secondbrain delete --older-than 30d
   ```

## Performance Issues

### High CPU Usage

**Solutions**:

1. **Limit worker processes**:
   ```bash
   export SECONDBRAIN_MAX_WORKERS=2
   ```

2. **Reduce batch size**:
   ```bash
   secondbrain ingest /path/to/docs --batch-size 10
   ```

### High Memory Usage

**Solutions**:

1. **Process documents in smaller batches**:
   ```bash
   secondbrain ingest /path/to/docs --batch-size 5
   ```

2. **Clear Python cache**:
   ```bash
   find . -type d -name __pycache__ -exec rm -r {} +
   ```

## Getting More Help

If these solutions don't resolve your issue:

1. **Check logs**:
   ```bash
   secondbrain health --verbose
   ```

2. **Enable debug mode**:
   ```bash
   export SECONDBRAIN_LOG_LEVEL=DEBUG
   ```

3. **Run diagnostics**:
   ```bash
   ./scripts/diagnostics.sh  # If available
   ```

4. **Open an issue** with:
   - Error messages
   - Log output
   - System information
   - Steps to reproduce

## Common Error Codes

| Error Code | Meaning | Solution |
|------------|---------|----------|
| ECONNREFUSED | Service not running | Start service with docker-compose |
| ETIMEDOUT | Connection timeout | Check network, increase timeout |
| CircuitBreakerError | Service unavailable | Wait for recovery or restart service |
| TimeoutError | Operation timed out | Increase timeout or optimize query |
| AuthenticationError | Invalid credentials | Check MongoDB URI credentials |
