# Performance Benchmarking Quick Start

## 🚀 Quick Setup (2 minutes)

1. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

2. **Run initial benchmarks:**
   ```bash
   ./scripts/run_benchmarks.sh baseline main
   ```

3. **Done!** You're ready to detect regressions.

## 📊 Common Commands

### Run Benchmarks
```bash
./scripts/run_benchmarks.sh run
```

### Check for Regressions
```bash
./scripts/run_benchmarks.sh compare
```

### Update Baseline (after optimizations)
```bash
./scripts/run_benchmarks.sh baseline
```

## 🎯 Key Files

| File | Purpose |
|------|---------|
| `scripts/run_benchmarks.sh` | Main benchmark runner |
| `scripts/benchmark_compare.py` | Regression detection |
| `scripts/pre-commit-benchmark.sh` | Pre-commit hook |
| `benchmarks/baselines/main.json` | Performance baseline |
| `docs/performance-testing.md` | Full documentation |

## ⚙️ Configuration

Set environment variables to customize:

```bash
# Stricter threshold (5%)
BENCHMARK_THRESHOLD=0.05 ./scripts/run_benchmarks.sh compare

# Use custom baseline
BENCHMARK_BASELINE=benchmarks/baselines/develop.json ./scripts/run_benchmarks.sh compare
```

## 🚫 Skip Benchmarks

```bash
# Skip for single commit
BENCHMARK_SKIP=1 git commit -m "WIP"

# Skip permanently (not recommended)
export BENCHMARK_SKIP=1
```

## 📈 Understanding Results

```
✅ All benchmarks within acceptable range
   - <10% change: OK
   - 10-20%: Review needed
   - >20%: Investigate immediately
```

## 🔧 Enable Pre-commit Hook

Add to `.pre-commit-config.yaml` (already added):

```yaml
- repo: local
  hooks:
    - id: benchmark-check
      name: Benchmark Performance Check
      entry: scripts/pre-commit-benchmark.sh
      language: system
      pass_filenames: false
      files: ^benchmarks/
```

Then run:
```bash
pre-commit install
```

## 📖 Full Documentation

See [docs/performance-testing.md](docs/performance-testing.md) for:
- Detailed configuration
- CI/CD integration examples
- Benchmark best practices
- Troubleshooting guide

---

**Project Policy**: GitHub Actions is prohibited. Use local pre-commit hooks for performance validation.
