# Testing Guide

Comprehensive guide to testing SecondBrain.

## Test Environment Configuration

### Quick Setup

1. **Create test environment file** (optional, for custom settings):
   ```bash
   cp .env.test .env.test.local
   ```

2. **Start test services**:
   ```bash
   docker-compose -f docker-compose.test.yml up -d
   ```

3. **Run tests**:
   ```bash
   pytest                    # All tests
   pytest -m "not integration"  # Fast tests only
   pytest -m integration     # Integration tests only
   ```

### Environment Variables

Test configuration is automatically managed by the `Config` class. When running pytest:

- **Automatic detection**: Tests are detected via `PYTEST_CURRENT_TEST` environment variable
- **Automatic file loading**: `.env.test` is loaded if it exists
- **Platform-aware defaults**: LLM endpoint configuration via environment variables

#### Test-Specific Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECONDBRAIN_MONGO_URI` | `mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin` | Test MongoDB connection |
| `SECONDBRAIN_MONGO_DB` | `secondbrain_test` | Test database name |
| `SECONDBRAIN_MONGO_COLLECTION` | `test_embeddings` | Test collection name |
| `SECONDBRAIN_LOG_LEVEL` | `DEBUG` | Verbose logging for tests |
| `OTEL_TRACING_ENABLED` | `false` | Disable OpenTelemetry tracing |
| `OTEL_METRICS_ENABLED` | `false` | Disable OpenTelemetry metrics |
| `SECONDBRAIN_CIRCUIT_BREAKER_ENABLED` | `false` | Disable circuit breaker |
| `SECONDBRAIN_RATE_LIMIT_ENABLED` | `false` | Disable rate limiting |

See [`.env.test`](../../.env.test) for complete list with comments.

### Configuration Priority

1. Environment variables (highest priority)
2. `.env.test` file (when running tests)
3. `.env` file (production)
4. Default values in `Config` class (lowest priority)

### Custom Test Configuration

To override defaults for specific test scenarios:

```bash
# Option 1: Set environment variable
export SECONDBRAIN_MONGO_URI="mongodb://custom:27019"
pytest

# Option 2: Create .env.test.local
cp .env.test .env.test.local
# Edit .env.test.local with custom values
pytest
```

## Test Structure

### Test Organization

```
tests/
├── unit/           # Unit tests
│   ├── test_config.py
│   ├── test_utils.py
│   └── test_parser.py
├── integration/    # Integration tests
│   ├── test_storage.py
│   └── test_ingestion.py
├── conftest.py     # Fixtures
└── test_cli.py     # CLI tests
```

## Running Tests

### Fast Profile (Default)

```bash
pytest
```

- Unit tests only
- ~5 seconds
- No external services

### Integration Tests

```bash
pytest -m integration
```

- Requires MongoDB + sentence-transformers
- ~15 seconds

### Full Test Suite

```bash
pytest
```

- All tests
- ~25 seconds

### With Coverage

```bash
pytest --cov=secondbrain --cov-report=term-missing
```

## Test Fixtures

### Basic Fixture

```python
@pytest.fixture
def sample_document():
    return Document(
        id="test-1",
        content="Test content",
        metadata={"source": "test"}
    )
```

### Async Fixture

```python
@pytest.fixture
async def mongo_client():
    client = AsyncMongoClient("mongodb://localhost:27017")
    yield client
    await client.close()
```

### Temporary Directory

```python
@pytest.fixture
def temp_dir(tmp_path):
    dir = tmp_path / "test_docs"
    dir.mkdir()
    return dir
```

## Test Markers

```python
@pytest.mark.integration
def test_integration():
    """Integration test"""
    pass

@pytest.mark.slow
def test_slow_test():
    """Slow test"""
    pass

@pytest.mark.asyncio
async def test_async():
    """Async test"""
    pass
```

## Writing Tests

### Unit Test Example

```python
def test_chunking_creates_correct_chunks():
    """Test that chunking produces expected results."""
    text = "A" * 10000
    
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    
    assert len(chunks) == 10
    assert len(chunks[0]) == 1000
    assert chunks[0][-100:] == chunks[1][:100]  # Overlap
```

### Integration Test Example

```python
@pytest.mark.integration
async def test_document_ingestion(mongo_client):
    """Test full ingestion pipeline."""
    storage = DocumentStorage(client=mongo_client)
    await storage.initialize()
    
    await storage.ingest_document(
        doc_id="test-1",
        content="Test content",
        metadata={"source": "test"}
    )
    
    results = await storage.search(
        query_embedding=[0.1] * 384,
        top_k=1
    )
    
    assert len(results) == 1
    assert results[0].document_id == "test-1"
```

### CLI Test Example

```python
def test_cli_ingest_command(runner, tmp_path):
    """Test CLI ingest command."""
    doc_path = tmp_path / "test.txt"
    doc_path.write_text("Test content")
    
    result = runner.invoke(cli, ["ingest", str(doc_path)])
    
    assert result.exit_code == 0
    assert "Successfully ingested" in result.output
```

## Coverage Goals

| Module | Target |
|--------|--------|
| CLI | 90% |
| Document Ingestion | 85% |
| Embedding | 80% |
| Storage | 90% |
| Search | 85% |
| Utils | 95% |

## Test Performance

### Parallel Execution

```bash
# Use pytest-xdist
pytest -n auto
```

### Skip Slow Tests

```bash
# Exclude slow tests
pytest -m "not slow"
```

### Caching

```bash
# Use pytest-cach
pytest --cache-show
```

## Mocking

### Mock External Services

```python
from unittest.mock import AsyncMock, patch

async def test_ingestion_with_mocked_embedding():
    with patch("secondbrain.embedding.local.LocalEmbedder.generate") as mock_embed:
        mock_embed.return_value = [0.1] * 384
        
        # Test logic
```

### Mock MongoDB

```python
from unittest.mock import MagicMock

def test_storage_with_mock():
    mock_client = MagicMock()
    storage = DocumentStorage(client=mock_client)
    
    # Test with mock
```

## Continuous Integration

### GitHub Actions

```yaml
- name: Run tests
  run: pytest -m "not slow" --cov=secondbrain
```

---

## Troubleshooting

### Test Timeouts

```bash
# Increase timeout
pytest --timeout=120
```

### Debugging Tests

```bash
# Show output
pytest -s

# Stop on failure
pytest -x

# Verbose
pytest -v
```

## Next Steps

- [Code Standards](code-standards.md) - Writing testable code
- [Development Setup](development.md) - Setup testing environment
