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

# Install cyclonedx-bom if not already installed
if ! command -v cyclonedx-py &> /dev/null; then
    echo "Installing cyclonedx-bom..."
    pip install -q cyclonedx-bom
fi

# Generate JSON SBOM using CycloneDX
echo "Generating CycloneDX JSON SBOM..."
cyclonedx-py environment -o sbom.json --of JSON
echo "✅ JSON SBOM generated: sbom.json"
echo ""

# Convert to SPDX format
echo "Converting to SPDX format..."
python3 << 'PYTHON_SCRIPT'
import json
from datetime import datetime, timezone

# Read the JSON SBOM
with open('sbom.json', 'r') as f:
    sbom_data = json.load(f)

# Extract packages from CycloneDX format
packages = []
if 'components' in sbom_data:
    for comp in sbom_data['components']:
        packages.append({
            'Name': comp.get('name', 'unknown'),
            'Version': comp.get('version', 'unknown'),
            'License': comp.get('licenses', [{}])[0].get('license', {}).get('id', 'NOASSERTION') or 
                      comp.get('licenses', [{}])[0].get('license', {}).get('name', 'NOASSERTION') if comp.get('licenses') else 'NOASSERTION'
        })
elif 'packages' in sbom_data:
    for pkg in sbom_data['packages']:
        packages.append({
            'Name': pkg.get('name', 'unknown'),
            'Version': pkg.get('version', 'unknown'),
            'License': pkg.get('license', 'NOASSERTION')
        })

# Create SPDX document header
spdx_version = "2.3"
spdx_id = "SPDXRef-DOCUMENT"
namespace = "https://spdx.example.com/secondbrain"

doc = f"""SPDXVersion: SPDX-{spdx_version}
DataLicense: CC0-1.0
SPDXID: {spdx_id}
DocumentName: secondbrain
DocumentNamespace: {namespace}
Creator: Tool: cyclonedx-py
Created: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}

"""

# Add each package
for i, pkg in enumerate(packages):
    pkg_id = f"SPDXRef-Package-{i+1}"
    name = pkg['Name']
    version = pkg['Version']
    license = pkg['License']
    
    doc += f"""
PackageName: {name}
SPDXID: {pkg_id}
PackageVersion: {version}
PackageLicenseConcluded: {license}
PackageLicenseDeclared: {license}
DownloadLocation: NOASSERTION

"""

# Write SPDX file
with open('sbom.spdx', 'w') as f:
    f.write(doc)

print(f"✅ SPDX SBOM created with {len(packages)} packages")
print("📍 Output: sbom.spdx")
PYTHON_SCRIPT

echo ""
echo "=========================================="
echo "SBOM generation complete!"
echo "=========================================="
echo "  - JSON format: sbom.json"
echo "  - SPDX format: sbom.spdx"
