# Test Performance Analysis

## Why Tests Take So Long to Run

### Root Cause Analysis

The SecondBrain test suite has **two distinct performance profiles**:

#### 1. Unit Tests (FAST - 1-2 seconds)
- **Example**: `tests/test_storage/` - 225 tests in 1.30s
- **Why fast**: Use mocked components, no real ML models
- **When to run**: Pre-commit, development loop

#### 2. Quantitative Tests (SLOW - 50+ seconds)
- **Example**: `tests/test_quantitative/test_precision_recall.py` - 9 tests in 50s
- **Why slow**: Real embedding generation (2+ seconds per query)
- **When to run**: CI/CD, pre-merge validation, performance monitoring

### The Bottleneck: Embedding Generation

Each quantitative test performs semantic search, which requires:

1. **Query embedding**: Convert search query to vector (~2s with all-MiniLM-L6-v2)
2. **Vector similarity search**: MongoDB cosine similarity (~0.1s)
3. **Result ranking**: Sort and filter results (~0.1s)

**Total per test**: ~6 seconds (mostly embedding generation)

```python
# Example: One test takes this long
def test_precision_at_k(self):
    query = "What is SecondBrain?"
    results = searcher.search(query, top_k=5)  # ← 2+ seconds here
    # ... rest of test: ~0.5 seconds
```

### What Was Optimized

✅ **Fixture scoping**: Reduced from function → session/module scope
- Eliminates repeated initialization overhead
- Impact: Minimal (<1s saved)

✅ **Pre-computed embeddings**: Seed data uses pre-computed embeddings
- Eliminates ~3-4 minutes of initial seeding time
- Impact: Significant for first run, but tests still embed queries

✅ **Mock embedding generator**: Created for future fast tests
- Provides microsecond embeddings instead of seconds
- Impact: Not yet used in tests (see recommendations)

## Recommended Solutions

### Solution 1: Separate Fast vs Performance Tests (RECOMMENDED)

**Create two test profiles:**

```bash
# Fast validation (development)
pytest tests/test_quantitative/ -m "not performance"

# Full performance testing (CI/CD)
pytest tests/test_quantitative/ -m "performance"
```

**Implementation:**

1. Add marker to performance-critical tests:
```python
@pytest.mark.performance  # Only run in full test suite
def test_precision_at_k(self):
    ...
```

2. Update `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    # ... existing markers ...
    "fast: quick validation tests using mock embeddings",
    "performance: full performance tests using real embeddings",
]
```

3. Create fast versions using mock embeddings:
```python
# tests/test_quantitative/test_precision_fast.py
from secondbrain.embedding.mock import MockEmbeddingGenerator

@pytest.fixture
def embed_gen():
    return MockEmbeddingGenerator()  # Microsecond embeddings
```

### Solution 2: Reduce Test Data Size

**Current**: 27 chunks with real embeddings
**Recommended**: 10 chunks for fast tests

```python
# tests/data/fast_test_embeddings.json
# Smaller dataset for development
```

### Solution 3: Cache Test Results

**Use pytest-cacheprovider**:
```bash
# Run only changed tests
pytest --lf  # Last failed
pytest --ff  # Failed first
```

### Solution 4: Parallelize Unit Tests

**Already configured**:
```bash
# Fast tests can be parallelized
pytest tests/test_storage/ -n auto  # 8x speedup
```

**Note**: Quantitative tests CANNOT be parallelized due to MongoDB contention.

## Performance Benchmarks

| Test Suite | Count | Time | Type | Parallelizable |
|------------|-------|------|------|----------------|
| test_storage/ | 225 | 1.30s | Unit | ✅ Yes |
| test_config/ | 50+ | <1s | Unit | ✅ Yes |
| test_quantitative/precision_recall | 9 | 50s | Integration | ❌ No |
| test_quantitative/golden_dataset | 10+ | 60s | Integration | ❌ No |
| **Total (all)** | 1674 | ~30 min | Mixed | Partial |

## Recommended Workflow

### Development Loop (30 seconds)
```bash
# Run only fast tests
pytest tests/test_storage/ tests/test_config/ -n auto
```

### Pre-Merge (5 minutes)
```bash
# Run fast tests + selected integration tests
pytest tests/ -m "not performance" -n auto
```

### Nightly/CI (30 minutes)
```bash
# Full test suite
pytest tests/
```

## How to Use Mock Embeddings

For tests that don't need real embedding quality:

```python
from secondbrain.embedding.mock import MockEmbeddingGenerator

@pytest.fixture
def embed_gen():
    return MockEmbeddingGenerator(dimension=384)

def test_something(embed_gen):
    # Instant embedding generation
    embedding = embed_gen.generate("test text")
    assert len(embedding) == 384
```

## Conclusion

**Tests are slow because they're MEASURING real performance.**

### Performance Test Profiles (NOW AVAILABLE)

| Profile | Command | Runtime | Use Case |
|---------|---------|---------|----------|
| **Unit Tests** | `pytest tests/test_storage/ -n auto` | ~1s | Development loop |
| **Metrics Unit Tests** | `pytest -m "fast_test and unit"` | **0.1s** | Rapid metrics validation |
| **Fast Quant** | `pytest -m "fast_test"` | **39s** | Limited fast validation (MongoDB-bound) |
| **Standard** | `pytest -m "not performance"` | ~2 min | Pre-merge validation |
| **Full** | `pytest -m "performance"` | **65s** | CI/CD nightly |

**Note**: 
- `test_precision_unit.py` uses mocked Searcher - **0.1s** but doesn't test real system
- `test_precision_fast.py` uses mock embeddings - **39s** (MongoDB is bottleneck)
- `test_precision_recall.py` uses real embeddings - **65s** (full system test)

### What's Been Optimized

✅ **Unit tests**: Already fast (1.3s for 225 tests)
- No changes needed - they use mocked components

✅ **Test markers added**: Can now separate fast vs slow tests
- `@pytest.mark.performance` - Real embedding tests (slow)
- `@pytest.mark.fast_test` - Mock embedding tests (fast)
- `@pytest.mark.unit` - Fully mocked tests (fastest)

✅ **Fast test variants created**:
- `test_precision_unit.py` - Mocked Searcher (**0.1s** for 9 tests)
- `test_precision_fast.py` - Mock embeddings, real MongoDB (**40s** for 9 tests)

✅ **Pre-computed embeddings**: For faster seeding
- Reduces initial seeding time from ~3-4 min to seconds

### The Reality: Database Operations Are the Real Bottleneck

**Mock embeddings save ~1-2 seconds per test**, but fast tests still take ~4.3s each due to:
- MongoDB connection initialization: ~1-2s
- Vector search query execution: ~0.5s
- Result processing and metric calculation: ~0.5s
- Fixture setup/teardown: ~1s
- **Total per test**: ~4.3s (9 tests = 39s)

**To get truly fast tests (<1s):** Mock the entire Searcher (see `test_precision_unit.py`)

**To get truly fast tests (<1s):**
- Would need to mock the entire Searcher
- But then you're not testing the real system
- Tradeoff: Speed vs. Confidence

### Recommended Workflow

**Development (30 seconds):**
```bash
# Run only unit tests
pytest tests/test_storage/ tests/test_config/ -n auto
```

**Pre-commit (2 minutes):**
```bash
# Run unit tests + fast quantitative tests
pytest -m "fast_test or unit" -n auto
```

**Pre-merge (5 minutes):**
```bash
# Run all non-performance tests
pytest -m "not performance" -n auto
```

**Nightly CI (30 minutes):**
```bash
# Full test suite including performance tests
pytest tests/
```

### Bottom Line

**Quantitative tests ARE supposed to be slow** when testing real system performance.

The optimizations provided:
1. ✅ **Separate fast validation** from slow performance tests
2. ✅ **Pre-computed embeddings** for faster seeding
3. ✅ **Test markers** for flexible test selection
4. ⚠️ **Mock embeddings** - saves 1-2s per test, but database is still the bottleneck

**If you need sub-second tests:** Mock the entire Searcher (but you lose confidence in real system behavior).

## Next Steps

1. **Add test markers** (`@pytest.mark.fast`, `@pytest.mark.performance`)
2. **Update CI/CD** to run different test profiles
3. **Document expected runtimes** in README
4. **Consider mocking** for non-critical quantitative tests
