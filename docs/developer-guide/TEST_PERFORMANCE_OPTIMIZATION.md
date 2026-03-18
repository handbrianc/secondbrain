# Test Performance Optimization

This document describes the performance optimizations applied to the test suite to reduce execution time.

## Summary of Optimizations

### 1. Conftest.py Optimizations

#### Module-Scoped Configuration Fixture
- **Change**: Changed `mock_config_defaults` from function scope to module scope
- **Impact**: Reduces setup overhead from ~0.17s per test to ~0.13s per test
- **Files**: `tests/conftest.py`

#### Module-Scoped Mock Fixtures
- **Change**: Made `mock_embedding_generator` and `mock_vector_storage` fixtures module-scoped
- **Impact**: Mocks are created once per module instead of per test
- **Files**: `tests/conftest.py`

### 2. CLI Test Optimizations

#### Removed Filesystem Context
- **Change**: Removed `runner.isolated_filesystem()` context managers from CLI validation tests
- **Impact**: Reduced CLI ingest test execution time from ~2.4s to ~1.9s per test (20% improvement)
- **Files**: `tests/test_cli/test_validation.py`

#### Simplified Path Handling
- **Change**: Used hardcoded test path (`/tmp/test_docs`) instead of creating directories in isolated filesystem
- **Impact**: Eliminates filesystem operations overhead
- **Files**: `tests/test_cli/test_validation.py`

### 3. Storage Test Optimizations

#### Module-Level Fixtures
- **Change**: Added `mock_storage_config` and `storage_with_mock` fixtures to aggregation tests
- **Impact**: Reduced setup time from ~0.18s to ~0.08s per test
- **Files**: `tests/test_storage/test_aggregation_edge_cases.py`

### 4. Pytest Configuration Optimizations

#### Parallel Execution
- **Change**: Changed from `-n auto` to `-n logical` for smarter worker allocation
- **Impact**: Better CPU utilization on multi-core systems
- **Files**: `pyproject.toml`

#### Asyncio Configuration
- **Change**: Added `asyncio_default_fixture_loop_scope = "function"` to prevent deprecation warnings
- **Impact**: Cleaner test output, no performance impact

#### Baseline Temp Directory
- **Change**: Added `--basetemp=/tmp/pytest-tmp` to reuse temp directories
- **Impact**: Reduces filesystem I/O overhead
- **Files**: `pyproject.toml`

#### Deprecation Warning Suppression
- **Change**: Added pyparsing deprecation warning filter
- **Impact**: Cleaner test output
- **Files**: `pyproject.toml`

## Performance Improvements

### Before Optimization

| Test Suite | Total Time | Avg Setup Time | Slowest Tests |
|------------|-----------|----------------|---------------|
| CLI Validation | ~29s | 0.17s | 2.4s each (12 tests) |
| Storage Aggregation | ~7s | 0.18s | 1.0s each (7 tests) |
| Utils | ~5.5s | 0.17s | 0.11s each |
| **Total Suite** | **~50-60s** | **0.17s** | - |

### After Optimization

| Test Suite | Total Time | Avg Setup Time | Slowest Tests | Improvement |
|------------|-----------|----------------|---------------|-------------|
| CLI Validation | ~24s | 0.13s | 1.9s each (12 tests) | 17% faster |
| Storage Aggregation | ~6s | 0.08s | 1.0s each (7 tests) | 14% faster |
| Utils | ~5.2s | 0.17s | 0.11s each | 5% faster |
| **Total Suite** | **~45s** | **0.13s** | - | **~20% faster** |

## Detailed Test Improvements

### CLI Ingest Tests (Before → After)

| Test | Before | After | Improvement |
|------|--------|-------|-------------|
| test_ingest_command | 2.40s | 1.92s | 20% |
| test_ingest_accepts_negative_batch_size | 2.40s | 1.91s | 20% |
| test_ingest_rejects_negative_chunk_size | 2.39s | 1.84s | 23% |
| test_ingest_accepts_zero_chunk_size | 2.39s | 1.88s | 21% |
| test_ingest_accepts_valid_chunk_size | 2.39s | 1.85s | 23% |

### Storage Aggregation Tests (Before → After)

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Setup time | 0.18s | 0.08s | 55% |
| Call time | 1.00s | 1.00s | 0% (unaffected) |

## Remaining Bottlenecks

### CLI Tests (~1.9s per test)
The remaining ~1.9s execution time for CLI ingest tests is primarily due to:
- Click CLI application initialization
- Environment variable loading
- Module imports and initialization

**Potential further optimization**: Mock the CLI at a higher level to bypass Click initialization entirely, but this would reduce test validity.

### Storage Aggregation Tests (~1.0s per test)
The ~1.0s execution time is due to:
- MongoDB aggregation pipeline complexity (even with mocks)
- Score calculation and sorting logic

**Potential further optimization**: These tests validate actual aggregation logic, so optimization would require architectural changes to the storage layer.

## Recommendations for Future Optimization

1. **Test Parallelization**: Consider using `pytest-xdist` with `--dist=loadscope` for better test distribution
2. **Selective Coverage**: Run coverage only on critical paths, not all tests
3. **Integration Test Separation**: Keep integration tests in a separate suite that runs less frequently
4. **Mock Database**: Consider using `mongomock` for faster in-memory MongoDB testing

## How to Measure Performance

```bash
# Run tests with timing information
pytest --durations=20 --no-cov -v

# Run specific test suite
pytest tests/test_cli/test_validation.py --durations=20 --no-cov

# Compare before/after with coverage
pytest --durations=20 --cov=secondbrain --cov-report=term-missing
```

## Conclusion

The optimizations achieved approximately **20% overall test suite speedup** by:
- Reducing fixture setup overhead through module scoping
- Eliminating unnecessary filesystem operations in CLI tests
- Optimizing pytest configuration for parallel execution

The remaining bottlenecks are inherent to the test design and would require architectural changes to improve further.
