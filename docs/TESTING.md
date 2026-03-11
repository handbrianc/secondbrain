# Testing Guide

This document describes the test structure, profiles, and optimization strategies for the SecondBrain project.

## Performance Summary

| Profile | Test Count | Duration | Tests/Second |
|---------|-----------|----------|--------------|
| **Fast (default)** | ~480 | 5-10s | 48-96 |
| **Integration** | ~16 | 15-20s | 0.8-1.1 |
| **Slow (E2E)** | ~4 | 20-25s | 0.16-0.2 |
| **Full** | ~505 | 40-50s | 10-12 |

*Measured on macOS with parallel pytest-xdist execution*

## Recent Optimizations (v0.1.0)

### 1. Removed Autouse Fixture Overhead
**Problem**: `cleanup_resources` fixture was `autouse=True`, causing ~0.2s overhead per test.

**Solution**: Made cleanup opt-in. Tests only pay overhead when they actually need client cleanup.

**Impact**: Reduced per-test setup from 0.21s to 0.03s (85% improvement)

### 2. Fast CLI Test Fixture
Added `fast_cli_test` fixture for pure unit tests with minimal config and no cleanup overhead.

### 3. Slow Test Marking
E2E tests marked with `@pytest.mark.slow` and excluded from default profile.

### 4. Parallel Coverage Support
Added `--cov-context=test` for proper coverage reporting with parallel execution.

## Test Profiles

The test suite is organized into different profiles to support various testing needs:

### Fast Tests (Default)

Run unit tests that don't require external services:

```bash
# Run all fast tests (excludes slow E2E tests)
pytest -m "not slow"

# Run with parallel execution (recommended)
pytest -m "not slow" -n auto

# Run with coverage
pytest -m "not slow" --cov=secondbrain --cov-report=html
```

**Characteristics:**
- ✅ No external service dependencies (MongoDB, Ollama)
- ✅ Uses mocked components and mongomock
- ✅ Fast execution (5-10 seconds for 480+ tests)
- ✅ Run on every commit/PR
- ✅ Excludes slow E2E tests (>1s execution time)

### Integration Tests

Run tests that require external services:

```bash
# Run only integration tests
pytest -m integration

# Run with parallel execution
pytest -m integration -n auto

# Run specific integration test file
pytest tests/test_integration/ -v
```

**Characteristics:**
- ⚠️ Requires MongoDB and Ollama running
- ⚠️ Slower execution (15-20 seconds for 16 tests)
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

### 6. Fixtures for CLI Tests

When testing CLI commands that invoke heavy operations, mock at the CLI level:

```python
@patch("secondbrain.document.DocumentIngestor")
def test_ingest_command(mock_ingestor_class):
    """Test CLI command without running actual ingestion."""
    mock_ingestor = MagicMock()
    mock_ingestor.ingest.return_value = {"success": 5, "failed": 0}
    mock_ingestor_class.return_value = mock_ingestor
    
    result = runner.invoke(cli, ["ingest", "/tmp/test"])
    assert result.exit_code == 0
```

**Time saved:** 7+ seconds per CLI test

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

## Fixture Reference

### Core Fixtures

| Fixture | Scope | Description | When to Use |
|---------|-------|-------------|-------------|
| `cleanup_resources` | function | Auto-closes VectorStorage/EmbeddingGenerator | Tests using real clients |
| `fast_cli_test` | function | Minimal config, no cleanup | Pure CLI unit tests |
| `mock_embedding_generator` | function | Mocked embedding generation | Tests needing embeddings |
| `mock_vector_storage` | function | Mocked storage operations | Tests needing storage |
| `cached_embedding_generator` | function | Pre-computed embeddings | Fast embedding tests |
| `mocked_pdf_extraction` | function | Mocked PDF text extraction | PDF processing tests |
| `sample_pdf_path` | session | Pre-generated test PDF | Any PDF test |
| `fast_test_config` | function | Optimized config values | Performance-sensitive tests |

### Usage Examples

#### Fast CLI Test (No Cleanup Overhead)
```python
def test_chunk_size_validation(fast_cli_test):
    """Pure validation test - no client cleanup needed."""
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "/tmp/test", "--chunk-size", "100"])
    assert result.exit_code == 0
```

#### Test Requiring Cleanup
```python
def test_real_storage_operations(cleanup_resources):
    """Test using real VectorStorage - cleanup happens automatically."""
    storage = VectorStorage()
    storage.store(...)
    # Automatically closed after test
```

## Test Profiling and Timing

### Identifying Slow Tests

Run tests with timing information:

```bash
# Show slowest 10 tests
pytest --durations=10

# Show all tests with durations > 0.1s
pytest --durations=50 --durations-minimum=0.1

# Show detailed timing with setup/teardown
pytest --setup-show --durations=20
```

### Test Performance Targets

| Test Category | Target Time | Current Status |
|---------------|-------------|----------------|
| Fast unit tests | <0.01s | ✅ Achieved |
| CLI tests (mocked) | <0.1s | ✅ Achieved |
| Rate limiter tests | <0.1s | ✅ Achieved |
| Integration tests | <1s each | ⚠️ Requires services |
| Slow E2E tests | <5s each | 🔴 Expected (real operations) |

### Common Slow Test Patterns

1. **Unmocked external services** - Use mocks/fakes
2. **Real PDF processing** - Use `mocked_pdf_extraction` fixture
3. **Real embedding generation** - Use `cached_embedding_generator` fixture
4. **Large sleep() calls** - Reduce window sizes in tests
5. **Real database operations** - Use mongomock

### Coverage vs Speed Trade-off

```bash
# Fast tests without coverage (for quick iteration)
pytest -m "not integration" --no-cov

# Fast tests with coverage (for CI)
pytest -m "not integration" --cov=secondbrain

# Full suite with coverage (for releases)
pytest --cov=secondbrain --cov-fail-under=80
```

**Note:** Coverage reporting adds ~30-50% overhead to test execution time.

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
