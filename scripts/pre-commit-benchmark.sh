#!/bin/bash
#
# Pre-commit Hook: Performance Regression Check
#
# This hook runs a quick benchmark check before commits to catch
# major performance regressions early.
#
# Configuration:
#   Set BENCHMARK_SKIP=1 to skip this hook (e.g., for CI that runs full benchmarks)
#   Set BENCHMARK_FAST=1 to run only fast benchmarks
#
# Note: This is opt-in. Add to .pre-commit-config.yaml to enable:
#
#   - repo: local
#     hooks:
#       - id: benchmark-check
#         name: Benchmark Performance Check
#         entry: scripts/pre-commit-benchmark.sh
#         language: system
#         pass_filenames: false
#         stages: [pre-commit]
#         always_run: false  # Only run when benchmark files change
#

# Skip if explicitly disabled
if [ "${BENCHMARK_SKIP:-0}" = "1" ]; then
    echo "[benchmark] Skipped via BENCHMARK_SKIP"
    exit 0
fi

# Colors
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}[benchmark]${NC} Checking for performance regressions..."

# Check if baseline exists
BASELINE_FILE="benchmarks/baselines/main.json"
if [ ! -f "${BASELINE_FILE}" ]; then
    echo -e "${YELLOW}[benchmark]${NC} No baseline found. Skipping regression check."
    echo "   Run 'scripts/run_benchmarks.sh baseline' to create initial baseline"
    exit 0
fi

# Quick benchmark run (single iteration for speed)
echo -e "${YELLOW}[benchmark]${NC} Running quick benchmark check..."

# Set aggressive timeout for pre-commit
export PYTEST_TIMEOUT=30

# Run only fast benchmarks if requested
if [ "${BENCHMARK_FAST:-0}" = "1" ]; then
    echo -e "${YELLOW}[benchmark]${NC} Fast mode enabled"
    pytest benchmarks/ \
        --benchmark-json=benchmark-results.json \
        --benchmark-only \
        --benchmark-min-rounds=1 \
        --benchmark-max-time=5 \
        -v \
        -q || {
            echo -e "${RED}[benchmark]${NC} Benchmarks failed to run"
            exit 1
        }
else
    pytest benchmarks/ \
        --benchmark-json=benchmark-results.json \
        --benchmark-only \
        --benchmark-min-rounds=3 \
        --benchmark-max-time=30 \
        -v \
        -q || {
            echo -e "${RED}[benchmark]${NC} Benchmarks failed to run"
            exit 1
        }
fi

# Compare against baseline
echo -e "${YELLOW}[benchmark]${NC} Comparing against baseline..."

python scripts/benchmark_compare.py compare \
    --current benchmark-results.json \
    --baseline "${BASELINE_FILE}" \
    --threshold 0.10 \
    --output benchmark-comparison.json

exit_code=$?

# Clean up
rm -f benchmark-results.json

if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}[benchmark]${NC} ✅ No performance regressions detected"
else
    echo -e "${RED}[benchmark]${NC} ❌ Performance regression detected!"
    echo "   See benchmark-comparison.json for details"
    echo "   To bypass: export BENCHMARK_SKIP=1"
    echo "   To update baseline: scripts/run_benchmarks.sh baseline"
fi

exit $exit_code
