#!/bin/bash
# Run the whole test suite: the Python suite (pytest) AND the MCP server's Rust
# suite (cargo fmt/clippy/test), with per-suite results and a single verdict.
#
# Usage:
#   ./scripts/run_all_tests.sh              # both suites
#   ./scripts/run_all_tests.sh --python-only
#   ./scripts/run_all_tests.sh --rust-only
#
# Nothing is auto-installed: pytest must be available (see requirements-dev.txt)
# and cargo for the Rust side (CI gates both via test-quality-gates.yml and
# rust-checks.yml). The Rust suite is skipped with a note when the toolchain
# or the mcp-server/ tree is absent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="$PROJECT_ROOT/mcp-server"

RUN_PYTHON=1
RUN_RUST=1
for arg in "$@"; do
    case "$arg" in
        --python-only) RUN_RUST=0 ;;
        --rust-only) RUN_PYTHON=0 ;;
        *)
            echo "Unknown option: $arg" >&2
            echo "Usage: $0 [--python-only | --rust-only]" >&2
            exit 2
            ;;
    esac
done

FAILED=0

run_python_suite() {
    echo "=========================================="
    echo "Python suite (pytest)"
    echo "=========================================="
    if ! command -v pytest &> /dev/null; then
        echo "SKIP: pytest not found (set up the environment with: pip install -e \".[dev]\")"
        FAILED=1
        return 0
    fi
    # pytest.ini_options addopts supply the full fast-suite config:
    # --timeout=120 --dist=loadfile -n auto -m 'not chaos'. Coverage is a CI
    # gate (test-quality-gates.yml), deliberately not passed here.
    if pytest; then
        echo "Python suite: PASS"
    else
        echo "Python suite: FAIL"
        FAILED=1
    fi
}

run_rust_suite() {
    echo "=========================================="
    echo "Rust suite (mcp-server: cargo fmt/clippy/test)"
    echo "=========================================="
    if [ ! -d "$MCP_DIR" ]; then
        echo "SKIP: $MCP_DIR does not exist"
        return 0
    fi
    if ! command -v cargo &> /dev/null; then
        echo "SKIP: cargo not found (rustup toolchain required; CI runs rust-checks.yml)"
        return 0
    fi
    local ok=1
    if ! cargo fmt --manifest-path "$MCP_DIR/Cargo.toml" --check; then
        echo "cargo fmt --check: FAIL"; ok=0
    fi
    if ! cargo clippy --manifest-path "$MCP_DIR/Cargo.toml" --all-targets -- -D warnings; then
        echo "cargo clippy: FAIL"; ok=0
    fi
    if ! cargo test --manifest-path "$MCP_DIR/Cargo.toml"; then
        echo "cargo test: FAIL"; ok=0
    fi
    if [ "$ok" -eq 1 ]; then
        echo "Rust suite: PASS"
    else
        echo "Rust suite: FAIL"
        FAILED=1
    fi
}

[ "$RUN_PYTHON" -eq 1 ] && run_python_suite
[ "$RUN_RUST" -eq 1 ] && run_rust_suite

echo "=========================================="
if [ "$FAILED" -eq 0 ]; then
    echo "All requested suites PASSED"
else
    echo "ONE OR MORE SUITES FAILED"
fi
echo "=========================================="
exit "$FAILED"
