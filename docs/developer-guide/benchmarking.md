# Benchmarking Guide

This guide explains how to benchmark SecondBrain performance and interpret results.

## Overview

Benchmarking helps you:

- Establish performance baselines
- Detect performance regressions
- Optimize configuration for your workload
- Compare hardware configurations

## Prerequisites

```bash
# Install dev dependencies with pytest-benchmark
pip install -e ".[dev]"

# Verify pytest-benchmark is installed
pytest --version  # Should show pytest-benchmark plugin
```

## Running Benchmarks

### Basic Usage

```bash
# Run all benchmarks
pytest benchmarks/ --benchmark-only

# Run specific benchmark file
pytest benchmarks/test_ingestion_benchmarks.py --benchmark-only

# Run with verbose output
pytest benchmarks/ --benchmark-only -v

# Save results for comparison
pytest benchmarks/ --benchmark-only --benchmark-save=my_run
```

### Benchmark Options

```bash
# Compare against previous run
pytest benchmarks/ --benchmark-only --benchmark-compare

# Only run specific test
pytest benchmarks/ --benchmark-only -k "test_ingest"

# Adjust timing rounds (default: 5)
pytest benchmarks/ --benchmark-only --benchmark-rounds=10

# Adjust timing repeats (default: 3)
pytest benchmarks/ --benchmark-only --benchmark-repeats=5
```

## Benchmark Types

### 1. Ingestion Throughput

Measures documents processed per second:

```python
def test_ingest_single_document(benchmark, temp_docx_file):
    """Benchmark single document ingestion."""
    # Implementation measures time from start to finish
```

**Metrics**:
- Mean time per document
- Standard deviation
- Documents per second

### 2. Search Latency

Measures time to retrieve search results:

```python
def test_search_latency(benchmark):
    """Benchmark search query latency."""
    # Implementation measures query execution time
```

**Metrics**:
- p50 (median) latency
- p95 latency
- p99 latency

### 3. Memory Usage

Measures memory footprint during operations:

```python
def test_memory_usage(benchmark):
    """Benchmark memory usage per operation."""
    # Implementation measures RSS memory changes
```

**Metrics**:
- Peak memory usage
- Memory per document
- Memory leak detection

## Interpreting Results

### Sample Output

```
benchmarking tests
name                              time (ms)     std dev       rounds  repeats
---------------------------------------------------------------------------
test_ingest_single_document       150.5         12.3          5       3
test_batch_ingest_documents       850.2         45.6          5       3
test_search_latency               45.8          8.2           5       3
```

### Key Metrics

| Metric | Meaning | Good | Concerning |
|--------|---------|------|------------|
| Mean time | Average operation time | < 200ms | > 500ms |
| Std dev | Variability | < 10% of mean | > 30% of mean |
| p95 latency | 95th percentile | < 300ms | > 1000ms |
| Memory usage | RAM consumption | < 2GB | > 4GB |

### Performance Regression Detection

A regression is detected when:

- Mean time increases by > 10%
- p95 latency increases by > 20%
- Memory usage increases by > 15%

```bash
# Compare against baseline
pytest benchmarks/ --benchmark-only --benchmark-compare

# Show only regressions
pytest benchmarks/ --benchmark-only --benchmark-compare --benchmark-only-failures
```

## Creating New Benchmarks

### Basic Benchmark Structure

```python
import pytest

def test_operation(benchmark, fixture1, fixture2):
    """Benchmark description."""
    def operation():
        # Code to benchmark
        result = some_function()
        return result
    
    # Run benchmark
    result = benchmark(operation)
    
    # Optional: report custom metrics
    print(f"\nCustom metric: {result}")
```

### Best Practices

1. **Use fixtures** for setup/teardown
2. **Minimize overhead** in benchmarked code
3. **Run multiple rounds** for statistical significance
4. **Isolate dependencies** (mock external services)
5. **Document expected ranges** in docstrings

### Example: Adding a New Benchmark

```python
# benchmarks/test_embedding_benchmarks.py
import pytest

def test_embedding_generation(benchmark):
    """Benchmark embedding generation for 100 text snippets."""
    texts = [f"Test text {i}" for i in range(100)]
    
    def generate_embeddings():
        from secondbrain.embedding import LocalEmbeddingGenerator
        embedder = LocalEmbeddingGenerator()
        return embedder.generate_batch(texts)
    
    result = benchmark(generate_embeddings)
    
    print(f"\nEmbeddings generated: {len(result)}")
    print(f"Average time per embedding: {result.stats['mean']/100*1000:.2f}ms")
```

## Continuous Benchmarking

### GitHub Actions Example

```yaml
name: Performance Benchmarks

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run benchmarks
        run: pytest benchmarks/ --benchmark-only --benchmark-json=benchmark.json
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: benchmark.json
```

### Performance Gates

Set thresholds to fail CI on regressions:

```python
# conftest.py
import pytest

def pytest_configure(config):
    if config.getoption("--benchmark-only"):
        # Set performance thresholds
        config.thresholds = {
            "max_mean_time": 200,  # ms
            "max_memory": 2048,    # MB
        }
```

## Troubleshooting Benchmarks

### No Data Reported

**Cause**: Benchmark didn't complete or fixture setup failed

**Solution**:
```bash
# Run without --benchmark-only to see errors
pytest benchmarks/ -v

# Check fixture setup
pytest benchmarks/ --fixtures
```

### High Variability

**Cause**: System load, background processes, thermal throttling

**Solution**:
- Run benchmarks on idle system
- Increase `--benchmark-rounds`
- Use `--benchmark-warmup` for JIT languages

### Comparison Failures

**Cause**: Benchmark names changed or results missing

**Solution**:
```bash
# Clear old results
rm -rf .benchmarks/

# Start fresh baseline
pytest benchmarks/ --benchmark-only --benchmark-save=baseline
```

## Best Practices

### Do's

✅ Run benchmarks on representative hardware  
✅ Use realistic test data  
✅ Run multiple times to establish baseline  
✅ Document expected performance ranges  
✅ Automate in CI/CD pipeline  
✅ Monitor trends over time  

### Don'ts

❌ Benchmark on overloaded systems  
❌ Use synthetic data that doesn't match production  
❌ Ignore outliers without investigation  
❌ Compare across different hardware configurations  
❌ Benchmark without proper warmup  

## Related Resources

- [pytest-benchmark documentation](https://pytest-benchmark.readthedocs.io/)
- [Performance Baselines](../architecture/PERFORMANCE.md)
- [Performance Guide](../user-guide/performance-guide.md)
