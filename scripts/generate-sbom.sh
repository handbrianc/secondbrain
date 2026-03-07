#!/bin/bash
# SBOM generation script using pip-licenses

set -e

echo "📋 Generating Software Bill of Materials (SBOM)..."

# Ensure we're in the project root
cd "$(dirname "$0")/.."

# Install pip-licenses if not already installed
pip install -q pip-licenses

# Generate SPDX-format SBOM
python3 << 'PYTHON_SCRIPT'
import json
from datetime import datetime, timezone

# Read the JSON SBOM
with open('sbom.json', 'r') as f:
    packages = json.load(f)

# Create SPDX document
spdx_version = "2.3"
spdx_id = "SPDXRef-DOCUMENT"
namespace = "https://spdx.example.com/secondbrain"

doc = f"""SPDXVersion: SPDX-{spdx_version}
DataLicense: CC0-1.0
SPDXID: {spdx_id}
DocumentName: secondbrain
DocumentNamespace: {namespace}
Creator: Tool: pip-licenses
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
