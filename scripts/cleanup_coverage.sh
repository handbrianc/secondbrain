#!/usr/bin/env bash
# Script to clean up coverage files after test runs

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Cleaning up coverage files..."

rm -f "$PROJECT_ROOT"/.coverage*
rm -rf "$PROJECT_ROOT"/htmlcov

echo "Cleanup complete."
