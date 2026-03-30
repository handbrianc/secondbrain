# Performance Guide

This guide covers performance optimization for the SecondBrain document intelligence system.

## Overview

SecondBrain is designed for efficient document processing and semantic search. This guide covers:

- Performance characteristics and expectations
- Configuration for optimal performance
- Troubleshooting slow operations
- Benchmarking your setup

## Expected Performance

### Document Ingestion

| Document Type | Typical Throughput | Memory Usage |
|--------------|-------------------|--------------|
| Text (10KB) | 10-20 docs/sec | ~50MB |
| PDF (100KB) | 5-10 docs/sec | ~100MB |
| DOCX (50KB) | 8-12 docs/sec | ~80MB |
| Large PDF (2MB+) | 1-3 docs/sec | ~500MB |

*Note: Performance varies based on hardware, document complexity, and configuration.*

### Search Operations

| Dataset Size | Typical Latency |
|--------------|----------------|
| 100 documents | 50-100ms |
| 1,000 documents | 100-200ms |
| 10,000 documents | 200-400ms |
| 100,000+ documents | 400-800ms |

## Configuration for Performance

### Environment Variables

```bash
# Optimize for speed (use more RAM)
export SECONDBRAIN_EMBEDDING_BATCH_SIZE=50
export SECONDBRAIN_EMBEDDING_CACHE_SIZE=2000
export SECONDBRAIN_MAX_WORKERS=8

# Optimize for memory usage (use less RAM)
export SECONDBRAIN_EMBEDDING_BATCH_SIZE=10
export SECONDBRAIN_EMBEDDING_CACHE_SIZE=500
export SECONDBRAIN_MAX_WORKERS=2
```

### CLI Options for Faster Processing

```bash
# Use more CPU cores for parallel ingestion
secondbrain ingest /path/to/docs --cores 8 --batch-size 20

# Limit search results for faster response
secondbrain search "query" --top-k 5

# Pre-filter to reduce search scope
secondbrain search "query" --file-type pdf --top-k 10
```

## Optimization Strategies

### 1. Parallel Processing

SecondBrain supports parallel document ingestion using multiple CPU cores:

```bash
# Auto-detect optimal core count
secondbrain ingest /path/to/docs

# Specify exact core count
secondbrain ingest /path/to/docs --cores 4

# Use with memory limit
secondbrain ingest /path/to/docs --cores 4 --memory-limit 0.8
```

### 2. Embedding Caching

Embeddings are cached to avoid regenerating for duplicate text:

```bash
# Increase cache size for better hit rate
export SECONDBRAIN_EMBEDDING_CACHE_SIZE=2000

# Monitor cache effectiveness
secondbrain metrics  # Shows cache hit rate
```

### 3. Batch Processing

For large document sets, use batch processing:

```bash
# Process in batches of 20 documents
secondbrain ingest /path/to/docs --batch-size 20

# Recursive processing for directories
secondbrain ingest /path/to/docs --recursive --batch-size 20
```

### 4. MongoDB Optimization

MongoDB automatically creates indexes for vector search. For optimal performance:

- Use MongoDB Atlas (managed) for production
- Ensure sufficient RAM for working set
- Monitor query performance with MongoDB profiler

## Troubleshooting

### Slow Ingestion

**Symptoms**: Processing < 1 document/second

**Solutions**:
1. Increase batch size: `--batch-size 20`
2. Use more cores: `--cores 4`
3. Check MongoDB connection speed
4. Verify document format (PDFs with images are slower)

### Slow Search

**Symptoms**: Search taking > 1 second

**Solutions**:
1. Reduce `--top-k` results
2. Add filters (`--source`, `--file-type`)
3. Check MongoDB index status
4. Increase available RAM for MongoDB

### High Memory Usage

**Symptoms**: Process using > 4GB RAM

**Solutions**:
1. Reduce embedding cache: `SECONDBRAIN_EMBEDDING_CACHE_SIZE=500`
2. Reduce batch size: `--batch-size 5`
3. Use fewer cores: `--cores 2`
4. Enable streaming: `SECONDBRAIN_STREAMING_ENABLED=true`

## Monitoring Performance

### Built-in Metrics

```bash
# View performance metrics
secondbrain metrics

# Check system health
secondbrain health
```

### Custom Monitoring

For production deployments, monitor:

- **Ingestion throughput**: Documents/second
- **Search latency**: p50, p95, p99 percentiles
- **Memory usage**: RSS memory of process
- **MongoDB query time**: Use MongoDB profiler

## Benchmarking

Run benchmarks to establish baseline performance:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run benchmarks
pytest benchmarks/ --benchmark-only

# Compare performance over time
pytest benchmarks/ --benchmark-only --benchmark-compare
```

See [Benchmarking Guide](../developer-guide/benchmarking.md) for detailed instructions.

## Hardware Recommendations

### Development

- **RAM**: 4GB minimum, 8GB recommended
- **CPU**: 2 cores minimum, 4+ recommended
- **Storage**: SSD preferred

### Production

- **RAM**: 16GB+ for large document sets
- **CPU**: 8+ cores for high throughput
- **Storage**: NVMe SSD for fastest I/O
- **MongoDB**: Managed service (Atlas) or dedicated server

## Performance Checklist

Before deploying to production:

- [ ] Run benchmarks to establish baseline
- [ ] Configure appropriate core count for your hardware
- [ ] Set embedding cache size based on available RAM
- [ ] Test with realistic document volumes
- [ ] Monitor MongoDB query performance
- [ ] Set up alerting for performance regressions
- [ ] Document expected throughput for your use case

## Related Documentation

- [Performance Baselines](../architecture/PERFORMANCE.md)
- [Benchmarking Guide](../developer-guide/benchmarking.md)
- [Configuration Reference](../getting-started/configuration.md)
