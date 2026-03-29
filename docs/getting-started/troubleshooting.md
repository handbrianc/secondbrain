# Troubleshooting

Common issues and solutions for SecondBrain.

## Installation Issues

### pip Install Fails

**Symptom**: `pip install secondbrain` fails with errors

**Solutions**:
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Clear cache
pip cache purge

# Try again
pip install secondbrain
```

### Dependency Conflicts

**Symptom**: `ResolutionImpossible` error

**Solutions**:
```bash
# Create fresh virtual environment
python -m venv venv
source venv/bin/activate
pip install secondbrain
```

## MongoDB Connection Issues

### Can't Connect to MongoDB

**Symptom**: `MongoServerSelectionError`

**Checklist**:
1. Is MongoDB running?
   ```bash
   mongosh
   ```
2. Is connection string correct?
   ```env
   MONGODB_URI=mongodb://localhost:27017
   ```
3. Is firewall blocking port 27017?
   ```bash
   netstat -an | grep 27017
   ```

### Authentication Failed

**Symptom**: `Authentication failed`

**Solutions**:
1. Verify credentials in connection string
2. Check user has proper permissions
3. Verify authentication database

## Embedding Issues

### Model Download Fails

**Symptom**: `HTTPError` when loading model

**Solutions**:
```bash
# Download manually
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Check internet connection
ping huggingface.co
```

### GPU Not Detected

**Symptom**: "CUDA not available"

**Solutions**:
```bash
# Check CUDA installation
nvidia-smi

# Verify PyTorch CUDA support
python -c "import torch; print(torch.cuda.is_available())"

# Install CUDA version
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

## Search Issues

### No Results Found

**Symptom**: Search returns empty results

**Checklist**:
1. Are documents ingested?
   ```bash
   secondbrain list
   ```
2. Is query too specific?
   ```bash
   secondbrain search "broader topic"
   ```
3. Check embedding model matches

### Slow Search

**Symptom**: Search takes > 5 seconds

**Solutions**:
1. Check MongoDB performance
2. Verify vector index exists
3. Reduce result limit
4. Check network latency

## Performance Issues

### High Memory Usage

**Symptom**: Process uses > 4GB RAM

**Solutions**:
```bash
# Reduce batch size
export CHUNK_SIZE=250

# Use smaller model
export EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### Slow Ingestion

**Symptom**: Ingestion takes too long

**Solutions**:
1. Enable GPU acceleration
2. Increase batch size
3. Use multiple workers
4. Check disk I/O

## CLI Issues

### Command Not Found

**Symptom**: `secondbrain: command not found`

**Solutions**:
```bash
# Reinstall
pip install --force-reinstall secondbrain

# Check PATH
which secondbrain

# Use full path
python -m secondbrain_cli
```

### Permission Denied

**Symptom**: `PermissionError`

**Solutions**:
```bash
# Run without sudo
pip install --user secondbrain

# Or fix permissions
sudo chmod -R 755 /usr/local/bin
```

## Error Messages

### Document Parsing Error

**Error**: `ParsingError: Unsupported format`

**Solution**: Check file format is supported (PDF, DOCX, TXT)

### Vector Dimension Mismatch

**Error**: `ValueError: Dimension mismatch`

**Solution**: Ensure embedding model hasn't changed

### Timeout Error

**Error**: `AsyncTimeoutError`

**Solution**: Increase timeout in configuration

## Getting Help

If you can't find your issue here:

1. Check [GitHub Issues](https://github.com/your-org/secondbrain/issues)
2. Ask in [GitHub Discussions](https://github.com/your-org/secondbrain/discussions)
3. Open a new issue with:
   - Error message
   - Steps to reproduce
   - Environment details
   - Logs

## Logs

### Enable Debug Logging

```env
LOG_LEVEL=DEBUG
LOG_FILE=secondbrain.log
```

### View Logs

```bash
tail -f secondbrain.log
```
