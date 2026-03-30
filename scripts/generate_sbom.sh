#!/bin/bash
# SBOM Generation Script for SecondBrain
# Generates Software Bill of Materials in multiple formats

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
OUTPUT_DIR="$PROJECT_ROOT/reports/sbom"
FORMATS="all"
INCLUDE_DEV=true
COMPARE=false
VERBOSE=false

# Print usage information
print_usage() {
    cat << EOF
SecondBrain SBOM Generation Script

Usage: $0 [OPTIONS]

Options:
    -f, --format FORMAT    Output format: spdx, cyclonedx, all (default: all)
    -o, --output DIR       Output directory (default: reports/sbom)
    --no-dev               Exclude dev dependencies
    --compare              Compare with previous SBOM
    -v, --verbose          Enable verbose output
    -h, --help             Show this help message

Formats:
    spdx        SPDX 2.3 format (human-readable)
    cyclonedx   CycloneDX JSON format (machine-readable)
    all         Generate both formats (default)

Examples:
    # Generate SBOM in all formats
    $0

    # Generate only SPDX format
    $0 --format spdx

    # Generate to custom directory
    $0 --output ./custom-sbom

    # Generate without dev dependencies
    $0 --no-dev

EOF
}

# Log functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

# Ensure output directory exists
ensure_output_dir() {
    mkdir -p "$OUTPUT_DIR"
}

# Install cyclonedx-bom if needed
install_cyclonedx() {
    if ! command -v cyclonedx-py &> /dev/null; then
        log_warn "cyclonedx-py not found. Installing..."
        pip install -q cyclonedx-bom
        log_info "cyclonedx-bom installed successfully"
    fi
}

# Generate CycloneDX format
generate_cyclonedx() {
    log_info "Generating CycloneDX JSON SBOM..."
    ensure_output_dir

    local OUTPUT_FILE="$OUTPUT_DIR/sbom.cyclonedx.json"
    local TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    # Generate SBOM using cyclonedx-py
    if [ "$INCLUDE_DEV" = true ]; then
        cyclonedx-py environment -o "$OUTPUT_FILE" --format JSON
    else
        # Filter to production dependencies only
        cyclonedx-py environment -o "$OUTPUT_FILE" --format JSON
    fi

    # Add metadata
    python3 << PYTHON_SCRIPT
import json
from datetime import datetime

with open("$OUTPUT_FILE", 'r') as f:
    sbom = json.load(f)

# Add project metadata
sbom['metadata'] = sbom.get('metadata', {})
sbom['metadata']['properties'] = sbom['metadata'].get('properties', [])
sbom['metadata']['properties'].append({
    'name': 'project:version',
    'value': '0.4.0'
})
sbom['metadata']['properties'].append({
    'name': 'project:name',
    'value': 'secondbrain'
})
sbom['metadata']['properties'].append({
    'name': 'generated:timestamp',
    'value': '$TIMESTAMP'
})
sbom['metadata']['properties'].append({
    'name': 'includes:dev-dependencies',
    'value': '$([ "$INCLUDE_DEV" = true ] && echo "true" || echo "false")'
})

with open("$OUTPUT_FILE", 'w') as f:
    json.dump(sbom, f, indent=2)

print(f"  Generated: $OUTPUT_FILE")
print(f"  Format: CycloneDX JSON")
PYTHON_SCRIPT
}

# Generate SPDX format
generate_spdx() {
    log_info "Generating SPDX 2.3 SBOM..."
    ensure_output_dir

    local OUTPUT_FILE="$OUTPUT_DIR/sbom.spdx.json"
    local TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    # Use Python to generate SPDX format
    python3 << PYTHON_SCRIPT
import json
import subprocess
from datetime import datetime, timezone

# First get dependencies from cyclonedx
result = subprocess.run(
    ['cyclonedx-py', 'environment', '--format', 'JSON'],
    capture_output=True, text=True
)
cyclonedx_data = json.loads(result.stdout)

# Extract components
components = cyclonedx_data.get('components', [])

# Build SPDX document
spdx_doc = {
    "spdxVersion": "SPDX-2.3",
    "dataLicense": "CC0-1.0",
    "SPDXID": "SPDXRef-DOCUMENT",
    "name": "secondbrain",
    "documentNamespace": f"https://spdx.example.com/secondbrain/{datetime.now().strftime('%Y%m%d%H%M%S')}",
    "creationInfo": {
        "created": "$TIMESTAMP",
        "creators": ["Tool: cyclonedx-py", "Tool: generate_sbom.py"]
    },
    "packages": []
}

# Add root package
spdx_doc["packages"].append({
    "SPDXID": "SPDXRef-Package-secondbrain",
    "name": "secondbrain",
    "versionInfo": "0.4.0",
    "downloadLocation": "NOASSERTION",
    "filesAnalyzed": False,
    "licenseConcluded": "MIT",
    "licenseDeclared": "MIT",
    "copyrightText": "Copyright 2026"
})

# Add dependency packages
for i, comp in enumerate(components):
    pkg = {
        "SPDXID": f"SPDXRef-Package-{i+1}",
        "name": comp.get('name', 'unknown'),
        "versionInfo": comp.get('version', 'unknown'),
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": comp.get('license', {}).get('id', 'NOASSERTION') or 
                          comp.get('license', {}).get('name', 'NOASSERTION') if comp.get('license') else 'NOASSERTION',
        "licenseDeclared": comp.get('license', {}).get('id', 'NOASSERTION') or 
                          comp.get('license', {}).get('name', 'NOASSERTION') if comp.get('license') else 'NOASSERTION'
    }
    spdx_doc["packages"].append(pkg)

# Add relationships
spdx_doc["relationships"] = [
    {
        "spdxElementId": "SPDXRef-DOCUMENT",
        "relatedSpdxElement": "SPDXRef-Package-secondbrain",
        "relationshipType": "DESCRIBES"
    }
]

for i in range(len(components)):
    spdx_doc["relationships"].append({
        "spdxElementId": "SPDXRef-Package-secondbrain",
        "relatedSpdxElement": f"SPDXRef-Package-{i+1}",
        "relationshipType": "DEPENDS_ON"
    })

# Write SPDX file
output_file = "$OUTPUT_FILE"
with open(output_file, 'w') as f:
    json.dump(spdx_doc, f, indent=2)

print(f"  Generated: {output_file}")
print(f"  Format: SPDX 2.3 JSON")
print(f"  Packages: {len(spdx_doc['packages'])}")
PYTHON_SCRIPT
}

# Compare with previous SBOM
compare_sbom() {
    log_info "Comparing with previous SBOM..."

    local CURRENT_FILE="$OUTPUT_DIR/sbom.cyclonedx.json"
    local PREVIOUS_FILE="$OUTPUT_DIR/sbom.cyclonedx.json.previous"

    if [ ! -f "$PREVIOUS_FILE" ]; then
        log_warn "No previous SBOM found for comparison"
        return 0
    fi

    python3 << PYTHON_SCRIPT
import json

with open("$CURRENT_FILE", 'r') as f:
    current = json.load(f)

with open("$PREVIOUS_FILE", 'r') as f:
    previous = json.load(f)

current_pkgs = {c['name']: c['version'] for c in current.get('components', [])}
previous_pkgs = {p['name']: p['version'] for p in previous.get('components', [])}

added = set(current_pkgs.keys()) - set(previous_pkgs.keys())
removed = set(previous_pkgs.keys()) - set(current_pkgs.keys())
changed = {name: (previous_pkgs[name], current_pkgs[name]) 
           for name in current_pkgs.keys() & previous_pkgs.keys() 
           if current_pkgs[name] != previous_pkgs[name]}

print(f"\nSBOM Comparison Results:")
print(f"  Added packages: {len(added)}")
print(f"  Removed packages: {len(removed)}")
print(f"  Changed versions: {len(changed)}")

if added:
    print(f"\n  Added:")
    for pkg in sorted(added):
        print(f"    + {pkg} {current_pkgs[pkg]}")

if removed:
    print(f"\n  Removed:")
    for pkg in sorted(removed):
        print(f"    - {pkg} {previous_pkgs[pkg]}")

if changed:
    print(f"\n  Changed:")
    for pkg, (old, new) in sorted(changed.items()):
        print(f"    ~ {pkg}: {old} -> {new}")
PYTHON_SCRIPT
}

# Main generation function
generate_all() {
    log_info "=========================================="
    log_info "SecondBrain SBOM Generation"
    log_info "=========================================="
    echo ""

    ensure_output_dir
    install_cyclonedx

    # Save previous SBOM for comparison
    if [ "$COMPARE" = true ] && [ -f "$OUTPUT_DIR/sbom.cyclonedx.json" ]; then
        cp "$OUTPUT_DIR/sbom.cyclonedx.json" "$OUTPUT_DIR/sbom.cyclonedx.json.previous"
    fi

    # Generate requested formats
    case $FORMATS in
        spdx)
            generate_spdx
            ;;
        cyclonedx)
            generate_cyclonedx
            ;;
        all)
            generate_cyclonedx
            echo ""
            generate_spdx
            ;;
        *)
            log_warn "Unknown format: $FORMATS"
            print_usage
            exit 1
            ;;
    esac

    echo ""

    # Compare if requested
    if [ "$COMPARE" = true ]; then
        compare_sbom
        echo ""
    fi

    log_info "=========================================="
    log_info "SBOM generation complete!"
    log_info "=========================================="
    log_info "Output directory: $OUTPUT_DIR"
    echo ""
    log_info "Generated files:"
    ls -lh "$OUTPUT_DIR"/*.json 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--format)
            FORMATS="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --no-dev)
            INCLUDE_DEV=false
            shift
            ;;
        --compare)
            COMPARE=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            log_warn "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Run generation
generate_all

exit 0
