#!/bin/bash
#
# Performance Benchmark Runner
#
# This script runs benchmarks and manages baseline comparisons.
# It's designed for local development and CI integration.
#
# Usage:
#   ./scripts/run_benchmarks.sh run              # Run benchmarks only
#   ./scripts/run_benchmarks.sh compare          # Run and compare against baseline
#   ./scripts/run_benchmarks.sh baseline         # Run and save as new baseline
#   ./scripts/run_benchmarks.sh full             # Full regression check
#
# Environment Variables:
#   BENCHMARK_BASELINE    - Path to baseline file (default: benchmarks/baselines/main.json)
#   BENCHMARK_THRESHOLD   - Regression threshold (default: 0.10 for 10%)
#   BENCHMARK_OUTPUT      - Output file for results (default: benchmark-results.json)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BASELINE_FILE="${BENCHMARK_BASELINE:-benchmarks/baselines/main.json}"
THRESHOLD="${BENCHMARK_THRESHOLD:-0.10}"
OUTPUT_FILE="${BENCHMARK_OUTPUT:-benchmark-results.json}"
BASELINE_DIR="benchmarks/baselines"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

run_benchmarks() {
    log_info "Running benchmarks..."
    pytest benchmarks/ \
        --benchmark-json="${OUTPUT_FILE}" \
        --benchmark-only \
        -v
    
    log_info "Benchmark results saved to: ${OUTPUT_FILE}"
}

compare_benchmarks() {
    if [ ! -f "${BASELINE_FILE}" ]; then
        log_warn "No baseline file found at ${BASELINE_FILE}"
        log_info "Run 'save-baseline' first to create a baseline"
        return 1
    fi
    
    log_info "Comparing against baseline: ${BASELINE_FILE}"
    python scripts/benchmark_compare.py compare \
        --current "${OUTPUT_FILE}" \
        --baseline "${BASELINE_FILE}" \
        --threshold "${THRESHOLD}"
}

save_baseline() {
    local baseline_name="${1:-main}"
    
    if [ ! -f "${OUTPUT_FILE}" ]; then
        log_error "No benchmark results found. Run benchmarks first."
        return 1
    fi
    
    mkdir -p "${BASELINE_DIR}"
    
    log_info "Saving baseline: ${baseline_name}"
    python scripts/benchmark_compare.py save-baseline \
        --input "${OUTPUT_FILE}" \
        --name "${baseline_name}" \
        --output-dir "${BASELINE_DIR}"
    
    log_info "Baseline saved to: ${BASELINE_DIR}/${baseline_name}.json"
}

show_help() {
    cat << HELP
Performance Benchmark Runner

Usage: $0 <command> [options]

Commands:
    run                     Run benchmarks only
    compare                 Run benchmarks and compare against baseline
    baseline [name]         Run benchmarks and save as new baseline
    full                    Full regression check (run + compare)
    help                    Show this help message

Environment Variables:
    BENCHMARK_BASELINE      Path to baseline file
                            (default: benchmarks/baselines/main.json)
    BENCHMARK_THRESHOLD     Regression threshold 0.0-1.0
                            (default: 0.10 for 10%)
    BENCHMARK_OUTPUT        Output file for results
                            (default: benchmark-results.json)

Examples:
    # Run benchmarks only
    $0 run

    # Compare against custom baseline
    BENCHMARK_BASELINE=benchmarks/baselines/develop.json $0 compare

    # Save new baseline with custom name
    $0 baseline feature-branch

    # Full regression check with 15% threshold
    BENCHMARK_THRESHOLD=0.15 $0 full

HELP
}

# Main
case "${1:-help}" in
    run)
        run_benchmarks
        ;;
    compare)
        run_benchmarks
        compare_benchmarks
        ;;
    baseline)
        run_benchmarks
        save_baseline "${2:-main}"
        ;;
    full)
        run_benchmarks
        compare_benchmarks
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
