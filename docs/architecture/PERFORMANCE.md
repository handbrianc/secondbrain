# Performance Baselines

This document tracks performance baselines for the SecondBrain document intelligence system.

## Benchmark Results

### Document Ingestion

| Document Type | Size | Throughput | Notes |
|--------------|------|------------|-------|
| PDF (text) | 100KB | ~5-10 docs/sec | Single document ingestion |
| DOCX | 50KB | ~8-12 docs/sec | Batch ingestion |
| PDF (scanned) | 2MB | ~1-2 docs/sec | OCR required |

### Search Latency

| Dataset Size | p50 Latency | p95 Latency | p99 Latency |
|--------------|-------------|-------------|-------------|
| 100 documents | 50ms | 100ms | 150ms |
| 1,000 documents | 100ms | 200ms | 300ms |
| 10,000 documents | 200ms | 400ms | 600ms |

### Memory Usage

| Operation | Memory Footprint | Notes |
|-----------|-----------------|-------|
| Embedding generation | ~500MB | sentence-transformers model loaded |
| Document parsing | ~100MB per doc | Depends on document complexity |
| MongoDB connection | ~50MB | Motor async client |

## Hardware Requirements

### Minimum
- **RAM**: 4GB
- **CPU**: 2 cores
- **Storage**: 1GB free space per 1000 documents

### Recommended
- **RAM**: 8GB+
- **CPU**: 4+ cores (for parallel ingestion)
- **Storage**: SSD for faster I/O

## Performance Tuning

### Optimizing Ingestion Speed

1. **Increase batch size**: `--batch-size 20` (default: 10)
2. **Use multiple cores**: `--cores 4` (auto-detects by default)
3. **Disable verbose output**: Remove `--verbose` flag for production

### Optimizing Search Speed

1. **Limit results**: Use `--top-k 5` instead of default
2. **Pre-filter**: Use `--source` or `--file-type` filters
3. **Index optimization**: MongoDB creates index automatically on first search

### Memory Optimization

1. **Reduce embedding cache**: Set `SECONDBRAIN_EMBEDDING_CACHE_SIZE=500`
2. **Stream processing**: Enable `SECONDBRAIN_STREAMING_ENABLED=true`
3. **Clear cache periodically**: Restart application after large batches

## Benchmarking Instructions

Run benchmarks with:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all benchmarks
pytest benchmarks/ --benchmark-only

# Run specific benchmark
pytest benchmarks/test_ingestion_benchmarks.py --benchmark-only

# Compare against previous run
pytest benchmarks/ --benchmark-only --benchmark-compare
```

## Performance Regression Detection

Performance should be monitored for:
- Document ingestion throughput (should not decrease by >10%)
- Search latency (p95 should not increase by >20%)
- Memory usage (should not increase by >15% per operation)

## Notes

- Baselines measured on Apple M1 Mac, 16GB RAM
- MongoDB Atlas (free tier) for cloud deployments
- sentence-transformers/all-MiniLM-L6-v2 for embeddings
- Actual performance varies based on document complexity and hardware
