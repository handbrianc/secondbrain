# Quantitative Testing Framework

Comprehensive quantitative testing framework for evaluating the SecondBrain RAG (Retrieval-Augmented Generation) pipeline. This framework provides automated, metrics-driven tests to validate the quality, performance, and consistency of your document intelligence system.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Test Categories](#test-categories)
- [Running Tests](#running-tests)
- [Understanding Metrics and Thresholds](#understanding-metrics-and-thresholds)
- [Golden Datasets](#golden-datasets)
- [Creating New Golden Datasets](#creating-new-golden-datasets)
- [Interpreting Test Results](#interpreting-test-results)
- [Troubleshooting](#troubleshooting)
- [Configuration](#configuration)

---

## Overview

The quantitative testing framework evaluates SecondBrain across five key dimensions:

1. **Performance** - Response times, throughput, and latency percentiles
2. **Consistency** - Answer stability across multiple runs
3. **Semantic Similarity** - Query-answer relevance and context alignment
4. **Precision & Recall** - Search result quality and ranking metrics
5. **Golden Dataset** - End-to-end validation with curated test cases

All tests use real pipeline execution (not mocks) with configurable thresholds for flexibility across different deployment scenarios.

---

## Quick Start

For new developers, here's how to get started with quantitative testing:

### Prerequisites

```bash
# Ensure MongoDB is running
docker-compose up -d

# Ensure sentence-transformers service is running
sentence-transformers serve

# Install test dependencies
pip install -e ".[dev]"
```

### Run All Quantitative Tests

```bash
# Run all quantitative tests (requires services)
# IMPORTANT: Do NOT use -n flag (pytest-xdist) - will cause PyTorch meta tensor errors
pytest tests/test_quantitative/ -v

# Run specific test category
pytest tests/test_quantitative/ -m performance -v
pytest tests/test_quantitative/ -m consistency -v
pytest tests/test_quantitative/ -m semantic_similarity -v
pytest tests/test_quantitative/ -m precision_recall -v
pytest tests/test_quantitative/ -m golden_dataset -v
```

### ⚠️ Important: No Parallel Execution

**DO NOT use pytest-xdist (`-n` flag) with quantitative tests!**

```bash
# WRONG - Will cause meta tensor errors
pytest tests/test_quantitative/ -v -n 4
pytest tests/test_quantitative/ -v --numprocesses=4

# CORRECT - Sequential execution only
pytest tests/test_quantitative/ -v
```

**Why?** These tests use PyTorch SentenceTransformer models that cannot be safely shared across pytest-xdist worker processes. Parallel execution causes `NotImplementedError: Cannot copy out of meta tensor` errors.

**Exception**: You can use `-n` flag for other test directories (e.g., `pytest tests/test_storage/ -v -n 4`), but NOT for `tests/test_quantitative/`.

### Fast Validation (No Services Required)

```bash
# Run tests that don't require MongoDB
pytest tests/test_quantitative/test_golden_dataset.py -v -k "load"
```

### Test Runtime Profiles

Quantitative tests support environment variable overrides for faster local testing:

```bash
# Smoke tests (fast, ~1-2 hours) - for local development
N_RUNS_STATISTICAL=5 MIN_RUNS_CONSISTENCY=5 N_RUNS_SEMANTIC_SIMILARITY=5 N_RUNS_SEMANTIC_EVALUATION=5 pytest tests/test_quantitative/ -v

# Statistical tests (full, ~3-4 hours) - for production/CI
pytest tests/test_quantitative/ -v

# Available overrides:
# - N_RUNS_STATISTICAL: Golden dataset tests (default: 30)
# - MIN_RUNS_CONSISTENCY: Consistency tests (default: 30)
# - N_RUNS_SEMANTIC_SIMILARITY: Semantic similarity tests (default: 30)
# - N_RUNS_SEMANTIC_EVALUATION: Semantic evaluation tests (default: 30)
```

**Note**: All quantitative tests run **sequentially** (no parallel execution) due to PyTorch model constraints.

---

## Installation

### Dependencies

The quantitative testing framework requires the following dependencies:

```bash
# Core testing dependencies (from pyproject.toml [dev] extras)
pip install -e ".[dev]"

# Specific quantitative testing dependencies
pip install sentence-transformers scikit-learn
```

### Verifying Installation

```bash
# Check that all test files are discoverable
pytest tests/test_quantitative/ --collect-only

# Verify fixtures are loaded
pytest tests/test_quantitative/conftest.py -v
```

---

## Test Categories

### 1. Performance Tests (`test_performance.py`)

**Marker**: `@pytest.mark.performance` or `@pytest.mark.benchmark`

Validates system latency, throughput, and response times.

**Test Commands**:
```bash
# Run all performance tests
pytest tests/test_quantitative/test_performance.py -v

# Run specific performance test
pytest tests/test_quantitative/test_performance.py::TestPerformance::test_query_response_time -v

# Run with benchmark reporting
pytest tests/test_quantitative/test_performance.py -v --benchmark-report
```

**Key Tests**:
- `test_query_response_time` - Mean and P95 latency for RAG queries
- `test_embedding_generation_time` - Embedding generation performance
- `test_search_latency` - Search operation latency
- `test_llm_generation_time` - LLM response generation time
- `test_throughput_queries_per_second` - Concurrent query throughput
- `test_p95_p99_latency` - Latency percentile analysis

### 2. Consistency Tests (`test_consistency.py`)

**Marker**: `@pytest.mark.consistency`

Validates answer stability across multiple runs and similar queries.

**Test Commands**:
```bash
# Run all consistency tests
pytest tests/test_quantitative/test_consistency.py -v

# Run specific consistency test
pytest tests/test_quantitative/test_consistency.py::TestConsistency::test_answer_consistency_across_runs -v
```

**Key Tests**:
- `test_answer_consistency_across_runs` - Same query, multiple runs (5 runs)
- `test_similar_queries_similar_answers` - Similar queries produce similar answers
- `test_query_rewriting_consistency` - Query rewriting maintains semantics
- `test_answer_embedding_stability` - Answer embeddings remain stable
- `test_temporal_consistency` - Consistency across sequential runs

### 3. Semantic Similarity Tests (`test_semantic_similarity.py`)

**Marker**: `@pytest.mark.semantic_similarity` or `@pytest.mark.threshold`

Validates semantic relevance between queries, answers, and retrieved context.

**Test Commands**:
```bash
# Run all semantic similarity tests
pytest tests/test_quantitative/test_semantic_similarity.py -v

# Run threshold validation tests
pytest tests/test_quantitative/test_semantic_similarity.py -m threshold -v
```

**Key Tests**:
- `test_query_answer_relevance` - Query-answer cosine similarity >= 0.6
- `test_query_context_alignment` - Retrieved chunks semantically related to query
- `test_cross_query_similarity` - Similar queries produce similar answers
- `test_golden_dataset_query_answer_similarity` - Golden dataset integration

### 4. Precision & Recall Tests (`test_precision_recall.py`)

**Marker**: `@pytest.mark.precision_recall` and `@pytest.mark.integration`

Validates search result quality using information retrieval metrics.

**Test Commands**:
```bash
# Run all precision/recall tests (requires MongoDB)
pytest tests/test_quantitative/test_precision_recall.py -v -m integration

# Run specific metric test
pytest tests/test_quantitative/test_precision_recall.py::TestPrecisionRecall::test_precision_at_k -v
```

**Key Tests**:
- `test_precision_at_k` - Precision@5, @10, @20
- `test_recall_at_k` - Recall@5, @10, @20
- `test_mean_average_precision` - mAP score across all queries
- `test_ndcg_at_k` - Normalized Discounted Cumulative Gain
- `test_precision_recall_tradeoff` - Verify expected P/R behavior

### 5. Golden Dataset Tests (`test_golden_dataset.py`)

**Marker**: `@pytest.mark.golden_dataset`

End-to-end validation against curated golden datasets.

**Test Commands**:
```bash
# Run all golden dataset tests
pytest tests/test_quantitative/test_golden_dataset.py -v

# Run by category
pytest tests/test_quantitative/test_golden_dataset.py::TestGoldenDataset::test_golden_query_by_category -v -k "configuration"
```

**Key Tests**:
- `test_load_valid_dataset` - Dataset schema validation
- `test_golden_query_coverage` - Query coverage validation
- `test_golden_query_by_category` - Category-based pass rates
- `test_answer_semantic_alignment` - Semantic similarity to expected answers
- `test_golden_dataset_pass_rate` - Overall pass rate >= 80%

---

## Understanding Metrics and Thresholds

### Performance Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Mean Response Time | < 5.0s | Acceptable for interactive CLI usage |
| P95 Response Time | < 8.0s | 95th percentile for production SLA |
| Mean Embedding Time | < 1.0s | Local model should be fast |
| P95 Embedding Time | < 2.0s | Tail latency bound |
| Mean Search Time | < 0.5s | Vector search should be instant |
| P95 Search Time | < 1.0s | Search tail latency |
| Mean LLM Time | < 3.0s | Local LLM generation bound |
| P95 LLM Time | < 5.0s | LLM tail latency |
| Min Throughput | >= 2.0 q/s | Concurrent query handling |

### Consistency Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Mean Consistency | >= 0.80 | Answers should be mostly stable |
| Variance | < 0.05 | Low variance indicates reliability |
| Embedding Stability | >= 0.95 | Embeddings should be highly stable |
| Query Rewriting Similarity | >= 0.70 | Rewritten queries maintain semantics |

### Semantic Similarity Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Query-Answer Similarity | >= 0.60 | Answers must be semantically relevant |
| Query-Context Similarity | >= 0.50 | Retrieved chunks must relate to query |
| Cross-Query Tolerance | < 0.15 | Similar queries → similar answers |

### Precision & Recall Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Precision@5 | >= 0.40 | 40% of top 5 should be relevant |
| Precision@10 | >= 0.50 | 50% of top 10 should be relevant |
| Precision@20 | >= 0.40 | Maintain relevance at scale |
| Recall@5 | >= 0.30 | Find 30% of relevant in top 5 |
| Recall@10 | >= 0.40 | Find 40% of relevant in top 10 |
| Recall@20 | >= 0.50 | Find 50% of relevant in top 20 |
| Mean Average Precision | >= 0.50 | Overall ranking quality |
| nDCG@10 | >= 0.60 | Ranking quality with position bias |

### Golden Dataset Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Overall Pass Rate | >= 80% | Most queries should pass |
| Category Pass Rate | >= 80% | Each category must meet threshold |
| Concept Presence | 100% | All expected concepts must appear |
| Forbidden Concept Absence | 100% | No forbidden concepts allowed |
| Semantic Alignment | >= 0.65 | Answers align with expected |

---

## Golden Datasets

### Location

Golden datasets are stored in `tests/data/golden_datasets/`:

- `tech_docs_golden.json` - Technical documentation queries
- `precision_recall_golden.json` - Precision/recall evaluation

### Dataset Format

Each golden dataset follows this JSON structure:

```json
{
  "metadata": {
    "name": "dataset_name",
    "description": "Purpose of this dataset",
    "version": "1.0.0",
    "created": "2026-04-12",
    "total_queries": 20
  },
  "queries": [
    {
      "id": "config-001",
      "query": "What is the default chunk size?",
      "expected_concepts": ["chunk", "size", "4096", "default"],
      "forbidden_concepts": ["memory", "buffer"],
      "category": "configuration",
      "expected_answer": "The default chunk size is 4096 tokens.",
      "relevant_chunk_ids": ["chunk-001", "chunk-002"]
    }
  ]
}
```

### Required Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier for the test case |
| `query` | string | Yes | The test query text |
| `expected_concepts` | array | Yes | Concepts that must appear in answers |
| `forbidden_concepts` | array | Yes | Concepts that must NOT appear |
| `category` | string | Yes | Test category (configuration, features, etc.) |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `expected_answer` | string | Reference answer for semantic comparison |
| `relevant_chunk_ids` | array | Expected relevant document/chunk IDs |
| `min_threshold` | float | Custom threshold for this query |

---

## Creating New Golden Datasets

### Step-by-Step Guide

1. **Identify the Test Domain**
   - Determine what aspect of the system to test
   - Define the category (configuration, features, errors, etc.)

2. **Create the Dataset File**
   ```bash
   # Create new dataset file
   touch tests/data/golden_datasets/my_new_dataset.json
   ```

3. **Define Metadata**
   ```json
   {
     "metadata": {
       "name": "my_new_dataset",
       "description": "Description of what this dataset tests",
       "version": "1.0.0",
       "created": "2026-04-12",
       "total_queries": 10
     }
   }
   ```

4. **Add Test Queries**
   ```json
   {
     "queries": [
       {
         "id": "my-test-001",
         "query": "What is the specific question?",
         "expected_concepts": ["concept1", "concept2"],
         "forbidden_concepts": ["wrong_concept"],
         "category": "my_category",
         "expected_answer": "The expected answer text"
       }
     ]
   }
   ```

5. **Best Practices for Query Creation**
   - Use real user queries, not synthetic ones
   - Include edge cases and boundary conditions
   - Cover diverse topics within the domain
   - Ensure expected concepts are specific and verifiable
   - Forbidden concepts should be common misconceptions

6. **Validate the Dataset**
   ```bash
   # Test that the dataset loads correctly
   pytest tests/test_quantitative/test_golden_dataset.py::TestGoldenDataset::test_load_valid_dataset -v
   ```

7. **Run Tests with New Dataset**
   ```bash
   # Run tests using your new dataset
   pytest tests/test_quantitative/test_golden_dataset.py -v -k "my_category"
   ```

---

## Interpreting Test Results

### Understanding Pass/Fail Output

**Passing Test Example**:
```
tests/test_quantitative/test_performance.py::TestPerformance::test_query_response_time PASSED
```

**Failing Test Example**:
```
tests/test_quantitative/test_performance.py::TestPerformance::test_query_response_time FAILED

AssertionError: Performance thresholds exceeded:
  Mean response time: 6.234s (threshold: 5.0s)
  P95 latency: 9.123s (threshold: 8.0s)
  Total samples: 10
```

### Metrics Interpretation Guide

#### Performance Metrics
- **Mean < Threshold**: System is performing within acceptable bounds
- **P95 < Threshold**: 95% of requests meet SLA
- **Throughput >= Minimum**: System handles expected load

#### Consistency Metrics
- **Mean Consistency >= 0.8**: Answers are stable across runs
- **Variance < 0.05**: Low variance = reliable system
- **Embedding Stability >= 0.95**: Semantic representation is consistent

#### Semantic Similarity Metrics
- **Query-Answer >= 0.6**: Answer is relevant to the query
- **Query-Context >= 0.5**: Retrieved documents are related
- **Cross-Query Correlation**: Similar queries → similar answers

#### Precision/Recall Metrics
- **Precision@K**: Of K results shown, how many are relevant?
- **Recall@K**: Of all relevant results, how many did we find?
- **mAP**: Overall ranking quality across all queries
- **nDCG**: Ranking quality considering position importance

#### Golden Dataset Metrics
- **Pass Rate >= 80%**: Most queries produce acceptable answers
- **Concept Presence**: All expected concepts appear in answers
- **Forbidden Absence**: No incorrect concepts in answers

### Common Failure Patterns

| Failure Pattern | Likely Cause | Solution |
|----------------|--------------|----------|
| Low consistency variance | LLM non-determinism | Increase temperature stability |
| Low semantic similarity | Poor retrieval | Check embedding model |
| Low precision@K | Irrelevant results | Tune similarity threshold |
| High response time | Resource constraints | Scale resources or optimize |

---

## Troubleshooting

### Common Issues

#### MongoDB Connection Errors

```
RuntimeError: Cannot connect to MongoDB
```

**Solution**:
```bash
# Start MongoDB
docker-compose up -d

# Verify connection
secondbrain health
```

#### LLM Unavailable

```
pytest.skip("LLM unavailable")
```

**Solution**:
```bash
# Start Ollama service
ollama serve

# Pull required model
ollama pull llama2

# Verify service
curl http://localhost:11434/api/version
```

#### Embedding Model Loading Failures

```
OSError: Cannot find local checkpoint
```

**Solution**:
```bash
# Install sentence-transformers
pip install sentence-transformers

# Download model manually
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

#### Golden Dataset Not Found

```
FileNotFoundError: Golden dataset not found
```

**Solution**:
```bash
# Verify dataset exists
ls tests/data/golden_datasets/

# Check dataset name in test
grep "GOLDEN_DATASETS_DIR" tests/test_quantitative/conftest.py
```

#### Performance Test Timeouts

```
pytest-timeout: Test exceeded 120 seconds
```

**Solution**:
```bash
# Increase timeout
pytest tests/test_quantitative/test_performance.py --timeout=300 -v

# Or reduce test iterations
# Edit test file and reduce NUM_RUNS
```

#### CI/CD Skipping Tests

Tests marked with `@pytest.mark.optional` or `@pytest.mark.integration` may be skipped in CI.

**Solution**:
```bash
# Include all markers
pytest tests/test_quantitative/ -v -m ""

# Or explicitly include integration
pytest tests/test_quantitative/ -v -m "integration"
```

### Debugging Techniques

#### Enable Verbose Output
```bash
pytest tests/test_quantitative/ -v -s
```

#### Show Fixture Values
```bash
pytest tests/test_quantitative/ --fixtures
```

#### Run Single Test with Full Output
```bash
pytest tests/test_quantitative/test_performance.py::TestPerformance::test_query_response_time -v -s
```

#### Collect Test Information
```bash
pytest tests/test_quantitative/ --collect-only
```

#### Generate Test Report
```bash
pytest tests/test_quantitative/ --html=report.html --self-contained-html
```

### Performance Tuning

#### Optimize Test Execution
```bash
# Parallel execution
pytest tests/test_quantitative/ -n auto

# Only run failed tests
pytest tests/test_quantitative/ --ff

# Cache results
pytest tests/test_quantitative/ --cache-clear
```

#### Reduce Test Time
```bash
# Skip slow tests
pytest tests/test_quantitative/ -m "not slow"

# Reduce benchmark iterations
# Edit test file: NUM_RUNS = 5 (instead of 10)
```

---

## Configuration

### Environment Variables

Quantitative tests respect these environment variables:

```bash
# Threshold overrides
SECONDBRAIN_TEST_MEAN_RESPONSE_TIME_THRESHOLD=6.0
SECONDBRAIN_TEST_CONSISTENCY_THRESHOLD=0.75

# Service endpoints
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_OLLAMA_URL=http://localhost:11434
```

### Custom Thresholds

To customize thresholds for your environment:

1. Create `tests/test_quantitative/conftest_local.py`:
   ```python
   # Override default thresholds
   THRESHOLD_MEAN_RESPONSE_TIME = 10.0  # More lenient for slower hardware
   THRESHOLD_MIN_THROUGHPUT = 1.0
   ```

2. Or set via pytest command line:
   ```bash
   pytest tests/test_quantitative/ \
     --threshold-response-time=10.0 \
     --threshold-throughput=1.0
   ```

### Test Profile Configuration

Create `pytest.ini` or update `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "performance: Performance/benchmark tests",
    "consistency: Consistency validation tests",
    "semantic_similarity: Semantic similarity tests",
    "precision_recall: Information retrieval metrics",
    "golden_dataset: Golden dataset validation",
    "integration: Requires external services",
    "optional: May be skipped in CI"
]

addopts = [
    "-v",
    "--strict-markers",
    "--tb=short"
]
```

---

## Support

- **Framework Issues**: [GitHub Issues](https://github.com/your-username/secondbrain/issues)
- **Documentation**: [Developer Guide](../../../docs/developer-guide/TESTING.md)
- **Architecture**: [Architecture Docs](../../../docs/architecture/index.md)

---

## License

MIT License - See [LICENSE](../../../docs/LICENSE.md) for details.
