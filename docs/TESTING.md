# Testing Guide

This document describes the test structure, profiles, and optimization strategies for the SecondBrain project.

## Test Profiles

The test suite is organized into different profiles to support various testing needs:

### Fast Tests (Default)

Run unit tests that don't require external services:

```bash
# Run all fast tests (excludes integration tests)
pytest -m "not integration"

# Run with parallel execution (recommended)
pytest -m "not integration" -n auto

# Run with coverage
pytest -m "not integration" --cov=secondbrain --cov-report=html
```

**Characteristics:**
- ✅ No external service dependencies (MongoDB, Ollama)
- ✅ Uses mocked components and mongomock
- ✅ Fast execution (<5 seconds for 400+ tests)
- ✅ Run on every commit/PR

### Integration Tests

Run tests that require external services:

```bash
# Run only integration tests
pytest -m integration

# Run with parallel execution
pytest -m integration -n auto

# Run specific integration test file
pytest tests/test_document/test_e2e_pdf_ingestion.py -v
```

**Characteristics:**
- ⚠️ Requires MongoDB and Ollama running
- ⚠️ Slower execution (30-45 seconds for all integration tests)
- ⚠️ Run nightly or on-demand
- ⚠️ Tests real service interactions

### Slow Tests

Run the slowest tests (PDF processing, full E2E workflows):

```bash
# Run only slow tests
pytest -m slow

# Run with detailed timing
pytest -m slow --durations=20
```

**Characteristics:**
- 🔴 PDF parsing with docling (~5s per test)
- 🔴 Full E2E pipelines with real embeddings
- 🔴 Run weekly or before releases

## Test Markers

Tests are marked with pytest markers for selective execution:

| Marker | Description | Example |
|--------|-------------|---------|
| `@pytest.mark.integration` | Requires external services | `tests/test_document/test_e2e_pdf_ingestion.py` |
| `@pytest.mark.slow` | Takes >1 second to execute | PDF processing tests |
| `@pytest.mark.unit` | Fast unit tests with mocks | Most tests in `tests/test_cli/` |

### Adding Markers to New Tests

```python
import pytest

@pytest.mark.integration
class TestMyFeature:
    """Integration test requiring MongoDB/Ollama."""
    
    def test_with_real_services(self):
        # Uses real MongoDB and Ollama
        pass

@pytest.mark.slow
def test_pdf_processing():
    """Slow test with PDF parsing."""
    pass

def test_unit_function():
    """Fast unit test (no marker needed)."""
    pass
```

## Test Fixtures

### Available Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `sample_pdf_path` | session | Creates a sample PDF for testing |
| `sample_pdf_with_multiple_pages` | session | Creates a 3-page PDF |
| `mock_embedding_generator` | function | Mocks EmbeddingGenerator |
| `mock_vector_storage` | function | Mocks VectorStorage |
| `cached_embedding_generator` | function | Fast embedding mock with deterministic output |
| `mocked_pdf_extraction` | function | Mocks PDF text extraction |
| `fast_test_config` | function | Optimized config for fast tests |
| `sample_embedding` | function | Pre-computed 768-dim embedding |
| `mongomock_client` | function | In-memory MongoDB mock |

### Using Fixtures

```python
def test_with_mocked_pdf(mocked_pdf_extraction, sample_pdf_path):
    """Test using mocked PDF extraction."""
    ingestor = DocumentIngestor()
    segments = ingestor._extract_text(sample_pdf_path)
    assert len(segments) == 3  # From mock
    
def test_with_cached_embeddings(cached_embedding_generator):
    """Test with fast, deterministic embeddings."""
    generator = EmbeddingGenerator()
    embedding = generator.generate("test text")
    assert len(embedding) == 768
```

## Test Optimization Strategies

### 1. Mock Heavy Operations

**Before (slow):**
```python
def test_pdf_ingestion(sample_pdf_path):
    ingestor = DocumentIngestor()
    segments = ingestor._extract_text(sample_pdf_path)  # ~5s
```

**After (fast):**
```python
def test_pdf_ingestion(mocked_pdf_extraction, sample_pdf_path):
    ingestor = DocumentIngestor()
    segments = ingestor._extract_text(sample_pdf_path)  # ~0.01s
```

**Time saved:** ~5 seconds per test

### 2. Use Cached Embeddings

**Before (slow):**
```python
def test_search():
    generator = EmbeddingGenerator()
    embedding = generator.generate("query")  # ~2s (Ollama call)
```

**After (fast):**
```python
def test_search(cached_embedding_generator):
    generator = EmbeddingGenerator()
    embedding = generator.generate("query")  # ~0.01s (mocked)
```

**Time saved:** ~2 seconds per test

### 3. Use mongomock Instead of Real MongoDB

**Before (slow):**
```python
def test_storage():
    storage = VectorStorage()  # Real MongoDB connection
    storage.store(doc)  # Network latency
```

**After (fast):**
```python
def test_storage(mongomock_client):
    storage = VectorStorage(client=mongomock_client)  # In-memory
    storage.store(doc)  # Instant
```

**Time saved:** ~1 second per test

### 4. Parallel Test Execution

Enable parallel execution with pytest-xdist:

```bash
# Auto-detect CPU cores
pytest -n auto

# Specify number of workers
pytest -n 4

# With coverage
pytest -n auto --cov=secondbrain
```

**Time saved:** 60-70% on multi-core machines

### 5. Reduce Rate Limiter Windows

Use `fast_test_config` fixture for rate-limited tests:

```python
def test_rate_limiting(fast_test_config):
    # Rate limiter window: 0.1s instead of 1.0s
    limiter = RateLimiter(max_requests=10, window_seconds=0.1)
```

**Time saved:** 90% on rate limiter tests

## Running Tests in CI/CD

### GitHub Actions (Local Development)

Since this project uses local development workflow, run tests locally:

```bash
# Pre-commit hook validation
pre-commit run --all-files

# Full test suite
pytest

# Fast tests only (for quick feedback)
pytest -m "not integration" -n auto

# Integration tests (requires services)
docker-compose up -d  # Start MongoDB
ollama serve &        # Start Ollama
pytest -m integration
```

### Test Coverage

```bash
# Run with coverage report
pytest --cov=secondbrain --cov-report=html --cov-report=term-missing

# Open coverage report
open htmlcov/index.html

# Enforce 80% coverage
pytest --cov=secondbrain --cov-fail-under=80
```

## Troubleshooting

### Tests Taking Too Long

1. **Check if integration tests are running accidentally:**
   ```bash
   pytest -m "not integration"  # Exclude integration tests
   ```

2. **Enable parallel execution:**
   ```bash
   pytest -n auto
   ```

3. **Use mocked fixtures:**
   ```python
   @pytest.fixture
   def my_test(mocked_pdf_extraction, cached_embedding_generator):
       pass
   ```

### MongoDB Connection Errors

1. **Ensure MongoDB is running:**
   ```bash
   docker-compose up -d
   ```

2. **Use mongomock for unit tests:**
   ```python
   def test_with_mock(mongomock_client):
       pass
   ```

3. **Clear test database:**
   ```bash
   mongosh secondbrain --eval "db.dropDatabase()"
   ```

### Ollama Connection Errors

1. **Ensure Ollama is running:**
   ```bash
   ollama serve
   ```

2. **Pull required model:**
   ```bash
   ollama pull embeddinggemma:latest
   ```

3. **Use mocked embeddings:**
   ```python
   def test_with_mock(cached_embedding_generator):
       pass
   ```

## Performance Benchmarks

### Current Performance

| Test Category | Count | Total Time | Avg per Test |
|---------------|-------|------------|--------------|
| Fast Tests | 400+ | <5s | <0.01s |
| Integration Tests | 50+ | ~15s | ~0.3s |
| Slow Tests (E2E) | 11 | ~16s | ~1.5s |
| **Total** | **513** | **~42s** | **~0.08s** |

### Target Performance (After Optimizations)

| Test Category | Count | Total Time | Avg per Test |
|---------------|-------|------------|--------------|
| Fast Tests | 400+ | <3s | <0.01s |
| Integration Tests | 50+ | ~8s | ~0.16s |
| Slow Tests (E2E) | 11 | ~8s | ~0.7s |
| **Total** | **513** | **~19s** | **~0.04s** |

**Expected Improvement:** 50-60% faster overall

## Contributing Test Improvements

When adding new tests:

1. **Prefer fast tests** with mocks unless testing service integration
2. **Add appropriate markers** (`@pytest.mark.integration`, `@pytest.mark.slow`)
3. **Use existing fixtures** instead of creating new ones
4. **Keep tests isolated** - each test should be independent
5. **Document slow operations** with comments explaining why they can't be mocked

Example:
```python
import pytest

@pytest.mark.integration  # Requires MongoDB
def test_real_storage_behavior():
    """Test actual MongoDB vector storage behavior."""
    storage = VectorStorage()
    # ... test code ...

@pytest.mark.slow  # PDF parsing is inherently slow
def test_pdf_chunking_behavior():
    """Test PDF chunking with real docling parser."""
    # This test can't be mocked because we're testing docling itself
    ingestor = DocumentIngestor()
    # ... test code ...

def test_chunking_logic():
    """Fast unit test for chunking algorithm."""
    # Mock the PDF extraction, test the chunking logic
    with patch.object(DocumentIngestor, '_extract_text', return_value=mock_segments):
        ingestor = DocumentIngestor()
        # ... test code ...
```

## Related Documentation

- [README.md](../README.md) - Project overview
- [Developer Guide](developer-guide.md) - Development setup
- [Configuration Guide](../docs/getting-started/configuration.md) - Environment variables
- [AGENTS.md](../AGENTS.md) - Agent coding guidelines
