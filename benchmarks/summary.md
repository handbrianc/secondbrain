# Test Suite Performance Benchmarks

## Worker Count Comparison

| Workers | Total Runtime | Relative Speed | Notes |
|---------|--------------|----------------|-------|
| 4       | 75.86s       | 0.93x          | Slower, underutilized |
| 8       | 70.27s       | 1.00x (baseline) | **Recommended default** |
| 12      | 66.73s       | 1.05x          | **Fastest**, best for high-performance systems |
| 16      | 70.48s       | 1.00x          | Diminishing returns |

## Analysis

**Best Configuration:** 12 workers
- 5% faster than default 8 workers
- Optimal balance between parallelism and resource contention
- Recommended for systems with 16-32GB RAM

**Recommended Defaults:**
- **4 workers**: Low-memory systems (<8GB RAM)
- **8 workers**: Standard systems (8-16GB RAM) ← Current default
- **12 workers**: High-performance systems (16-32GB RAM) ← Fastest
- **16 workers**: Only for E2E tests with isolated databases

## Test Categorization Performance

### Fast Tests (not e2e and not slow)
- **Count**: ~1,352 tests (96% of total)
- **Expected runtime**: ~20-25s with 8 workers
- **Use case**: Development workflow, pre-commit hooks

### E2E Tests
- **Count**: ~24 tests (2% of total)
- **Expected runtime**: ~15-20s with 8 workers
- **Use case**: Full integration validation, CI/CD

### Chaos Tests
- **Count**: ~28 tests (2% of total)
- **Expected runtime**: ~10-15s with 8 workers
- **Use case**: Reliability testing, failure injection validation

### OCR Tests
- **Count**: ~1 test (<1% of total)
- **Expected runtime**: ~3s
- **Use case**: Image processing validation

## Optimization Impact

### Before Optimization
- Total runtime: ~70s
- No test categorization
- All tests run every time

### After Optimization
- **Fast tests only**: ~20-25s (65% reduction)
- **Full suite**: ~67s (5% reduction from fixture optimizations)
- **E2E tests**: ~15-20s (selective execution)

## Usage Examples

```bash
# Development: Run only fast unit tests
pytest -m "not e2e and not slow"

# Full test suite (CI/CD)
pytest

# E2E tests only
pytest -m "e2e"

# Show slowest tests
pytest --durations=10

# Benchmark specific worker count
pytest -n 12 --durations=0
```

## Recommendations

1. **Use 12 workers** for best performance on high-performance systems
2. **Run fast tests during development** with `pytest -m "not e2e and not slow"`
3. **Run full suite in CI/CD** before merges
4. **Run E2E tests separately** when validating new features
5. **Monitor test durations** with `pytest --durations=10` regularly

## Hardware Requirements

| Workers | RAM Required | CPU Cores | Use Case |
|---------|--------------|-----------|----------|
| 4       | 4-8GB        | 4+        | Laptop, low-memory systems |
| 8       | 8-16GB       | 8+        | Standard development machine |
| 12      | 16-32GB      | 12+       | High-performance workstation |
| 16      | 32GB+        | 16+       | CI/CD servers, dedicated test machines |
