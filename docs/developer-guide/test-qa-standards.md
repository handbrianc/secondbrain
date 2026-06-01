# Test Quality Gates - CI/CD Configuration

## Overview

This document describes the test quality gates implemented in the SecondBrain CI/CD pipeline to ensure test quality, coverage, and performance standards are maintained.

## Quality Gates

### 1. Coverage Threshold

**Requirement:** 80% code coverage minimum

**Enforcement:**
```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "--cov-fail-under=80"
```

**CI/CD Check:**
- Integration tests must achieve ≥80% coverage
- Failing coverage blocks merge to main branch
- Coverage reports uploaded to Codecov for trend tracking

### 2. Flaky Test Detection

**Configuration:**
```yaml
# .github/workflows/test-quality-gates.yml
- name: Run tests with flaky detection
  run: |
    pytest -m "flaky" \
      --reruns=3 \
      --reruns-delay=2
```

**Requirements:**
- Tests marked with `@pytest.mark.flaky` automatically retry 3 times
- 2-second delay between retries
- Persistent failures are flagged for investigation

### 3. Mutation Testing

**Configuration:**
```yaml
- name: Run mutation testing (sample)
  run: |
    mutmut run --paths-to-mutate secondbrain.rag.factory
    mutmut results
```

**Requirements:**
- Mutation testing runs on critical modules
- Target mutation score: ≥80%
- Full mutation testing runs weekly (not on every PR)

### 4. Performance Baselines

**Configuration:**
```yaml
- name: Run performance tests
  run: |
    pytest -m "performance" \
      --benchmark-autosave \
      --benchmark-compare
```

**Requirements:**
- Performance tests compared against baseline
- No regression >10% without approval
- Benchmarks stored as artifacts

### 5. Test Markers

**Required Markers:**
- `unit` - Fast unit tests (run on every PR)
- `integration` - Integration tests (require services)
- `flaky` - Known flaky tests (auto-retry)
- `performance` - Performance benchmarks
- `slow` - Slow tests (>1s execution)

**Execution Strategy:**
```bash
# Fast path (every commit)
pytest -m "unit"

# Full path (PR to main)
pytest -m "unit or integration"

# Performance (scheduled)
pytest -m "performance"
```

## GitHub Actions Workflow

**Location:** `.github/workflows/test-quality-gates.yml`

**Triggers:**
- Push to `main` and `develop` branches
- Pull requests to `main` and `develop`

**Jobs:**
1. **test-quality** - Runs on Python 3.11 and 3.12
   - Unit tests
   - Integration tests with coverage
   - Mutation testing (sample)
   - Coverage upload to Codecov

2. **flaky-test-detection** - Dedicated flaky test runner
   - Retry logic for known flaky tests
   - Failure reporting

3. **performance-baseline** - Performance tracking
   - Benchmark execution
   - Comparison against baseline
   - Artifact storage

## Coverage Reporting

### Tools
- **pytest-cov** - Coverage collection
- **Codecov** - Coverage reporting and trending
- **Coverage HTML** - Local detailed reports

### Commands
```bash
# Generate coverage report
pytest --cov=secondbrain --cov-report=html

# View in browser
open htmlcov/index.html

# Terminal summary
pytest --cov=secondbrain --cov-report=term-missing
```

### Coverage Targets
| Module | Current | Target | Priority |
|--------|---------|--------|----------|
| Overall | 27.7% | 80% | Critical |
| factory.py | 0% | 80% | ✅ Complete |
| rag/pipeline.py | 8.8% | 70% | In Progress |
| domain/storage.py | 18.2% | 75% | Pending |
| circuit_breaker.py | 28% | 65% | Pending |

## Mutation Testing

### Setup
```bash
# Install
pip install mutmut

# Configure (already in pyproject.toml)
[tool.mutmut]
python_paths = ["src"]
test_command = "pytest {mutmut_test_file} -xvs"
```

### Execution
```bash
# Full mutation testing (slow, run weekly)
mutmut run

# Quick mutation testing (specific module)
mutmut run --paths-to-mutate secondbrain.rag.factory

# View results
mutmut results
mutmut show
```

### Interpretation
- **Killed** - Tests caught the mutation ✅
- **Survived** - Tests didn't catch mutation ❌ (improve tests)
- **Timeout** - Mutation caused timeout ⚠️ (adjust timeout)
- **Skipped** - Test was skipped ⚠️ (check configuration)

## Performance Baselines

### Setup
```bash
# Install pytest-benchmark
pip install pytest-benchmark

# Run benchmarks
pytest -m "performance" --benchmark-autosave

# Compare against baseline
pytest -m "performance" --benchmark-compare
```

### Marking Performance Tests
```python
import pytest

@pytest.mark.performance
@pytest.mark.benchmark(group="search")
def test_search_latency(benchmark):
    """Measure search latency."""
    result = benchmark(search_function, query)
    assert result is not None
```

### Baseline Management
```bash
# Save baseline
pytest --benchmark-save=baseline_v1

# Compare to baseline
pytest --benchmark-compare --benchmark-compare-fail=mean:10.0
```

## Troubleshooting

### Coverage Fails
**Problem:** Coverage below 80%

**Solution:**
1. Run `pytest --cov-report=html`
2. Open `htmlcov/index.html`
3. Identify uncovered lines (red)
4. Add tests for uncovered paths
5. Re-run tests

### Mutation Testing Fails
**Problem:** Mutation score too low

**Solution:**
1. Run `mutmut show` to see surviving mutations
2. Identify test gaps
3. Add targeted tests
4. Re-run mutation testing

### Performance Regression
**Problem:** Benchmark shows >10% regression

**Solution:**
1. Investigate root cause
2. Optimize code or update baseline
3. Document justification if regression is acceptable
4. Update baseline: `pytest --benchmark-reset`

### Flaky Tests
**Problem:** Tests fail intermittently

**Solution:**
1. Mark with `@pytest.mark.flaky`
2. Add retry logic
3. Investigate root cause
4. Fix underlying issue
5. Remove flaky marker when fixed

## Best Practices

1. **Run tests locally before pushing**
   ```bash
   pytest -m "not integration"  # Fast tests
   ```

2. **Check coverage before PR**
   ```bash
   pytest --cov=secondbrain --cov-report=term-missing
   ```

3. **Run mutation testing on critical modules**
   ```bash
   mutmut run --paths-to-mutate secondbrain.rag.factory
   ```

4. **Monitor Codecov trends**
   - Check coverage trends over time
   - Investigate coverage drops
   - Aim for gradual improvement

5. **Update baselines responsibly**
   - Only update after optimization or justified changes
   - Document baseline changes in PR

## Related Documentation

- [Mutation Testing Guide](./mutation-testing.md)
- [Testing Best Practices](./TESTING.md)
- [Running Tests](./RUNNING_TESTS.md)

---

**Last Updated:** May 30, 2026  
**Workflow Version:** 1.0.0  
**Coverage Target:** 80%  
**Mutation Target:** 80%
