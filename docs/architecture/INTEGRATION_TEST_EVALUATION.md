# Integration Test Evaluation

Evaluation framework for SecondBrain integration tests.

## Test Categories

### Unit Tests
- Test individual components in isolation
- Fast execution (< 1 second per test)
- No external dependencies

### Integration Tests
- Test component interactions
- Require MongoDB and sentence-transformers
- Medium execution time (1-5 seconds per test)

### End-to-End Tests
- Test complete workflows
- Full system validation
- Slower execution (5-30 seconds per test)

## Test Infrastructure

### Required Services

```yaml
# docker-compose.yml
version: '3.8'
services:
  mongo:
    image: mongo:8.0
    ports:
      - "27017:27017"
  
  sentence-transformers:
    image: sentence-transformers:latest
    ports:
      - "11434:11434"
```

### Test Fixtures

```python
@pytest.fixture
async def mongo_client():
    client = AsyncMongoClient("mongodb://localhost:27017")
    yield client
    await client.close()

@pytest.fixture
async def document_storage(mongo_client):
    storage = DocumentStorage(client=mongo_client)
    await storage.initialize()
    yield storage
    await storage.cleanup()
```

## Test Profiles

### Fast Profile (Default)

```bash
pytest -m "not integration"
```

- Unit tests only
- ~5 seconds total
- No external services required

### Integration Profile

```bash
pytest -m integration
```

- Integration tests
- ~15 seconds total
- Requires MongoDB + sentence-transformers

### Slow Profile (E2E)

```bash
pytest -m slow
```

- Full end-to-end tests
- ~16 seconds total
- Complete workflow validation

### Full Profile

```bash
pytest
```

- All tests
- ~25 seconds total
- Complete test coverage

## Test Markers

```python
@pytest.mark.integration
def test_ingestion_flow():
    """Integration test requiring services"""
    pass

@pytest.mark.slow
def test_full_workflow():
    """Slow end-to-end test"""
    pass

@pytest.mark.asyncio
async def test_async_operations():
    """Async test"""
    pass
```

## Coverage Goals

| Module | Target | Current |
|--------|--------|---------|
| CLI | 90% | 92% |
| Document Ingestion | 85% | 88% |
| Embedding | 80% | 82% |
| Storage | 90% | 91% |
| Search | 85% | 87% |
| Utils | 95% | 94% |

**Overall Target**: 85% coverage

## Running Tests

### Local Development

```bash
# Fast profile (default)
pytest

# With coverage
pytest --cov=secondbrain --cov-report=term-missing

# Integration tests only
pytest -m integration

# Specific test file
pytest tests/test_storage.py
```

### CI/CD

```bash
# Full test suite with coverage
pytest -m "not slow" --cov=secondbrain --cov-report=xml

# Generate coverage report
coverage html
```

## Test Data

### Fixtures

```python
@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(sample_pdf_content)
    return pdf_path

@pytest.fixture
def sample_documents():
    return [
        {"id": "1", "content": "Test document 1"},
        {"id": "2", "content": "Test document 2"},
    ]
```

### Test Databases

- Use separate test database
- Clean before/after each test
- Isolated from production data

## Performance Testing

### Benchmarks

```bash
# Run benchmarks
pytest --benchmark-only

# Compare with baseline
pytest --benchmark-compare
```

### Load Testing

```python
def test_concurrent_ingestion():
    """Test parallel document ingestion"""
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(ingest_document, doc)
            for doc in large_document_set
        ]
        results = [f.result() for f in futures]
    assert all(results)
```

## Quality Gates

### Pre-Commit

```bash
# Must pass before commit
ruff check .
ruff format --check .
mypy .
pytest -m "not integration"
```

### Pre-Release

```bash
# Full validation
pytest
mypy .
bandit -r src/
pip-audit
```

## Troubleshooting

### Test Failures

```bash
# Verbose output
pytest -v

# Show captured output
pytest -s

# Stop on first failure
pytest -x

# Detailed failure info
pytest -vv
```

### Service Issues

```bash
# Check MongoDB
docker-compose logs mongo

# Check sentence-transformers
docker-compose logs sentence-transformers

# Restart services
docker-compose restart
```
