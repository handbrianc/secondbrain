# Integration Test Evaluation

Integration testing strategy and evaluation for SecondBrain.

## Testing Philosophy

SecondBrain employs a comprehensive integration testing approach to ensure system reliability.

## Test Categories

### Unit Tests

**Purpose**: Test individual components in isolation

```python
def test_chunk_text():
    chunks = chunk_text("Long text...", chunk_size=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
```

**Coverage**: ~90% of codebase

### Integration Tests

**Purpose**: Test component interactions

```python
@pytest.mark.integration
async def test_ingest_and_search():
    # Setup
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    ingestor = DocumentIngestor(storage=storage)
    
    # Action
    doc_ids = await ingestor.ingest_file("test.pdf")
    
    # Verification
    results = await storage.search("test query", limit=5)
    assert len(results) > 0
```

**Requirements**:
- MongoDB instance running
- Test data available
- Isolated test database

### End-to-End Tests

**Purpose**: Test complete workflows

```python
@pytest.mark.integration
def test_cli_workflow():
    runner = CliRunner()
    
    # Ingest
    result = runner.invoke(cli, ["ingest", "test.pdf"])
    assert result.exit_code == 0
    
    # Search
    result = runner.invoke(cli, ["search", "query"])
    assert result.exit_code == 0
    assert "result" in result.output
```

## Test Infrastructure

### Test Database

```python
@pytest.fixture
async def test_db():
    client = AsyncMongoClient("mongodb://localhost:27017")
    db = client["secondbrain_test"]
    
    yield db
    
    # Cleanup
    await db.drop_collection("documents")
    await client.drop_database("secondbrain_test")
```

### Mock Services

```python
from mongomock import MongoClient

@pytest.fixture
def mock_mongo():
    client = MongoClient()
    return client["test_db"]
```

## Performance Testing

### Benchmark Tests

```python
@pytest.mark.benchmark
def test_search_latency(benchmark):
    def search():
        results = storage.search("query", limit=10)
        return results
    
    result = benchmark(search)
    assert len(result) <= 10
```

### Load Testing

```python
@pytest.mark.integration
async def test_concurrent_search():
    async def search_task(i):
        return await storage.search(f"query {i}", limit=5)
    
    tasks = [search_task(i) for i in range(100)]
    results = await asyncio.gather(*tasks)
    
    assert len(results) == 100
```

## Circuit Breaker Testing

### Failure Scenarios

```python
@pytest.mark.circuit_breaker
async def test_circuit_opens_on_failure():
    # Simulate service failure
    mock_storage = MockStorage(fail_after=5)
    
    # Make requests until circuit opens
    for i in range(10):
        try:
            await mock_storage.search("query")
        except CircuitOpenError:
            assert i >= 5
            break
```

### Recovery Testing

```python
@pytest.mark.circuit_breaker
async def test_circuit_closes_after_recovery():
    mock_storage = MockStorage(recover_after=10)
    
    # Wait for recovery
    await asyncio.sleep(10)
    
    # Should succeed
    result = await mock_storage.search("query")
    assert result is not None
```

## Property-Based Testing

### Hypothesis Integration

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=1000))
def test_chunking_preserves_content(text):
    chunks = chunk_text(text, chunk_size=100)
    reconstructed = " ".join(chunks)
    
    # Content should be preserved (with overlap)
    assert text.strip() in reconstructed or reconstructed in text.strip()
```

## Coverage Requirements

### Minimum Coverage

- **Lines**: 90%
- **Branches**: 85%
- **Functions**: 90%
- **Classes**: 85%

### Coverage Report

```bash
pytest --cov=secondbrain --cov-report=html

# Open coverage report
open htmlcov/index.html
```

## Continuous Integration

### GitHub Actions

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
      - name: Run tests
        run: pytest --cov=secondbrain
```

## Test Data Management

### Fixtures

```python
@pytest.fixture
def sample_document():
    return Document(
        id="test-123",
        title="Test Document",
        content="This is test content.",
        metadata={"source": "test.pdf"}
    )
```

### Test Data Files

```
tests/
├── data/
│   ├── sample.pdf
│   ├── sample.docx
│   └── sample.txt
```

## Troubleshooting

### Flaky Tests

**Issue**: Tests fail intermittently

**Solutions**:
- Increase timeouts
- Add proper async cleanup
- Use transaction isolation
- Mock external dependencies

### Slow Tests

**Issue**: Tests take too long

**Solutions**:
- Use smaller test datasets
- Mock expensive operations
- Run tests in parallel (`-n auto`)
- Mark slow tests with `@pytest.mark.slow`

## See Also

- [Testing Guide](../developer-guide/TESTING.md) - Detailed testing instructions
- [Async API](../developer-guide/async-api.md) - Async testing patterns
- [CI/CD](../developer-guide/development.md) - Continuous integration
