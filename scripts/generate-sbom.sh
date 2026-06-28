#!/bin/bash
# SBOM generation script using cyclonedx-py

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "📋 Generating Software Bill of Materials (SBOM)..."

# Ensure we're in the project root
cd "$PROJECT_ROOT"

# Clean up old SBOM files before generating new ones
echo ""
echo "Cleaning up old SBOM files..."
if [ -f "$PROJECT_ROOT/sbom.json" ]; then
    rm -f "$PROJECT_ROOT/sbom.json"
    echo "  - Removed: sbom.json"
fi
if [ -f "$PROJECT_ROOT/sbom.spdx" ]; then
    rm -f "$PROJECT_ROOT/sbom.spdx"
    echo "  - Removed: sbom.spdx"
fi
echo "SBOM cleanup complete."
echo ""

# Generate JSON SBOM using CycloneDX
echo "Generating CycloneDX JSON SBOM..."
cyclonedx-py environment -o sbom.json --of JSON
echo "✅ JSON SBOM generated: sbom.json"
echo ""

# Convert to SPDX format using Python module
echo "Converting to SPDX format..."
python3 "$SCRIPT_DIR/sbom_converter.py"

echo ""
echo "=========================================="
echo "SBOM generation complete!"
echo "=========================================="
echo "  - JSON format: sbom.json"
echo "  - SPDX format: sbom.spdx"
