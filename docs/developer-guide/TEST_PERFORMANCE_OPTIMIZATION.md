# Performance Testing Guide

Performance testing and benchmarking guide for SecondBrain.

## Overview

This guide covers performance testing strategies and benchmarking tools for SecondBrain.

## Benchmarking Tools

### pytest-benchmark

```python
import pytest

@pytest.mark.benchmark
def test_search_latency(benchmark):
    """Benchmark search latency."""
    
    def search():
        results = storage.search("test query", limit=10)
        return len(results)
    
    stats = benchmark(search)
    
    assert stats.mean < 0.1  # < 100ms
    assert stats.min > 0.001  # > 1ms
```

### Running Benchmarks

```bash
# Run benchmarks
pytest --benchmark-only

# Save benchmark data
pytest --benchmark-save=baseline

# Compare with baseline
pytest --benchmark-compare
```

## Performance Metrics

### Ingestion Performance

```python
import time
from secondbrain.ingestor import DocumentIngestor

def benchmark_ingestion(pdf_path: str):
    """Benchmark document ingestion."""
    ingestor = DocumentIngestor(storage=storage)
    
    start = time.perf_counter()
    doc_ids = ingestor.ingest_file(pdf_path)
    elapsed = time.perf_counter() - start
    
    print(f"Ingestion time: {elapsed:.2f}s")
    print(f"Documents ingested: {len(doc_ids)}")
```

### Search Performance

```python
def benchmark_search(queries: List[str]):
    """Benchmark search performance."""
    times = []
    
    for query in queries:
        start = time.perf_counter()
        results = storage.search(query, limit=10)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    print(f"Avg latency: {sum(times)/len(times):.3f}s")
    print(f"Min latency: {min(times):.3f}s")
    print(f"Max latency: {max(times):.3f}s")
```

## Load Testing

### Concurrent Users

```python
import asyncio
import aiohttp

async def simulate_user(session, query):
    """Simulate a user making a search."""
    start = time.perf_counter()
    async with session.post('/search', json={'query': query}) as resp:
        await resp.json()
    return time.perf_counter() - start

async def load_test(num_users: int, queries: List[str]):
    """Load test with concurrent users."""
    async with aiohttp.ClientSession() as session:
        tasks = [
            simulate_user(session, query)
            for query in queries * num_users
        ]
        results = await asyncio.gather(*tasks)
    
    print(f"Throughput: {len(results)/sum(results):.2f} req/s")
```

### Stress Testing

```python
def stress_test(duration: int = 60):
    """Stress test for given duration."""
    import threading
    
    start_time = time.time()
    requests = 0
    
    def worker():
        nonlocal requests
        while time.time() - start_time < duration:
            storage.search("test query", limit=10)
            requests += 1
    
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    print(f"Total requests: {requests}")
    print(f"RPS: {requests/duration:.2f}")
```

## Profiling

### cProfile

```python
import cProfile
import pstats

def profile_search():
    """Profile search operation."""
    profiler = cProfile.Profile()
    profiler.enable()
    
    storage.search("test query", limit=10)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)
```

### Memory Profiling

```python
from memory_profiler import profile

@profile
def memory_test():
    """Test memory usage."""
    documents = []
    for i in range(1000):
        doc = create_document(i)
        documents.append(doc)
    return documents
```

## Optimization Strategies

### Batch Processing

```python
# Before: Individual processing
for doc in documents:
    embeddings.append(model.encode(doc.content))

# After: Batch processing
embeddings = model.encode([doc.content for doc in documents], batch_size=32)
```

### Caching

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_embedding(text: str):
    return model.encode(text)
```

### Connection Pooling

```python
# Optimize MongoDB connection
client = AsyncMongoClient(
    uri,
    maxPoolSize=50,
    minPoolSize=10,
    maxIdleTimeMS=300000
)
```

## Performance Budgets

### Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Search latency | < 100ms | p95 |
| Ingestion rate | > 100 docs/min | docs/minute |
| Memory usage | < 2GB | Resident set size |
| CPU usage | < 50% | Average |

### CI Integration

```yaml
# .github/workflows/performance.yml
name: Performance

on: [push]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run benchmarks
        run: pytest --benchmark-only --benchmark-json=output.json
      
      - name: Store benchmarks
        uses: benchmark-action/github-action-benchmark@v1
        with:
          tool: 'pytest'
          output-file-path: output.json
```

## See Also

- [Testing Guide](TESTING.md)
- [Async API](async-api.md)
- [Configuration](configuration.md)
