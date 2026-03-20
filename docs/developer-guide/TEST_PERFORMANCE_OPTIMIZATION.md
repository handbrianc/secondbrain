# Test Performance Optimization

Optimize test execution speed for SecondBrain.

## Current Performance

| Profile | Duration | Workers |
|---------|----------|---------|
| Fast | ~5s | 4 |
| Integration | ~15s | 4 |
| Full | ~25s | 4 |

## Optimization Strategies

### Parallel Execution

```bash
# Use all available cores
pytest -n auto

# Specific worker count
pytest -n 8
```

### Test Selection

```bash
# Run only failed tests from last run
pytest --last-failed

# Run specific test file
pytest tests/test_config.py

# Run tests matching pattern
pytest -k "test_chunk"
```

### Skip Unnecessary Tests

```bash
# Exclude integration tests
pytest -m "not integration"

# Exclude slow tests
pytest -m "not slow"
```

### Caching

```bash
# Enable pytest cache
pytest --cache-clear  # Clear cache

# Show cached values
pytest --cache-show
```

## Test Configuration

### pyproject.toml

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
markers = [
    "slow: marks tests as slow",
    "integration: marks integration tests",
]
timeout = 60
```

### conftest.py

```python
import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: mark test as slow to run"
    )
```

## Benchmarking

### Setup

```bash
pip install pytest-benchmark
```

### Usage

```python
def test_performance(benchmark):
    result = benchmark(function_to_test)
    assert result is not None
```

### Run Benchmarks

```bash
pytest --benchmark-only
```

## Profiling

### CPU Profiling

```bash
python -m cProfile -o profile.out -m pytest
```

### Memory Profiling

```bash
pytest --memray
```

## Best Practices

1. **Keep tests fast** - Target < 1s per test
2. **Use fixtures efficiently** - Cache expensive setup
3. **Parallelize** - Use pytest-xdist
4. **Skip when possible** - Mark slow tests
5. **Mock external services** - Don't rely on network

## Troubleshooting

### Slow Tests

```bash
# Find slowest tests
pytest --durations=10
```

### Memory Leaks

```bash
# Track memory usage
pytest --memray --memray-bind=host
```

## Next Steps

- [Testing Guide](TESTING.md) - Complete testing guide
- [Code Standards](code-standards.md) - Performance-aware coding
