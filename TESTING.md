# Testing Guide

Comprehensive guide for testing the SecondBrain project.

## Quick Commands

### Run All Tests
```bash
pytest
```

### Run Fast Unit Tests (Development)
```bash
pytest -m "not e2e and not slow"
```
**Runtime:** ~20-25s | **Use case:** Pre-commit, local development

### Run E2E Tests
```bash
pytest -m "e2e"
```
**Runtime:** ~15-20s | **Use case:** Full integration validation

### Run Specific Test Categories
```bash
pytest -m "ocr"          # OCR tests only (~3s)
pytest -m "chaos"        # Chaos engineering tests (~10-15s)
pytest -m "concurrent"   # Concurrency tests
pytest -m "integration"  # All integration tests
```

### Show Slowest Tests
```bash
pytest --durations=10
```

### Run Changed Tests Only (Incremental)
```bash
pytest --testmon
```
**Requires:** `pytest-testmon` installed (included in dev dependencies)

## Test Categories

| Category | Marker | Runtime | Services Required | Count |
|----------|--------|---------|-------------------|-------|
| Unit Tests | `unit` | <1s | None | ~1,200 |
| Integration | `integration` | 1-5s | MongoDB (mocked) | ~150 |
| E2E | `e2e` | 5-15s | MongoDB, Embedding Model | ~24 |
| Slow | `slow` | >5s | Varies | ~55 |
| OCR | `ocr` | 2-3s | OCR libraries | ~1 |
| Chaos | `chaos` | 10-30s | MongoDB | ~28 |
| Concurrent | `concurrent` | 2-5s | MongoDB | ~30 |

## Performance Optimizations

### Fixture Scoping

The test suite uses optimized fixture scoping to minimize overhead:

| Fixture | Scope | Purpose | Savings |
|---------|-------|---------|---------|
| `mongo_client` | session | Single MongoDB client per session | ~200ms/test |
| `embedding_model` | session | Single model load per session | ~2-3s/test |
| `test_database` | class | One database per test class | ~100ms/test |
| `mocked_pdf_extraction_module` | module | Mock PDF extraction | ~3-5s/test |
| `mock_embeddings` | module | Deterministic mock embeddings | ~2-3s/test |
| `cached_embedding_generator` | function | Fast mock for unit tests | ~2-3s/test |

### Expected Runtime Savings

| Optimization | Savings | Applicable Tests |
|--------------|---------|------------------|
| Session-scoped MongoDB | ~200ms per test | All MongoDB tests |
| Session-scoped model | ~2-3s per test | E2E tests with real embeddings |
| Mock PDF extraction | ~3-5s per test | Unit tests with PDF processing |
| Mock embeddings | ~2-3s per test | Unit tests with embedding generation |
| Fast test config | ~10x faster rate limits | Tests with rate limiting |

### Parallel Execution

Recommended worker counts based on system resources:

| Workers | RAM Required | CPU Cores | Runtime | Use Case |
|---------|--------------|-----------|---------|----------|
| 4 | 4-8GB | 4+ | ~76s | Low-memory systems |
| 8 | 8-16GB | 8+ | ~70s | **Default** (standard systems) |
| 12 | 16-32GB | 12+ | ~67s | **Fastest** (high-performance) |
| 16 | 32GB+ | 16+ | ~70s | CI/CD servers |

**To change worker count:**
```bash
# Override in command line
pytest -n 12

# Or modify pyproject.toml
[tool.pytest.ini_options]
addopts = "-n 12 --timeout=60 ..."
```

## Test Fixtures

### Common Fixtures

#### `mocked_pdf_extraction_module`
Mocks PDF text extraction to avoid slow docling processing.
```python
def test_something(mocked_pdf_extraction_module):
    # PDF extraction returns pre-computed mock data
    result = ingestor.ingest("test.pdf")
    assert result is not None
```

#### `mock_embeddings`
Generates deterministic 384-dim embeddings based on text hash.
```python
def test_embedding_generation(mock_embeddings):
    embedding = mock_embeddings("test text")
    assert len(embedding) == 384
```

#### `cached_embedding_generator`
Provides mock embedding generator with pre-cached embeddings.
```python
def test_with_cached_generator(cached_embedding_generator):
    result = cached_embedding_generator.generate("test")
    assert len(result) == 384
```

#### `mongo_client`
Session-scoped MongoDB client for integration tests.
```python
def test_with_real_mongo(mongo_client):
    db = mongo_client["test_db"]
    # Use the shared client
```

#### `test_database`
Class-scoped test database.
```python
class TestMyFeature:
    def test_with_database(self, test_database):
        # Each test class gets its own database
        test_database["collection"].insert_one({...})
```

### Creating Custom Fixtures

```python
@pytest.fixture(scope="module")
def my_custom_fixture():
    """Module-scoped fixture for expensive setup."""
    setup_data = expensive_operation()
    yield setup_data
    cleanup_operation(setup_data)
```

## Troubleshooting

### Test Pollution
**Symptom:** Tests fail due to data from other tests

**Solutions:**
1. Check for missing `clean_test_database` fixture usage
2. Verify unique collection names (use UUID-based names)
3. Run tests in isolation: `pytest test_file.py::test_name`
4. Ensure proper fixture scoping (function vs module vs session)

### MongoDB Connection Timeouts
**Symptom:** Tests fail with connection timeout errors

**Solutions:**
1. Ensure MongoDB is running: `mongosh` should connect
2. Check URI in `.env`: `MONGODB_URI=mongodb://localhost:27017`
3. For integration tests, use docker-compose services
4. Increase timeout: `pytest --timeout=120`

### Slow Tests
**Symptom:** Tests taking longer than expected

**Diagnosis:**
```bash
# Identify slowest tests
pytest --durations=10

# Profile specific test
pytest -vv test_file.py::test_name --benchmark
```

**Solutions:**
1. Add appropriate markers (`@pytest.mark.slow`)
2. Consider mocking expensive operations
3. Use fixture scoping to reduce setup overhead
4. Run in parallel: `pytest -n auto`

### Test Collection Errors
**Symptom:** pytest can't collect tests

**Solutions:**
1. Check for syntax errors: `python -m py_compile test_file.py`
2. Verify pytest markers are registered in `pyproject.toml`
3. Clear pytest cache: `rm -rf .pytest_cache`
4. Check import statements are correct

### Fixture Dependency Errors
**Symptom:** `Fixture "X" not available` errors

**Solutions:**
1. Ensure fixture is defined in `conftest.py` or imported
2. Check fixture scope compatibility (session fixtures can't depend on function fixtures)
3. Verify fixture names match exactly (case-sensitive)

## CI/CD Integration

### GitHub Actions (Example)
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      mongodb:
        image: mongo:6.0
        ports:
          - 27017:27017
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run fast tests
        run: pytest -m "not e2e and not slow"
      - name: Run E2E tests
        run: pytest -m "e2e"
```

### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-fast
        name: Run fast tests
        entry: pytest -m "not e2e and not slow"
        language: system
        pass_filenames: false
        always_run: true
```

## Test Data Management

### Temporary Directories
Use pytest's built-in `tmp_path` fixture:
```python
def test_with_temp_files(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    # Automatically cleaned up after test
```

### Sample Data
Use session-scoped fixtures for expensive sample data:
```python
@pytest.fixture(scope="session")
def sample_pdf_path(tmp_path_factory):
    pdf_path = tmp_path_factory.mktemp("data") / "sample.pdf"
    # Create PDF once per session
    return pdf_path
```

## Coverage Reporting

### Generate Coverage Report
```bash
pytest --cov=secondbrain --cov-report=html --cov-report=term-missing
```

### Coverage Thresholds
```python
# pyproject.toml
[tool.coverage.report]
fail_under = 80  # Minimum 80% coverage
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

## Best Practices

1. **Use appropriate markers** - Helps selective execution
2. **Prefer mocks for unit tests** - Faster and more reliable
3. **Use session-scoped fixtures** - For expensive setup
4. **Clean up test data** - Use fixtures with teardown
5. **Test behavior, not implementation** - Focus on outcomes
6. **Keep tests independent** - No test should depend on another
7. **Use parametrize for edge cases** - DRY test patterns
8. **Document slow tests** - Mark with `@pytest.mark.slow`

## Benchmarking

### Run Benchmarks
```bash
pytest --benchmark-only
```

### Benchmark Results
See `benchmarks/summary.md` for detailed performance analysis.

### Adding New Benchmarks
```python
def test_performance(benchmark):
    result = benchmark(expensive_function, arg1, arg2)
    assert result is not None
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-xdist (parallel execution)](https://pytest-xdist.readthedocs.io/)
- [pytest-cov (coverage)](https://pytest-cov.readthedocs.io/)
- [pytest-timeout](https://pytest-timeout.readthedocs.io/)
- [pytest-testmon (incremental testing)](https://pytest-testmon.readthedocs.io/)
