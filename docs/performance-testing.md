# Performance Testing & Regression Detection

This guide explains how to run performance benchmarks, detect regressions, and manage baselines in the SecondBrain project.

## Overview

The project uses `pytest-benchmark` for performance testing with the following capabilities:

- **Automated benchmarking** of document ingestion and processing
- **Baseline comparison** against known-good performance metrics
- **Regression detection** with configurable thresholds (default: 10%)
- **Pre-commit hooks** for early regression detection
- **Baseline management** for tracking performance over time

## Setup

### Install Dependencies

```bash
pip install -e ".[dev]"
```

The `dev` extra includes `pytest-benchmark` and all necessary tools.

### Initial Baseline Creation

Before regression checking can work, create an initial baseline:

```bash
# Run benchmarks and save as main baseline
./scripts/run_benchmarks.sh baseline main
```

This creates `benchmarks/baselines/main.json` with current performance metrics.

## Running Benchmarks

### Basic Benchmark Run

```bash
# Run all benchmarks
./scripts/run_benchmarks.sh run

# Or directly with pytest
pytest benchmarks/ --benchmark-only -v
```

### Compare Against Baseline

```bash
# Run and compare (fails if >10% regression)
./scripts/run_benchmarks.sh compare

# Custom threshold (15%)
BENCHMARK_THRESHOLD=0.15 ./scripts/run_benchmarks.sh compare
```

### Save New Baseline

```bash
# Save current results as new baseline
./scripts/run_benchmarks.sh baseline

# Save with custom name
./scripts/run_benchmarks.sh baseline develop
```

### Full Regression Check

```bash
# Run benchmarks + compare (recommended for CI)
./scripts/run_benchmarks.sh full
```

## Benchmark Comparison Commands

### Direct Script Usage

```bash
# Compare two benchmark result files
python scripts/benchmark_compare.py compare \
    --current benchmark-results.json \
    --baseline benchmarks/baselines/main.json \
    --threshold 0.10

# Save results to file
python scripts/benchmark_compare.py compare \
    --current benchmark-results.json \
    --baseline benchmarks/baselines/main.json \
    --output comparison-results.json

# Save new baseline
python scripts/benchmark_compare.py save-baseline \
    --input benchmark-results.json \
    --name main \
    --output-dir benchmarks/baselines
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BENCHMARK_BASELINE` | `benchmarks/baselines/main.json` | Baseline file path |
| `BENCHMARK_THRESHOLD` | `0.10` | Regression threshold (0.10 = 10%) |
| `BENCHMARK_OUTPUT` | `benchmark-results.json` | Results output file |

## Baseline Storage Strategy

### Directory Structure

```
benchmarks/
├── baselines/
│   ├── main.json          # Production baseline (from main branch)
│   ├── develop.json       # Development baseline
│   └── feature-xyz.json   # Feature branch baselines
└── test_ingestion_benchmarks.py
```

### Baseline File Format

```json
{
  "name": "main",
  "created_at": "2026-03-29T10:30:00",
  "benchmarks": [
    {
      "name": "test_ingest_single_document",
      "stats": {
        "mean": 0.045,
        "stddev": 0.002,
        "iterations": 100
      }
    }
  ]
}
```

### Baseline Management Best Practices

1. **Main Baseline**: Update only on main branch merges after verification
2. **Feature Baselines**: Create per-branch for performance-focused features
3. **Regular Updates**: Refresh baselines quarterly or after major optimizations
4. **Version Control**: Commit baselines to track performance history

## Regression Alerting

### Threshold Configuration

Default threshold is 10% regression. Configure per-use case:

```bash
# Strict (5%)
BENCHMARK_THRESHOLD=0.05 ./scripts/run_benchmarks.sh compare

# Lenient (20%)
BENCHMARK_THRESHOLD=0.20 ./scripts/run_benchmarks.sh compare
```

### Alert Levels

| Regression | Status | Action |
|------------|--------|--------|
| < 10% | ✅ OK | No action needed |
| 10-20% | ⚠️ Warning | Review before merge |
| > 20% | ❌ Critical | Investigate immediately |

### Output Interpretation

```
BENCHMARK COMPARISON RESULTS
======================================================================
Timestamp: 2026-03-29T10:30:00
Regression Threshold: 10.0%
----------------------------------------------------------------------

SUMMARY:
  Total Benchmarks: 3
  Passed: 2
  Regressions: 1
  Improvements: 0
  Regression Rate: 33.3%

⚠️  REGRESSIONS DETECTED:
  ❌ test_ingest_single_document
      Current: 52.34ms
      Baseline: 45.12ms
      Regression: 16.0%

======================================================================
❌ PERFORMANCE REGRESSION DETECTED!
   1 benchmark(s) exceeded 10.0% threshold
```

## Pre-commit Hook Integration

### Enable Pre-commit Benchmark Check

Add to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: benchmark-check
      name: Benchmark Performance Check
      entry: scripts/pre-commit-benchmark.sh
      language: system
      pass_filenames: false
      stages: [pre-commit]
      # Only run when benchmark files change
      files: ^benchmarks/
```

### Pre-commit Hook Behavior

- **Skips** if no baseline exists
- **Runs** quick benchmarks (3 iterations, 30s max)
- **Compares** against main baseline
- **Fails** commit if >10% regression detected
- **Bypass** with `BENCHMARK_SKIP=1`

### Skipping for Specific Cases

```bash
# Skip for single commit
BENCHMARK_SKIP=1 git commit -m "WIP"

# Skip for entire session
export BENCHMARK_SKIP=1
```

## CI/CD Integration (Manual)

Since GitHub Actions is prohibited per project policy, here's how to integrate with external CI:

### GitLab CI Example

```yaml
benchmark:
  stage: test
  image: python:3.12
  script:
    - pip install -e ".[dev]"
    - ./scripts/run_benchmarks.sh full
  artifacts:
    reports:
      performance: benchmark-comparison.json
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == "main"
```

### Jenkins Example

```groovy
pipeline {
    agent any
    stages {
        stage('Benchmarks') {
            steps {
                sh 'pip install -e ".[dev]"'
                sh './scripts/run_benchmarks.sh full'
            }
            post {
                always {
                    archiveArtifacts artifacts: 'benchmark-*.json'
                }
            }
        }
    }
}
```

### GitHub Actions (Reference Only)

**Note**: Prohibited per project policy. Use local pre-commit hooks instead.

If manual integration is absolutely needed:

```yaml
# DO NOT COMMIT - For reference only
name: Performance Benchmarks
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run benchmarks
        run: ./scripts/run_benchmarks.sh full
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: benchmark-*.json
```

## Benchmark Best Practices

### Writing Benchmarks

```python
import pytest

def test_fast_operation(benchmark):
    """Benchmark should be fast (<1s) and repeatable."""
    
    def operation():
        # Code to benchmark
        result = process_data()
        return result
    
    # Benchmark runs multiple iterations automatically
    result = benchmark(operation)
    
    # Verify correctness
    assert result is not None
```

### Benchmark Fixtures

```python
@pytest.fixture
def benchmark_data():
    """Setup benchmark data once."""
    return create_test_data()

def test_operation_with_data(benchmark, benchmark_data):
    def operation():
        return process(benchmark_data)
    
    result = benchmark(operation)
```

### Avoiding Common Pitfalls

1. **Don't** include setup/teardown in benchmark
2. **Don't** benchmark one-off operations (use warmup)
3. **Do** use `--benchmark-only` to skip non-benchmark tests
4. **Do** run benchmarks in isolation for accuracy

## Troubleshooting

### "No baseline found"

```bash
# Create initial baseline
./scripts/run_benchmarks.sh baseline main
```

### "Benchmarks failed to run"

```bash
# Check dependencies
pip install -e ".[dev]"

# Run with verbose output
pytest benchmarks/ --benchmark-only -v -s
```

### High Variance in Results

```bash
# Increase iterations
pytest benchmarks/ --benchmark-min-rounds=10

# Check system load (avoid running during high CPU usage)
```

### False Positive Regressions

1. Check system load/temperature
2. Run multiple times to confirm
3. Consider increasing threshold temporarily
4. Update baseline if optimization is intentional

## Advanced Usage

### Custom Benchmark Groups

```bash
# Run specific benchmark file
pytest benchmarks/test_ingestion_benchmarks.py --benchmark-only

# Run specific test
pytest benchmarks/ -k "test_ingest_single" --benchmark-only
```

### Export Formats

```bash
# JSON (default)
pytest benchmarks/ --benchmark-json=output.json

# YAML
pytest benchmarks/ --benchmark-histogram=plots/

# Console summary
pytest benchmarks/ --benchmark-only --benchmark-summary
```

### Performance Profiling

```bash
# With line profiler
pytest benchmarks/ --benchmark-profile

# With memory profiler
pytest benchmarks/ --benchmark-memory-usage
```

## Maintenance

### Quarterly Baseline Review

```bash
# Compare all baselines
for baseline in benchmarks/baselines/*.json; do
    echo "=== $baseline ==="
    python scripts/benchmark_compare.py compare \
        --current benchmark-results.json \
        --baseline "$baseline"
done
```

### Archive Old Baselines

```bash
# Move old baselines to archive
mkdir -p benchmarks/baselines/archive
mv benchmarks/baselines/old-*.json benchmarks/baselines/archive/
```

## References

- [pytest-benchmark Documentation](https://pytest-benchmark.readthedocs.io/)
- [Pre-commit Hooks](https://pre-commit.com/)
- [Project Testing Guide](tests/README.md)
