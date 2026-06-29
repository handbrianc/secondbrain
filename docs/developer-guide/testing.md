# Testing Guide

Comprehensive guide to writing and running tests for SecondBrain.

## Framework

SecondBrain uses pytest with several plugins:

| Plugin | Purpose |
|--------|---------|
| pytest-asyncio | Async test support |
| pytest-xdist | Parallel execution |
| pytest-timeout | Prevent hanging tests |
| pytest-rerunfailures | Flaky test retry |
| pytest-cov | Coverage reporting |
| hypothesis | Property-based testing |

## Running Tests

### All Tests

```bash
pytest
```

### Verbose Output

```bash
pytest -v
```

### With Coverage

```bash
pytest --cov=secondbrain --cov-report=term-missing
```

HTML report:

```bash
pytest --cov=secondbrain --cov-report=html
open htmlcov/index.html
```

### Parallel Execution

```bash
# Use all CPUs
pytest -n auto

# Specify worker count
pytest -n 4
```

### Specific Paths

```bash
# Single file
pytest tests/unit/test_config.py

# Directory
pytest tests/integration/

# Pattern
pytest tests/**/test_*storage*
```

## Test Markers

Mark tests by category for selective execution:

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.unit` | Unit tests with mocks |
| `@pytest.mark.integration` | Require external services |
| `@pytest.mark.fast` | Under 50ms execution |
| `@pytest.mark.medium` | Under 500ms execution |
| `@pytest.mark.slow` | Over 1s execution |
| `@pytest.mark.concurrent` | Thread safety tests |
| `@pytest.mark.flaky` | Known intermittent failures |

### Running by Marker

```bash
# Fast tests only
pytest -m fast

# Exclude slow tests
pytest -m "not slow"

# Both conditions
pytest -m "not slow and integration"
```

## Fixture Scope

Fixtures can have different scopes:

```python
@pytest.fixture(scope="session")
def db_connection():
    """Session-scoped: created once per test session."""
    return connect_to_db()

@pytest.fixture(scope="function")
def temp_file(tmp_path):
    """Function-scoped: created per test."""
    return tmp_path / "test.txt"
```

## Mocking

Use `mongomock` for MongoDB simulation:

```python
from mongomock import MongoClient

@pytest.fixture
def mock_mongo():
    client = MongoClient()
    yield client
    client.close()
```

Example test with mocking:

```python
def test_delete_removes_document(mock_mongo, sample_chunk):
    """Test that delete removes the chunk from storage."""
    db = mock_mongo.secondbrain
    db.embeddings.insert_one(sample_chunk)
    
    deleter = Deleter(db)
    count = deleter.delete(chunk_id=sample_chunk["chunk_id"])
    
    assert count == 1
    assert db.embeddings.count_documents({}) == 0
```

## Async Testing

Mark async tests appropriately:

```python
@pytest.mark.asyncio
async def test_async_search_returns_results():
    """Test async search with mocked storage."""
    results = await async_storage.search("test query")
    assert len(results) > 0
```

## Hypothesis Property Testing

For generative testing of invariants:

```python
from hypothesis import given, strategies as st

@given(
    chunk_sizes=st.lists(st.integers(min_value=1, max_value=10000), min_size=1, max_size=100),
    overlap=st.integers(min_value=0, max_value=500)
)
def test_chunk_overlap_always_smaller_than_size(chunk_sizes, overlap):
    """Overlap must always be less than chunk size for valid configs."""
    # Filter to valid combinations
    assume(max(chunk_sizes) > overlap)
    
    # Test invariant holds
    for size in chunk_sizes:
        assert size > overlap
```

## Fixtures Location

Standard fixture locations:

- `tests/conftest.py` - Shared fixtures
- `tests/unit/conftest.py` - Unit-specific fixtures
- `tests/integration/conftest.py` - Integration fixtures

## Testing External Services

Integration tests requiring live services use markers:

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="External services required")
def test_real_mongo_connection():
    """Test against live MongoDB instance."""
    client = MongoClient(os.getenv("SECONDBRAIN_MONGO_URI"))
    ...
```

## Test Data

### Sample Fixtures

```python
@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a minimal PDF for testing."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 sample content")
    return pdf_path

@pytest.fixture
def sample_chunks():
    """Create sample chunks for testing."""
    return [
        Chunk(id="1", text="First chunk", source="./test.pdf", page=1),
        Chunk(id="2", text="Second chunk", source="./test.pdf", page=1),
    ]
```

## Coverage Requirements

Minimum coverage threshold: **75%**

Measured across all modules:

```
TOTAL                                    4500   1200    73%
```

Focus on covering:

- Core business logic
- Error handling branches
- Configuration parsing
- CLI argument handling

## Continuous Integration

GitHub Actions runs tests on:

- Multiple Python versions (3.11, 3.12)
- Operating systems (Ubuntu, macOS)
- With coverage reporting to Codecov

## Debugging Failed Tests

### PDB

Insert breakpoint:

```python
def test_failing():
    import pdb; pdb.set_trace()
    ...
```

### Detailed Tracebacks

```bash
pytest --tb=long --pdb src/tests/failing_test.py
```

### Reproduce Locally

Use exact same environment:

```bash
pytest tests/path/to/test.py -v -p no:warnings
```