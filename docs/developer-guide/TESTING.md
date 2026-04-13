# Testing Guide

Comprehensive guide to testing SecondBrain.

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

## Quantitative Testing

The quantitative testing framework provides automated, metrics-driven evaluation of the RAG pipeline across five key dimensions: performance, consistency, semantic similarity, precision/recall, and ROUGE scores.

### Test Organization

```
tests/test_quantitative/
├── README.md                    # Comprehensive framework documentation
├── conftest.py                  # Shared fixtures and utilities
├── test_performance.py          # Performance/benchmark tests
├── test_consistency.py          # Answer consistency tests
├── test_semantic_similarity.py  # Semantic relevance tests
├── test_precision_recall.py     # Information retrieval metrics
├── test_rouge_scores.py         # Text generation quality
└── test_golden_dataset.py       # Golden dataset validation
```

### Running Quantitative Tests

```bash
# Run all quantitative tests (requires MongoDB + Ollama)
pytest tests/test_quantitative/ -v

# Run specific test category
pytest tests/test_quantitative/test_performance.py -v
pytest tests/test_quantitative/test_consistency.py -v
pytest tests/test_quantitative/test_semantic_similarity.py -v
pytest tests/test_quantitative/test_precision_recall.py -v
pytest tests/test_quantitative/test_rouge_scores.py -v
pytest tests/test_quantitative/test_golden_dataset.py -v

# Run by marker
pytest tests/test_quantitative/ -m performance -v
pytest tests/test_quantitative/ -m consistency -v
pytest tests/test_quantitative/ -m semantic_similarity -v
pytest tests/test_quantitative/ -m precision_recall -v
pytest tests/test_quantitative/ -m rouge -v
pytest tests/test_quantitative/ -m golden_dataset -v
```

### Test Categories Overview

| Category | Marker | Services Required | Description |
|----------|--------|-------------------|-------------|
| Performance | `@pytest.mark.performance` | MongoDB, Ollama | Response times, throughput, latency |
| Consistency | `@pytest.mark.consistency` | MongoDB, Ollama | Answer stability across runs |
| Semantic Similarity | `@pytest.mark.semantic_similarity` | MongoDB, Ollama | Query-answer relevance |
| Precision & Recall | `@pytest.mark.precision_recall` | MongoDB | Search result quality |
| ROUGE Scores | `@pytest.mark.rouge` | MongoDB, Ollama | Text generation quality |
| Golden Dataset | `@pytest.mark.golden_dataset` | MongoDB, Ollama | End-to-end validation |

### Metrics and Thresholds

#### Performance Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Mean Response Time | < 5.0s | Average RAG query time |
| P95 Response Time | < 8.0s | 95th percentile latency |
| Mean Embedding Time | < 1.0s | Embedding generation |
| Mean Search Time | < 0.5s | Vector search latency |
| Min Throughput | >= 2.0 q/s | Concurrent query handling |

#### Consistency Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Mean Consistency | >= 0.80 | Answer stability across runs |
| Variance | < 0.05 | Low variance = reliable |
| Embedding Stability | >= 0.95 | Semantic representation stability |

#### Semantic Similarity Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Query-Answer Similarity | >= 0.60 | Answer relevance |
| Query-Context Similarity | >= 0.50 | Retrieved chunk relevance |

#### Precision & Recall Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Precision@5 | >= 0.40 | 40% of top 5 relevant |
| Recall@10 | >= 0.40 | Find 40% of relevant |
| Mean Average Precision | >= 0.50 | Overall ranking quality |
| nDCG@10 | >= 0.60 | Ranking quality |

#### ROUGE Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| ROUGE-1 F1 | >= 0.50 | Unigram overlap |
| ROUGE-2 F1 | >= 0.40 | Bigram overlap |
| ROUGE-L F1 | >= 0.40 | Sentence structure |

#### Golden Dataset Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Overall Pass Rate | >= 80% | Most queries pass |
| Category Pass Rate | >= 80% | Per-category threshold |

### Golden Datasets

Golden datasets are curated JSON files with query/answer pairs for validation:

```bash
# Location
tests/data/golden_datasets/
├── tech_docs_golden.json
├── precision_recall_golden.json
└── rouge_reference_answers.json
```

#### Dataset Format

```json
{
  "metadata": {
    "name": "dataset_name",
    "version": "1.0.0",
    "total_queries": 20
  },
  "queries": [
    {
      "id": "test-001",
      "query": "What is the default chunk size?",
      "expected_concepts": ["chunk", "size", "4096"],
      "forbidden_concepts": ["memory", "buffer"],
      "category": "configuration",
      "expected_answer": "The default chunk size is 4096 tokens."
    }
  ]
}
```

#### Creating New Golden Datasets

1. Create JSON file in `tests/data/golden_datasets/`
2. Define metadata with name, version, description
3. Add queries with required fields:
   - `id`: Unique identifier
   - `query`: Test query text
   - `expected_concepts`: Concepts must appear in answers
   - `forbidden_concepts`: Concepts must NOT appear
   - `category`: Test category
4. Optionally add `expected_answer` for semantic comparison
5. Validate with: `pytest tests/test_quantitative/test_golden_dataset.py::TestGoldenDataset::test_load_valid_dataset -v`

### Interpreting Results

#### Passing Test
```
tests/test_quantitative/test_performance.py::TestPerformance::test_query_response_time PASSED
```

#### Failing Test
```
AssertionError: Performance thresholds exceeded:
  Mean response time: 6.234s (threshold: 5.0s)
  P95 latency: 9.123s (threshold: 8.0s)
```

#### Common Failure Patterns

| Pattern | Likely Cause | Solution |
|---------|--------------|----------|
| Low consistency | LLM non-determinism | Increase temperature stability |
| Low semantic similarity | Poor retrieval | Check embedding model |
| Low precision@K | Irrelevant results | Tune similarity threshold |
| High response time | Resource constraints | Scale resources |

### Troubleshooting

#### MongoDB Connection Errors
```bash
# Start MongoDB
docker-compose up -d

# Verify connection
secondbrain health
```

#### LLM Unavailable
```bash
# Start Ollama
ollama serve

# Pull model
ollama pull llama2
```

#### Missing Dependencies
```bash
# Install test dependencies
pip install -e ".[dev]"

# Install quantitative testing deps
pip install sentence-transformers scikit-learn rouge-score
```

#### Test Timeouts
```bash
# Increase timeout
pytest tests/test_quantitative/ --timeout=300 -v
```

### Quick Start for New Developers

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Start services
docker-compose up -d
ollama serve

# 3. Run fast validation (no services)
pytest tests/test_quantitative/test_golden_dataset.py -v -k "load"

# 4. Run full quantitative suite
pytest tests/test_quantitative/ -v

# 5. Run specific category
pytest tests/test_quantitative/test_performance.py -v
```

### Configuration

#### Custom Thresholds

Create `tests/test_quantitative/conftest_local.py`:
```python
THRESHOLD_MEAN_RESPONSE_TIME = 10.0  # More lenient for slower hardware
```

#### Pytest Configuration

Update `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    "performance: Performance/benchmark tests",
    "consistency: Consistency validation tests",
    "semantic_similarity: Semantic similarity tests",
    "precision_recall: Information retrieval metrics",
    "rouge: ROUGE score evaluation",
    "golden_dataset: Golden dataset validation",
    "integration: Requires external services",
    "optional: May be skipped in CI"
]
```

### Parallel Execution

```bash
# Run tests in parallel
pytest tests/test_quantitative/ -n auto

# Only run failed tests
pytest tests/test_quantitative/ --ff

# Generate HTML report
pytest tests/test_quantitative/ --html=report.html --self-contained-html
```

### See Also

- [Detailed Framework Documentation](../../tests/test_quantitative/README.md)
- [Golden Dataset Format](../../tests/data/golden_datasets/README.md)
- [Architecture Overview](../architecture/index.md)

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
