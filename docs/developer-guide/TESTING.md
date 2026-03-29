# Testing Guide

Comprehensive testing guide for SecondBrain.

## Testing Overview

SecondBrain uses pytest for testing with comprehensive coverage of unit, integration, and performance tests.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_document.py         # Document tests
├── test_storage.py          # Storage tests
├── test_ingestor.py         # Ingestion tests
├── test_search.py           # Search tests
├── test_cli.py              # CLI tests
└── integration/             # Integration tests
    ├── test_mongodb.py
    └── test_full_pipeline.py
```

## Running Tests

### Basic Test Run

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_document.py

# Run specific test
pytest tests/test_document.py::test_document_creation
```

### Test Options

```bash
# Run with coverage
pytest --cov=secondbrain --cov-report=html

# Run only failed tests
pytest --lf

# Run tests matching pattern
pytest -k "search"

# Parallel execution
pytest -n auto

# Set timeout
pytest --timeout=60
```

## Writing Tests

### Unit Tests

```python
import pytest
from secondbrain.document import Document

def test_document_creation():
    """Test document can be created."""
    doc = Document(
        id="test-123",
        title="Test Document",
        content="Test content"
    )
    
    assert doc.id == "test-123"
    assert doc.title == "Test Document"
    assert doc.content == "Test content"

def test_document_metadata():
    """Test document metadata handling."""
    doc = Document(
        id="test-123",
        title="Test",
        content="Content",
        metadata={"author": "John", "tags": ["test"]}
    )
    
    assert doc.metadata["author"] == "John"
    assert "test" in doc.metadata["tags"]
```

### Async Tests

```python
import pytest
import pytest_asyncio
from secondbrain.storage import MongoDBStorage

@pytest_asyncio.fixture
async def storage():
    """Create test storage."""
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    await storage.initialize()
    yield storage
    await storage.cleanup()

@pytest.mark.asyncio
async def test_store_document(storage):
    """Test storing a document."""
    doc = Document(id="1", title="Test", content="Content")
    doc_id = await storage.store_document(doc)
    
    assert doc_id is not None
    
    retrieved = await storage.get_document(doc_id)
    assert retrieved.title == "Test"
```

### Integration Tests

```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_ingestion_pipeline(storage, sample_pdf):
    """Test complete ingestion pipeline."""
    ingestor = DocumentIngestor(storage=storage)
    
    # Ingest document
    doc_ids = await ingestor.ingest_file(sample_pdf)
    assert len(doc_ids) > 0
    
    # Search for content
    results = await storage.search("test content", limit=5)
    assert len(results) > 0
```

## Fixtures

### Shared Fixtures

```python
# conftest.py

import pytest
import pytest_asyncio
from secondbrain.document import Document

@pytest.fixture
def sample_document():
    """Create a sample document."""
    return Document(
        id="test-123",
        title="Sample Document",
        content="This is sample content for testing.",
        metadata={"source": "test.pdf", "author": "Test Author"}
    )

@pytest.fixture
def sample_documents(sample_document):
    """Create multiple sample documents."""
    return [sample_document] + [
        Document(
            id=f"test-{i}",
            title=f"Document {i}",
            content=f"Content {i}"
        )
        for i in range(10)
    ]
```

## Mocking

### Mock External Services

```python
from unittest.mock import Mock, patch

def test_search_with_mocked_storage():
    """Test search with mocked storage."""
    mock_storage = Mock()
    mock_storage.search.return_value = [Document(id="1", title="Test", content="Content")]
    
    searcher = DocumentSearcher(storage=mock_storage)
    results = searcher.search("query")
    
    assert len(results) == 1
    mock_storage.search.assert_called_once_with("query", limit=10)
```

## Coverage

### Coverage Configuration

```ini
# .coveragerc
[run]
source = secondbrain
omit = 
    */tests/*
    */venv/*
    */__init__.py

[report]
precision = 2
fail_under = 90
```

### Coverage Reports

```bash
# Generate HTML report
pytest --cov=secondbrain --cov-report=html

# Generate XML report (for CI)
pytest --cov=secondbrain --cov-report=xml

# Show missing lines
pytest --cov=secondbrain --cov-report=term-missing
```

## Performance Testing

### Benchmark Tests

```python
import pytest

@pytest.mark.benchmark
def test_search_performance(benchmark):
    """Benchmark search performance."""
    
    def search():
        results = storage.search("test query", limit=10)
        return len(results)
    
    result = benchmark(search)
    assert result > 0
    
    # Check timing
    assert benchmark.stats.mean < 0.1  # < 100ms
```

## Hypothesis Testing

### Property-Based Testing

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=1000))
def test_chunking_preserves_text(text):
    """Test chunking preserves original text."""
    chunks = chunk_text(text, chunk_size=100)
    reconstructed = " ".join(chunks)
    
    # Content should be largely preserved
    assert len(reconstructed) >= len(text) * 0.9
```

## CI/CD Integration

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
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install -e ".[dev]"
      
      - name: Run tests
        run: pytest --cov=secondbrain --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Troubleshooting

### Flaky Tests

**Issue**: Tests fail intermittently

**Solutions**:
- Add proper async cleanup
- Use transaction isolation
- Mock time-dependent operations
- Increase timeouts

### Slow Tests

**Issue**: Tests take too long

**Solutions**:
- Mark slow tests: `@pytest.mark.slow`
- Use smaller datasets
- Mock expensive operations
- Run in parallel: `pytest -n auto`

## See Also

- [Code Standards](code-standards.md)
- [Development Setup](development.md)
- [Integration Test Evaluation](../architecture/INTEGRATION_TEST_EVALUATION.md)
