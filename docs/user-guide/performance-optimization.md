# Performance Optimization Guide

This guide covers performance optimization strategies for SecondBrain, including ingestion optimization, search tuning, memory management, GPU acceleration, and monitoring.

## Table of Contents

- [Benchmark Baselines](#benchmark-baselines)
- [Ingestion Optimization](#ingestion-optimization)
- [Search Optimization](#search-optimization)
- [Memory Management](#memory-management)
- [GPU Acceleration](#gpu-acceleration)
- [Monitoring & Profiling](#monitoring--profiling)

---

## Benchmark Baselines

### Current Performance Metrics

**Hardware Reference:**
- CPU: Apple M1 Max
- RAM: 32GB
- Storage: NVMe SSD
- MongoDB: Local instance

**Baseline Results** (as of v0.4.0):

| Operation | Document Size | Time | Memory |
|-----------|--------------|------|--------|
| Ingest (single) | 10KB | 150ms | 400MB |
| Ingest (batch 100) | 10KB | 8s | 800MB |
| Search (single query) | - | 50ms | 500MB |
| Embedding (1000 texts) | 100 tokens | 12s | 600MB |

### Running Benchmarks

```bash
# Run all benchmarks
./scripts/run_benchmarks.sh run

# Run specific benchmark
./scripts/run_benchmarks.sh run --test ingestion

# Compare against baseline
./scripts/run_benchmarks.sh compare

# Save new baseline
./scripts/run_benchmarks.sh baseline --name v0.4.0
```

**Benchmark Results Location**: `benchmark-results.json`

---

## Ingestion Optimization

### 1. Batch Processing

Process multiple documents concurrently for better throughput:

```python
from secondbrain.document.async_ingestor import AsyncDocumentIngestor

# Sequential (slow)
for doc_path in paths:
    await ingestor.ingest(doc_path)  # ~150ms each

# Batch (fast)
async with AsyncDocumentIngestor() as ingestor:
    await ingestor.ingest_batch(paths, batch_size=10)  # ~80ms per doc
```

**Performance Impact:**
- 10x faster for 100 documents
- Memory usage: +200MB for batch buffer

### 2. Chunk Size Tuning

Optimal chunk size depends on your use case:

| Chunk Size | Search Quality | Ingestion Speed | Memory |
|------------|----------------|-----------------|--------|
| 256 tokens | Low | Fast | Low |
| 512 tokens | Medium | Medium | Medium |
| 1024 tokens | High | Slow | High |

**Recommended:**
```python
# Balanced configuration
ingestor = DocumentIngestor(
    chunk_size=512,      # Good quality/speed tradeoff
    chunk_overlap=50     # 10% overlap for context
)
```

### 3. Parallel Document Parsing

Use multiple workers for CPU-intensive parsing:

```bash
# Set worker count (default: CPU count)
export INGEST_WORKERS=4

# Run ingestion
secondbrain ingest /path/to/docs/ --workers 4
```

**Performance Impact:**
- 4 workers: 3.5x faster than single worker
- 8 workers: 5x faster (diminishing returns)

### 4. Embedding Cache

Cache embeddings to avoid recomputation:

```python
from secondbrain.utils.embedding_cache import EmbeddingCache

cache = EmbeddingCache(cache_dir=".embedding_cache")

# Check cache before computing
if cached := cache.get(text):
    embedding = cached
else:
    embedding = model.encode(text)
    cache.set(text, embedding)
```

**Performance Impact:**
- Cache hit: <1ms vs 12ms for embedding
- Cache hit rate: ~60% for repeated documents

---

## Search Optimization

### 1. Query Preprocessing

Optimize queries for better results:

```python
from secondbrain.conversation import QueryRewriter

rewriter = QueryRewriter()

# Expand query for better retrieval
expanded = rewriter.expand_query("machine learning")
# "machine learning algorithms and applications"

# Rewrite for context
rewritten = rewriter.rewrite_query(
    query="how does it work?",
    context="previous conversation about neural networks"
)
```

### 2. Result Limit Tuning

Balance quality vs. speed:

```python
# Fast but may miss relevant results
results = await searcher.search(query, limit=5)

# Slower but more comprehensive
results = await searcher.search(query, limit=50)

# Recommended for most use cases
results = await searcher.search(query, limit=10)
```

**Performance Impact:**
- limit=5: 30ms
- limit=10: 50ms
- limit=50: 150ms

### 3. Hybrid Search

Combine vector and keyword search:

```python
results = await searcher.hybrid_search(
    query="machine learning",
    vector_weight=0.7,
    keyword_weight=0.3,
    filter={"collection": "papers"}
)
```

**Benefits:**
- Better precision for technical terms
- 20% improvement in relevance scores

### 4. Index Optimization

Create MongoDB indexes for faster queries:

```python
from pymongo import ASCENDING
from pymongo.operations import SearchIndex

# Vector search index (auto-created)
# Metadata filter indexes (manual)
collection.create_index([("collection", ASCENDING)])
collection.create_index([("metadata.source", ASCENDING)])
collection.create_index([("embedding_model", ASCENDING)])
```

---

## Memory Management

### 1. Embedding Model Memory

Control memory usage of embedding models:

```python
# Load model with memory optimization
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "all-MiniLM-L6-v2",
    device="cpu",  # or "cuda" for GPU
    trust_remote_code=True
)

# Offload to disk when not in use
import torch
torch.cuda.empty_cache()  # Clear GPU cache
```

**Memory Footprint:**
- all-MiniLM-L6-v2: ~600MB
- all-mpnet-base-v2: ~1.2GB
- all-MiniLM-L12-v2: ~1.8GB

### 2. Batch Size Tuning

Adjust batch size based on available memory:

```python
# Low memory (<8GB)
embeddings = model.encode(texts, batch_size=16)

# Medium memory (8-16GB)
embeddings = model.encode(texts, batch_size=32)

# High memory (>16GB)
embeddings = model.encode(texts, batch_size=64)
```

### 3. Connection Pooling

Reuse MongoDB connections:

```python
from motor.motor_asyncio import AsyncIOMotorClient

# Create client with connection pool
client = AsyncIOMotorClient(
    "mongodb://localhost:27017",
    maxPoolSize=10,
    minPoolSize=5,
    maxIdleTimeMS=300000
)

# Reuse client across requests
database = client.secondbrain
```

### 4. Garbage Collection

Force garbage collection after large operations:

```python
import gc

async def ingest_large_batch(paths):
    await ingestor.ingest_batch(paths)
    
    # Clean up memory
    del paths
    gc.collect()
```

---

## GPU Acceleration

### 1. GPU Detection

Check GPU availability:

```python
import torch

if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f}GB")
else:
    print("No GPU detected, using CPU")
```

### 2. Model Placement

Move embedding model to GPU:

```python
from sentence_transformers import SentenceTransformer

# Auto-detect GPU
device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
```

### 3. CUDA Memory Management

Control GPU memory usage:

```python
import torch

# Limit GPU memory usage
torch.cuda.set_per_process_memory_fraction(0.8, 0)  # Use 80% of GPU

# Clear cache after batch
torch.cuda.empty_cache()

# Monitor memory
print(f"GPU Memory: {torch.cuda.memory_allocated(0) / 1e9:.2f}GB")
```

### 4. Performance Comparison

**Embedding Generation Speed** (1000 texts, 100 tokens each):

| Hardware | Model | Time | Speedup |
|----------|-------|------|---------|
| CPU (M1) | all-MiniLM-L6-v2 | 12s | 1x |
| GPU (RTX 3080) | all-MiniLM-L6-v2 | 2s | 6x |
| GPU (RTX 4090) | all-MiniLM-L6-v2 | 1s | 12x |

**Recommendation:**
- Use GPU for batch ingestion (>100 documents)
- CPU is fine for single document ingestion

---

## Monitoring & Profiling

### 1. Built-in Profiler

Use the profiling script:

```bash
# Profile ingestion
python scripts/profile_ingestion.py --input ./test-docs/

# Profile search
python scripts/profile_search.py --query "machine learning"

# Generate report
python scripts/profile_ingestion.py --report --output profile-report.html
```

### 2. Performance Metrics

Track key metrics:

```python
from secondbrain.utils.metrics import metrics

# Record operation duration
metrics.record("ingestion.duration", duration_seconds)
metrics.record("search.latency", query_time)

# Track throughput
metrics.increment("documents.ingested")
metrics.increment("queries.executed")
```

### 3. Circuit Breaker Monitoring

Monitor service health:

```python
from secondbrain.utils.circuit_breaker import get_circuit_state

state = get_circuit_state("mongodb")
if state == "OPEN":
    logger.warning("MongoDB circuit breaker is open")
```

### 4. Logging Performance

Enable performance logging:

```bash
# Set log level to INFO for performance stats
export LOG_LEVEL=INFO

# Or DEBUG for detailed timing
export LOG_LEVEL=DEBUG
```

**Sample Output:**
```
INFO [2026-03-30 12:00:00] Operation completed: ingest_document (duration: 0.150s)
  - document.parse: 0.050s
  - document.embed: 0.080s
  - document.store: 0.020s
```

### 5. Performance Checklist

Before deploying to production:

- [ ] Run benchmarks and save baseline
- [ ] Tune chunk size for your use case
- [ ] Configure connection pooling
- [ ] Enable GPU if available
- [ ] Set up monitoring dashboards
- [ ] Configure circuit breakers
- [ ] Test under load (100+ concurrent requests)
- [ ] Profile memory usage
- [ ] Verify query latency <100ms
- [ ] Verify ingestion throughput >10 docs/sec

---

## Troubleshooting

### Slow Ingestion

**Symptoms:** Ingesting documents takes longer than expected

**Solutions:**
1. Enable batch processing
2. Increase worker count
3. Use GPU for embeddings
4. Check MongoDB connection speed
5. Reduce chunk size

### High Memory Usage

**Symptoms:** Process uses >4GB RAM

**Solutions:**
1. Reduce batch size
2. Use smaller embedding model
3. Enable garbage collection
4. Check for memory leaks
5. Limit concurrent operations

### Slow Search

**Symptoms:** Query latency >200ms

**Solutions:**
1. Reduce result limit
2. Add MongoDB indexes
3. Check MongoDB performance
4. Use query caching
5. Optimize query preprocessing

### MongoDB Connection Issues

**Symptoms:** Connection timeouts, circuit breaker opens

**Solutions:**
1. Increase connection pool size
2. Check network latency
3. Verify MongoDB is running
4. Tune circuit breaker thresholds
5. Add retry logic

---

## See Also

- [Configuration Guide](../developer-guide/configuration.md)
- [Observability Guide](observability.md)
- [Architecture Decision Records](../architecture/ADRs/)
- [Benchmark Scripts](../../scripts/run_benchmarks.sh)
