# Test Performance Optimization Guide

## Current Problems

1. **Slow startup**: Single test takes ~30 seconds due to pytest-cov + xdist overhead
2. **Worker failures**: Coverage data not returned from xdist workers
3. **Over-engineering**: 20+ parallel workers for 531 tests is excessive
4. **Hypothesis default**: 50 examples per property test is too many for CI

## Optimized Test Commands

### Fast Profile (Pre-commit / Local Dev)
```bash
# Skip coverage, use fewer workers
pytest -m "not integration and not slow" -n 4 --no-cov

# Or even faster - no parallelization for quick feedback
pytest -m "not integration and not slow" --no-cov
```

### Balanced Profile (PR Validation)
```bash
# Limited workers, no coverage
pytest -m "not integration" -n 8 --no-cov

# Or with coverage but single process
pytest -m "not integration" --cov=secondbrain --cov-report=term-missing
```

### Full Profile (Nightly / Release)
```bash
# Full coverage with parallel workers
pytest -n 12 --cov=secondbrain --cov-report=html --cov-report=term-missing

# Include integration tests
pytest --cov=secondbrain --cov-report=term-missing
```

## Configuration Changes

### Option 1: Modify pyproject.toml defaults

Update `[tool.pytest.ini_options]` in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
# Reduced workers, coverage disabled by default for speed
addopts = "-m 'not slow' -n 8 --no-cov"
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
# ... rest of config
```

### Option 2: Create pytest profiles

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
# Default: fast profile for local dev
addopts = "-m 'not slow' -n 8 --no-cov"

# Profiles for different use cases
markers = [
    # ... existing markers
    "fast_profile: Run with minimal overhead",
    "balanced_profile: Medium coverage",
    "full_profile: Complete validation",
]
```

## Specific Optimizations

### 1. Reduce xdist workers
**Current**: `-n auto` (uses all CPU cores, ~20+ workers)
**Recommended**: `-n 4` or `-n 8` for better coverage collection

```bash
# Change in pyproject.toml
addopts = "--cov=secondbrain --cov-report=term-missing --cov-fail-under=80 -m 'not slow' -n 4 --dist loadscope"
```

### 2. Disable coverage for local dev
**Current**: Coverage always enabled
**Recommended**: Coverage only for CI/release

```bash
# Add to .env or shell alias
alias pytest-fast="pytest --no-cov -n 4"
```

### 3. Reduce Hypothesis examples
**Current**: `@settings(max_examples=50)`
**Recommended**: `@settings(max_examples=10)` for faster feedback

Update `tests/test_property_based/test_properties.py`:
```python
@settings(max_examples=10)  # Was 50
```

### 4. Use --no-cov flag locally
Add to shell config (`~/.bashrc` or `~/.zshrc`):
```bash
alias pytest="pytest --no-cov -n 4"
alias pytest-full="pytest --cov=secondbrain --cov-report=term-missing"
```

### 5. Cache coverage data
For CI, use coverage caching:
```bash
pytest --cov=secondbrain --cov-append -n 8
```

### 6. Skip expensive fixtures
Add fixture markers to skip heavy setup:
```python
@pytest.mark.no_mongo
def test_something():
    # Skip MongoDB setup
```

## Expected Performance Improvements

| Profile | Command | Current | Optimized | Speedup |
|---------|---------|---------|-----------|---------|
| **Fast** | `pytest -m "not integration"` | ~42s | ~5s | **8x faster** |
| **Balanced** | `pytest -m "not slow" -n 8` | ~42s | ~10s | **4x faster** |
| **Full** | `pytest --cov` | ~42s | ~25s | **1.7x faster** |

## Recommended Default Commands

### For Developers
```bash
# Quick local validation
pytest -m "not integration" -n 4 --no-cov

# With coverage (less frequent)
pytest --cov=secondbrain --cov-report=term-missing
```

### For CI/CD
```bash
# PR validation
pytest -m "not integration" -n 8 --cov=secondbrain --cov-report=xml

# Nightly build
pytest --cov=secondbrain --cov-report=html --cov-report=xml
```

## Migration Steps

1. **Update pyproject.toml** (optional):
   ```toml
   addopts = "-m 'not slow' -n 4 --no-cov"
   ```

2. **Reduce Hypothesis examples** in `test_properties.py`:
   ```python
   @settings(max_examples=10)  # Was 50
   ```

3. **Add shell aliases** for common workflows:
   ```bash
   alias pytest-fast="pytest --no-cov -n 4"
   alias pytest-full="pytest --cov=secondbrain"
   ```

4. **Document in README**:
   Update the "Quality Checks" section with new commands

## Trade-offs

| Optimization | Benefit | Cost |
|--------------|---------|------|
| `--no-cov` | 3-5x faster | No coverage feedback |
| `-n 4` instead of `-n auto` | Better coverage collection | Slightly slower parallelization |
| `max_examples=10` | 5x faster property tests | Less thorough property testing |
| Skip integration tests | 2-3x faster | Less end-to-end validation |

## Conclusion

The main bottleneck is **pytest-cov + xdist interaction**. By reducing workers and disabling coverage for local development, you can achieve **4-8x speedup** for most test runs.
