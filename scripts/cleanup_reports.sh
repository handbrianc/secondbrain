#!/usr/bin/env bash
# Script to clean up old security and SBOM report files
# Removes JSON and MD report files before generating new ones

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Cleaning up old security and SBOM reports..."
echo ""

# Define directories to clean
REPORT_DIRS=(
    "docs/security"
    "site/security"
    "reports"  # If centralized reports directory exists
)

# Track what we delete
deleted_count=0
deleted_files=()

# Function to delete report files in a directory
cleanup_directory() {
    local dir="$1"
    local full_path="$PROJECT_ROOT/$dir"
    
    if [ ! -d "$full_path" ]; then
        echo "Directory not found: $dir (skipping)"
        return
    fi
    
    echo "Scanning: $dir"
    
    # Find and remove JSON report files (excluding package.json and cache files)
    while IFS= read -r -d '' file; do
        # Skip node_modules, cache directories, and package.json
        if [[ "$file" == *"node_modules"* ]] || \
           [[ "$file" == *".cache"* ]] || \
           [[ "$file" == *".mypy_cache"* ]] || \
           [[ "$file" == *".pytest_cache"* ]] || \
           [[ "$file" == *".ruff_cache"* ]] || \
           [[ "$file" == *".venv"* ]] || \
           [[ "$file" == *"venv"* ]] || \
           [[ "$(basename "$file")" == "package.json" ]] || \
           [[ "$(basename "$file")" == "sbom.json" ]]; then
            continue
        fi
        
        deleted_files+=("$file")
        ((deleted_count++))
    done < <(find "$full_path" -type f \( -name "*report*.json" -o -name "*security*.json" -o -name "*sbom*.json" -o -name "*vulnerability*.json" -o -name "*bandit*.json" -o -name "*safety*.json" \) -print0 2>/dev/null)
    
    # Find and remove MD report files
    while IFS= read -r -d '' file; do
        # Skip main documentation files
        if [[ "$(basename "$file")" == "index.md" ]] || \
           [[ "$(basename "$file")" == "security.md" ]] || \
           [[ "$(basename "$file")" == "README.md" ]]; then
            continue
        fi
        
        deleted_files+=("$file")
        ((deleted_count++))
    done < <(find "$full_path" -type f \( -name "*report*.md" -o -name "*security*.md" -o -name "*vulnerability*.md" -o -name "*remediation*.md" -o -name "*scan*.md" -o -name "*findings*.md" \) -print0 2>/dev/null)
}

# Clean each directory
for dir in "${REPORT_DIRS[@]}"; do
    cleanup_directory "$dir"
done

# Also clean root directory for any stray report files
echo ""
echo "Checking root directory for stray report files..."
while IFS= read -r -d '' file; do
    # Only clean specific report files in root
    basename_file=$(basename "$file")
    if [[ "$basename_file" == "sbom.json" ]] || \
       [[ "$basename_file" == "sbom.spdx" ]] || \
       [[ "$basename_file" == "*security_report.md" ]]; then
        deleted_files+=("$file")
        ((deleted_count++))
    fi
done < <(find "$PROJECT_ROOT" -maxdepth 1 -type f \( -name "sbom.json" -o -name "sbom.spdx" -o -name "*security_report.md" \) -print0 2>/dev/null)

# Display summary
echo ""
echo "=========================================="
echo "Cleanup Summary"
echo "=========================================="

if [ $deleted_count -eq 0 ]; then
    echo "No old report files found."
else
    echo "Deleted $deleted_count file(s):"
    echo ""
    for file in "${deleted_files[@]}"; do
        echo "  - $file"
    done
fi

echo ""
echo "Cleanup complete."
