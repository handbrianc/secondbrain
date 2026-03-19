# Test Timeout Analysis & Optimization Report

## Executive Summary

**Problem**: Tests timeout at 120s limit with 519+ tests running on 4 parallel workers (`-n 4`)

**Root Causes Identified**:
1. **Circuit breaker tests** - 8 tests with `time.sleep(0.15)` each = ~1.2s+ per test
2. **Integration/E2E tests** - 14 slow tests + 18 integration tests involving real services
3. **No per-test timeout** - Single slow test can block entire worker
4. **pytest-cov + xdist overhead** - Coverage collection amplifies parallelization costs

---

## Problematic Test Categories

### 1. Circuit Breaker Tests (HIGH PRIORITY)

**File**: `tests/test_utils/test_circuit_breaker.py`

**Issue**: 8 tests with hardcoded `time.sleep(0.15)` calls for recovery timeout testing

```python
# Lines 132, 152, 178, 239, 299 - all use time.sleep(0.15)
def test_open_to_half_open_after_timeout(self):
    config = CircuitBreakerConfig(recovery_timeout=0.1)  # 100ms
    cb = CircuitBreaker(config)
    # ... open circuit ...
    time.sleep(0.15)  # WAIT - blocks test thread
    assert cb.is_allowed() is True
```

**Impact**: ~1.2s+ cumulative sleep time across 8 tests
**Marker**: `@pytest.mark.circuit_breaker`

**Recommendation**:
- Mock time progression instead of real sleeps
- Reduce recovery timeout to 0.01s for tests
- Add `@pytest.mark.slow` to these tests

---

### 2. End-to-End Integration Tests (CRITICAL)

**Files**:
- `tests/test_integration/test_end_to_end.py` - 4 tests marked `@pytest.mark.slow @pytest.mark.integration`
- `tests/test_integration/test_e2e_ingestion.py` - 2 integration tests
- `tests/test_integration/test_e2e_search.py` - 5 integration tests
- `tests/test_document/test_e2e_pdf_ingestion.py` - 10 tests marked `@pytest.mark.slow @pytest.mark.integration`

**Issue**: Tests involve real MongoDB/SentenceTransformers connections

```python
# test_e2e_pdf_ingestion.py:96-108
def test_embedding_generation(self):
    embedding_gen = LocalEmbeddingGenerator()
    if not embedding_gen.validate_connection():
        pytest.skip("SentenceTransformers not available")
    # Real model loading + inference - 5-10s per test
```

**Impact**: Each E2E test can take 5-15s with real services
**Total**: ~100-150s if all integration tests run

**Recommendation**:
- Ensure `-m "not integration"` is default (already configured)
- Add per-test timeouts: `@pytest.mark.timeout(10)`
- Mock external services more aggressively

---

### 3. Slow Tests Distribution

| Category | Count | Estimated Duration | Total Time |
|----------|-------|-------------------|------------|
| `@pytest.mark.slow` | 14 | 5-15s each | 70-210s |
| `@pytest.mark.integration` | 18 | 2-10s each | 36-180s |
| Circuit breaker | 8 | 1-2s each | 8-16s |
| Property-based (hypothesis) | 10 | 0.5-2s each | 5-20s |

---

## Configuration Issues

### Current pyproject.toml Settings

```toml
[tool.pytest.ini_options]
addopts = "-m 'not slow' -n 4"  # Excludes slow, 4 workers
asyncio_mode = "auto"
```

**Problems**:
1. ❌ No per-test timeout configuration
2. ❌ No xdist worker timeout (`--test-timeout`)
3. ❌ Circuit breaker tests not marked as slow
4. ❌ Hypothesis still uses default 10 examples (may be too many)

---

## Recommended Optimizations

### 1. Add Per-Test Timeouts (CRITICAL)

Install pytest-timeout and configure:

```toml
[tool.pytest.ini_options]
addopts = "-m 'not slow' -n 4 --timeout=60"  # 60s per test
asyncio_mode = "auto"

[tool.pytest-timeout]
timeout = 60
timeout_method = "thread"  # More aggressive than signal
```

**Impact**: Prevents single test from blocking worker indefinitely

---

### 2. Mock Time in Circuit Breaker Tests (HIGH PRIORITY)

Replace `time.sleep()` with `unittest.mock.patch`:

```python
# tests/test_utils/test_circuit_breaker.py
from unittest.mock import patch
import time

@pytest.mark.circuit_breaker
class TestCircuitBreakerStateTransitions:
    def test_open_to_half_open_after_timeout(self):
        config = CircuitBreakerConfig(recovery_timeout=0.1)
        cb = CircuitBreaker(config)
        
        # Open the circuit
        for _ in range(5):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        # MOCK time progression instead of real sleep
        with patch('secondbrain.utils.circuit_breaker.time.time') as mock_time:
            mock_time.side_effect = [0, 0.2]  # Simulate time passing
            assert cb.is_allowed() is True
            assert cb.state == CircuitState.HALF_OPEN
```

**Impact**: Reduces 0.15s sleeps to instant mock calls

---

### 3. Mark Circuit Breaker Tests as Slow

```python
# tests/test_utils/test_circuit_breaker.py
@pytest.mark.circuit_breaker
@pytest.mark.slow  # Add this
class TestCircuitBreakerStateTransitions:
```

**Impact**: Excluded from fast test runs by default

---

### 4. Optimize Hypothesis for CI

```python
# tests/test_property_based/test_properties.py
# Already optimized to max_examples=10, but add CI override
@settings(max_examples=10, deadline=500)  # Add deadline
def test_sanitize_preserves_valid_input(self, query: str):
```

Add to pyproject.toml:
```toml
[tool.pytest.ini_options]
markers = [
    # ... existing markers
    "hypothesis: marks tests as property-based testing",
]
```

Run hypothesis tests separately:
```bash
# Fast profile - skip hypothesis
pytest -m "not slow and not hypothesis" -n 4

# Full validation - include hypothesis
pytest -m "not slow" -n 4
```

---

### 5. Reduce XDist Workers for Coverage

When running with coverage, reduce workers to avoid coverage collection issues:

```bash
# Fast feedback (no coverage)
pytest -m "not slow" -n 4 --no-cov

# With coverage (fewer workers)
pytest -m "not slow" -n 2 --cov=secondbrain

# CI profile
pytest -m "not slow" -n 8 --cov=secondbrain --cov-report=xml
```

Update pyproject.toml defaults:
```toml
[tool.pytest.ini_options]
# Default: fast profile for local dev (no coverage, 4 workers)
addopts = "-m 'not slow' -n 4 --no-cov --timeout=60"
```

---

### 6. Add Test Grouping for Better Parallelization

Use `--dist loadscope` to group related tests on same worker:

```toml
[tool.pytest.ini_options]
addopts = "-m 'not slow' -n 4 --no-cov --timeout=60 --dist loadscope"
```

**Benefit**: Prevents fixture setup/teardown overhead from multiplying

---

### 7. Mock External Services Aggressively

For integration tests that don't need real services:

```python
# tests/test_integration/test_e2e_search.py
@pytest.mark.integration
@patch("secondbrain.search.LocalEmbeddingGenerator")
@patch("secondbrain.search.VectorStorage")
@patch("pymongo.MongoClient")  # Add MongoDB mock
def test_search_e2e(self, mock_client, mock_storage, mock_embed):
    # Completely mock all external dependencies
```

---

## Optimized Test Commands

### For Developers (Local)

```bash
# Fast profile - unit tests only, no coverage
pytest -m "not slow and not integration and not hypothesis" -n 4 --no-cov --timeout=30

# With coverage (slower)
pytest -m "not slow and not integration" -n 2 --cov=secondbrain --timeout=60
```

### For CI/CD

```bash
# PR validation - skip integration, include hypothesis
pytest -m "not integration" -n 8 --cov=secondbrain --cov-report=xml --timeout=60

# Nightly build - full suite
pytest -n 8 --cov=secondbrain --cov-report=html --timeout=120
```

### For Release Validation

```bash
# Full E2E with real services
pytest -m "not hypothesis" --timeout=180

# Just slow tests
pytest -m "slow" --timeout=180
```

---

## Expected Performance Improvements

| Scenario | Current | Optimized | Speedup |
|----------|---------|-----------|---------|
| **Fast tests** (unit only) | ~42s | ~8s | **5x faster** |
| **With coverage** | ~42s | ~15s | **3x faster** |
| **Circuit breaker** | ~1.2s sleeps | ~0.05s | **24x faster** |
| **Full suite** | 120s+ timeout | ~90s | **30% faster** |

---

## Implementation Checklist

### Phase 1: Immediate Fixes (High Impact)

- [ ] Add `pytest-timeout` to dev dependencies
- [ ] Configure `--timeout=60` in pyproject.toml
- [ ] Add `@pytest.mark.slow` to circuit breaker tests
- [ ] Mock `time.sleep()` in circuit breaker tests

### Phase 2: Configuration Tuning

- [ ] Update `addopts` to include `--no-cov --timeout=60`
- [ ] Add `--dist loadscope` for better parallelization
- [ ] Separate hypothesis tests with marker

### Phase 3: Test Optimization

- [ ] Refactor circuit breaker tests to mock time
- [ ] Add per-test `@pytest.mark.timeout(10)` to critical tests
- [ ] Review integration tests for unnecessary real service calls

### Phase 4: Documentation

- [ ] Update README with new test commands
- [ ] Document test profiles in TESTING_OPTIMIZATION.md
- [ ] Add CI/CD examples with optimized commands

---

## Files Requiring Changes

1. **pyproject.toml**
   - Add pytest-timeout dependency
   - Update `addopts`
   - Add timeout configuration

2. **tests/test_utils/test_circuit_breaker.py**
   - Add `@pytest.mark.slow` to all tests
   - Mock time progression instead of real sleeps

3. **tests/conftest.py**
   - Add timeout fixture defaults
   - Add circuit_breaker marker to fixture setup

4. **README.md**
   - Update test commands section

5. **tests/TESTING_OPTIMIZATION.md**
   - Add timeout configuration section
   - Update performance tables

---

## Monitoring & Validation

After implementing changes, track:

```bash
# Measure individual test times
pytest --durations=20  # Show 20 slowest tests

# Profile parallel execution
pytest -n 4 --dist loadscope --log-cli-level=INFO

# Check for timeouts
pytest --timeout=60 -v 2>&1 | grep -i timeout
```

Expected outcome: No tests should exceed 60s, most unit tests under 1s.
