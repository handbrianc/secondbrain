#!/bin/bash
# Quality validation script for SecondBrain project
# Run all quality checks before committing

set -e

echo "=========================================="
echo "Running SecondBrain Quality Checks"
echo "=========================================="

echo ""
echo "1. Ruff linting..."
ruff check src/
ruff format --check src/

echo ""
echo "2. Mypy type checking..."
mypy src/secondbrain

echo ""
echo "3. Running quick tests..."
pytest -q --tb=no

echo ""
echo "=========================================="
echo "✓ All quality checks passed!"
echo "=========================================="
