# Test Performance Baselines

## Overview

This document establishes performance baselines for SecondBrain test execution to ensure tests remain fast and reliable.

## Test Execution Time Targets

### Unit Tests
- **Individual test**: < 1 second
- **Test file** (10-20 tests): < 30 seconds
- **Module suite** (50+ tests): < 2 minutes
- **Full test suite**: < 15 minutes (with parallel execution)

### Integration Tests
- **Individual test**: < 10 seconds
- **Test file**: < 2 minutes
- **Integration suite**: < 10 minutes

## Performance Metrics

### Query Operations
| Metric | Target | Tolerance |
|--------|--------|-----------|
| Simple query | < 50ms | ±20% |
| Query with history | < 100ms | ±20% |
| Query with rewrites | < 150ms | ±20% |

### Ingestion Operations
| Metric | Target | Tolerance |
|--------|--------|-----------|
| Single document (text) | < 500ms | ±30% |
| Single document (PDF) | < 2s | ±30% |
| Batch ingestion (10 docs) | < 10s | ±30% |

### Search Operations
| Metric | Target | Tolerance |
|--------|--------|-----------|
| Top-5 search | < 100ms | ±20% |
| Top-10 search | < 150ms | ±20% |
| Search with filters | < 200ms | ±20% |

## Test Timing Tolerances

Tests that measure execution time should use appropriate tolerance ranges:

```python
def test_query_performance(self):
    """Test query completes within acceptable time."""
    start = time.time()
    result = perform_query("test")
    duration = time.time() - start
    
    # Allow 20% variance for system load
    assert 0.040 <= duration <= 0.060, f"Query took {duration:.3f}s, expected ~0.05s"
```

## Parallel Execution

### xdist Configuration
```ini
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
addopts = "-n auto --dist=loadfile"
```

### Expected Speedup
| Workers | Speedup Factor |
|---------|---------------|
| 4 | 3.5x |
| 8 | 6.5x |
| 16 | 12x |
| auto (CPU count) | Optimal |

## Performance Test Categories

### Fast Tests (< 1s)
```python
@pytest.mark.fast
def test_quick_operation(self):
    """Test that should complete in < 1 second."""
    ...
```

### Medium Tests (1-5s)
```python
@pytest.mark.slow
def test_medium_operation(self):
    """Test that takes 1-5 seconds."""
    ...
```

### Slow Tests (> 5s)
```python
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_long_operation(self):
    """Test that takes > 5 seconds (max 30s)."""
    ...
```

## Monitoring Performance Regressions

### CI/CD Integration
```yaml
# GitHub Actions example
- name: Run performance tests
  run: pytest tests/test_performance.py -v
  env:
    PYTEST_ADDOPTS: "--json-report --json-report-file=report.json"
```

### Performance Report
Track these metrics in CI:
- Total execution time
- Slowest 10 tests
- Tests exceeding thresholds
- Trend over time

## Baseline Measurement Commands

### Measure Individual Test
```bash
pytest tests/test_module.py::TestClass::test_method -v --durations=0
```

### Measure Test File
```bash
pytest tests/test_module.py -v --durations=10
```

### Measure Full Suite
```bash
pytest -v --durations=20 --json-report
```

### Compare Performance
```bash
# Baseline
pytest --json-report --json-report-file=baseline.json

# Current
pytest --json-report --json-report-file=current.json

# Compare
python scripts/compare-performance.py baseline.json current.json
```

## Performance Budget

### Per-Test Budget
- **Computation**: < 80% of time budget
- **I/O**: < 15% of time budget  
- **Overhead**: < 5% of time budget

### Test Suite Budget
| Suite | Budget | Warning | Critical |
|-------|--------|---------|----------|
| Unit tests | 10 min | 12 min | 15 min |
| Integration | 15 min | 18 min | 20 min |
| Full suite | 25 min | 30 min | 35 min |

## Optimization Guidelines

### When Tests Exceed Budget
1. **Profile first**: `pytest --profile-svg`
2. **Identify bottlenecks**: Look for I/O, slow mocks, excessive setup
3. **Optimize**:
   - Use faster mocks
   - Reduce test data size
   - Parallelize where possible
   - Cache expensive operations
4. **Verify**: Re-run and confirm improvement

### Common Optimizations
```python
# ❌ Slow: Real I/O
def test_with_real_file(self):
    with open("large_file.txt") as f:
        result = process(f.read())

# ✅ Fast: Mocked I/O
@pytest.fixture
def mock_large_file(mocker):
    mocker.patch("builtins.open", return_value=MagicMock(read=MagicMock(return_value="x" * 10000)))

def test_with_mocked_file(self, mock_large_file):
    with open("large_file.txt") as f:
        result = process(f.read())
```

## Performance Test Files

| File | Purpose | Tests | Target Time |
|------|---------|-------|-------------|
| `test_performance.py` | Metrics collection | 8 | < 10s |
| `test_multicore_performance.py` | Parallel ingestion | 12 | < 30s |
| `test_*.py` (all) | Regular tests | ~1800 | < 15min total |

## Maintenance

### Monthly Review
- [ ] Check for tests exceeding budgets
- [ ] Update baselines if system changes
- [ ] Remove or optimize consistently slow tests
- [ ] Verify parallel execution efficiency

### When to Update Baselines
- Hardware upgrades
- Major dependency updates
- Algorithm changes
- After optimization efforts

---

**Last Updated:** 2026-05-30  
**Version:** 1.0  
**Maintained By:** Test Infrastructure Team
