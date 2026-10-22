#!/bin/bash
# Security Scan Script for SecondBrain
# Runs comprehensive security scanning on dependencies and code

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "SecondBrain Security Scan"
echo "=========================================="
echo ""

# Clean up old reports before generating new ones
echo "Cleaning up old security reports..."
if [ -x "$SCRIPT_DIR/cleanup_reports.sh" ]; then
    "$SCRIPT_DIR/cleanup_reports.sh"
    echo ""
else
    echo "Warning: cleanup_reports.sh not found or not executable. Skipping cleanup."
    echo ""
fi

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# PYSEC-2026-3740 (CVE-2026-81726; grype/GHSA id GHSA-8mgp-746c-j5xp): nltk is
# a dev-only transitive dep of safety; no fixed release exists (OSV re-opened
# 2026-10-14, fixed=None against nltk 3.10.3 — the latest release). Mirrors
# the documented ignore in pyproject.toml [tool.safety].
#
# CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v): diskcache unsafe pickle
# deserialization; no fixed release exists (5.6.3 is the latest release).
# Transitive of the optional llama-cpp-python extras, not imported by
# secondbrain code. Mirrors the documented ignore in pyproject.toml
# [tool.safety].
#
# Pillow 12.3.0 - 2026-10 advisory cluster (CVE-2026-112390..112406,
# 112891..112901; 24 advisories total): TIFF encode/decode memory-safety
# issues, APNG/PDF-parser DoS paths, etc. All are fixed in 13.0.0, and all
# are upstream-blocked: every docling-slim release caps pillow>=10,<13, so
# no resolvable environment can take the fix (uv lock and pip both fail).
# Pillow is transitive via docling (no PIL imports in secondbrain code);
# no TIFF-save path exists in the codebase and the image-open paths are
# bounded by the docker memory caps on ingestion workers (DoS-only, no
# RCE/data exposure from this codebase's usage). Mirrors the documented
# ignore in pyproject.toml [tool.safety]. Revisit when docling-slim lifts
# the pillow<13 cap; new 12.3.0 advisories will need adding here too.
PIP_AUDIT_IGNORE_ARGS=(
    --ignore-vuln PYSEC-2026-3740 --ignore-vuln CVE-2025-69872
    # pillow 12.3.0 2026-10 advisory cluster (fixed 13.0.0, upstream-blocked)
    --ignore-vuln CVE-2026-112390 --ignore-vuln CVE-2026-112391
    --ignore-vuln CVE-2026-112392 --ignore-vuln CVE-2026-112393
    --ignore-vuln CVE-2026-112395 --ignore-vuln CVE-2026-112396
    --ignore-vuln CVE-2026-112397 --ignore-vuln CVE-2026-112399
    --ignore-vuln CVE-2026-112400 --ignore-vuln CVE-2026-112401
    --ignore-vuln CVE-2026-112402 --ignore-vuln CVE-2026-112404
    --ignore-vuln CVE-2026-112405 --ignore-vuln CVE-2026-112406
    --ignore-vuln CVE-2026-112891 --ignore-vuln CVE-2026-112892
    --ignore-vuln CVE-2026-112893 --ignore-vuln CVE-2026-112894
    --ignore-vuln CVE-2026-112895 --ignore-vuln CVE-2026-112896
    --ignore-vuln CVE-2026-112897 --ignore-vuln CVE-2026-112899
    --ignore-vuln CVE-2026-112900 --ignore-vuln CVE-2026-112901
)

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated.${NC}"
    echo "Please activate your virtual environment before running security scans."
    echo ""
fi

# Function to run pip-audit
run_pip_audit() {
    echo -e "${GREEN}Running pip-audit dependency scan...${NC}"
    echo ""
    
    if command -v pip-audit &> /dev/null; then
        pip-audit --desc on "${PIP_AUDIT_IGNORE_ARGS[@]}"
        echo ""
        echo -e "${GREEN}pip-audit completed successfully${NC}"
    else
        echo -e "${YELLOW}pip-audit not installed. Skipping...${NC}"
    fi
    echo ""
}

# Function to run safety check
run_safety_check() {
    echo -e "${GREEN}Running safety vulnerability check...${NC}"
    echo ""
    
    if command -v safety &> /dev/null; then
        safety check --full-report
        echo ""
        echo -e "${GREEN}safety check completed${NC}"
    else
        echo -e "${YELLOW}safety not installed. Skipping...${NC}"
    fi
    echo ""
}

# Function to run bandit
run_bandit() {
    echo -e "${GREEN}Running bandit security linter...${NC}"
    echo ""
    
    if command -v bandit &> /dev/null; then
        bandit -r src/secondbrain -c pyproject.toml -ll
        echo ""
        echo -e "${GREEN}bandit completed${NC}"
    else
        echo -e "${YELLOW}bandit not installed. Skipping...${NC}"
    fi
    echo ""
}

# Function to generate SBOM
generate_sbom() {
    echo -e "${GREEN}Generating Software Bill of Materials (SBOM)...${NC}"
    echo ""
    
    if command -v cyclonedx-py &> /dev/null; then
        cyclonedx-py env -o sbom.json
        echo ""
        echo -e "${GREEN}SBOM generated: sbom.json${NC}"
        echo "SBOM format: SPDX JSON"
    else
        echo -e "${YELLOW}cyclonedx-py not installed. Skipping...${NC}"
    fi
    echo ""
}

# Function to scan SBOM for vulnerabilities
scan_sbom() {
    echo -e "${GREEN}Scanning SBOM for vulnerabilities...${NC}"
    echo ""
    
    if [ -f "sbom.json" ]; then
        if command -v pip-audit &> /dev/null; then
            pip-audit --requirement sbom.json "${PIP_AUDIT_IGNORE_ARGS[@]}"
            echo ""
            echo -e "${GREEN}SBOM scan completed${NC}"
        else
            echo -e "${YELLOW}pip-audit not available for SBOM scanning${NC}"
        fi
    else
        echo -e "${YELLOW}SBOM not found. Run generate_sbom first.${NC}"
    fi
    echo ""
}

# Function to check the dependency tree for conflicts
# pip check fails on broken installed requirements. pipdeptree's silence mode
# still prints the summary without failing on unrelated metadata cycles.
run_pipdeptree() {
    echo -e "${GREEN}Running pipdeptree dependency tree check...${NC}"
    echo ""

    if command -v pipdeptree &> /dev/null; then
        python -m pip check
        pipdeptree --summary -w silence
        echo ""
        echo -e "${GREEN}pipdeptree completed${NC}"
    else
        echo -e "${YELLOW}pipdeptree not installed. Skipping...${NC}"
    fi
    echo ""
}

# Function to run all checks
run_all() {
    echo -e "${GREEN}Running ALL security checks...${NC}"
    echo ""

    generate_sbom
    run_pip_audit
    run_safety_check
    run_bandit
    run_pipdeptree

    echo ""
    echo "=========================================="
    echo -e "${GREEN}All security scans completed!${NC}"
    echo "=========================================="
}

# Parse arguments
case "${1:-all}" in
    audit)
        run_pip_audit
        ;;
    safety)
        run_safety_check
        ;;
    bandit)
        run_bandit
        ;;
    pipdeptree)
        run_pipdeptree
        ;;
    sbom)
        generate_sbom
        ;;
    scan-sbom)
        scan_sbom
        ;;
    all)
        run_all
        ;;
    help)
        echo "SecondBrain Security Scan Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  audit     Run pip-audit dependency scan"
        echo "  safety    Run safety vulnerability check"
        echo "  bandit    Run bandit security linter"
        echo "  pipdeptree Check dependency tree for conflicts"
        echo "  sbom      Generate Software Bill of Materials"
        echo "  scan-sbom Scan SBOM for vulnerabilities"
        echo "  all       Run all security checks (default)"
        echo "  help      Show this help message"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
