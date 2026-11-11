#!/bin/bash
# Security Scan Script for SecondBrain
# Runs comprehensive security scanning on dependencies and code

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Absolute artifact paths so the script works from any working directory.
SBOM_PATH="$PROJECT_ROOT/sbom.json"
SBOM_BASELINE_PATH="$PROJECT_ROOT/sbom.baseline.json"

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
# (Pillow 12.3.0 advisory ignores removed 2026-11: docling-slim 2.148.0
# and docling-ibm-models 4.0.4 dropped their pillow<13 pins, the lock
# resolves pillow 13.0.0, and the whole 2026-10 cluster was fixed in
# 13.0.0. Mirrors the removal in pyproject.toml [tool.safety].)
#
# filelock CVE-2026-112940/112913/112907: fixed in 4.2.1, but safety 3.8.1
# requires filelock>=3.16.1,<4.0, so upgrading makes the dev environment
# unresolvable. These affect SQLite-backed ReadWriteLock/AsyncReadWriteLock
# and Windows soft locks; Safety uses standard FileLock, and SecondBrain
# does not import filelock. The security job runs on Linux. Mirrors the
# documented ignore in pyproject.toml [tool.safety]; revisit when Safety
# permits filelock>=4.2.1.
#
# 2026-10-31 pip-audit advisory cluster on the same filelock 3.32.x (the
# audit DB caught up to the October Anthropic-OSS-Scanner reports): same
# acceptance. Nine fixed in 4.2.1; CVE-2026-112936 fixed in 4.0.9 - still
# >=4.0, still unresolvable under safety's filelock<4.0 floor. Other
# filelock advisories remain blocking.
PIP_AUDIT_IGNORE_ARGS=(
    --ignore-vuln PYSEC-2026-3740 --ignore-vuln CVE-2025-69872
    --ignore-vuln CVE-2026-112940 --ignore-vuln CVE-2026-112913
    --ignore-vuln CVE-2026-112907
    # filelock 2026-10-31 advisory cluster (fixed 4.2.1 / 4.0.9, safety-blocked)
    --ignore-vuln CVE-2026-112908 --ignore-vuln CVE-2026-112909
    --ignore-vuln CVE-2026-112910 --ignore-vuln CVE-2026-112911
    --ignore-vuln CVE-2026-112912 --ignore-vuln CVE-2026-112915
    --ignore-vuln CVE-2026-112935 --ignore-vuln CVE-2026-112936
    --ignore-vuln CVE-2026-112938 --ignore-vuln CVE-2026-112939
    # (pillow 12.3.0 2026-10 + 2026-10-31 cluster ignores removed 2026-11:
    # docling-slim 2.148.0 lifted the pillow<13 cap, lock resolves 13.0.0,
    # all of them fixed in 13.0.0 — see pyproject.toml [tool.safety].)
    # authlib 1.7.x (CI pin): fixed 1.9.0/1.9.1, incompatible with
    # Safety 3.8.1's httpx2 transport; dev-only transitive, no src imports
    --ignore-vuln CVE-2026-116672 --ignore-vuln CVE-2026-96760
    --ignore-vuln PYSEC-2026-4355 --ignore-vuln PYSEC-2026-4356
    --ignore-vuln PYSEC-2026-4357 --ignore-vuln PYSEC-2026-4358
    --ignore-vuln PYSEC-2026-4359 --ignore-vuln PYSEC-2026-4360
    --ignore-vuln PYSEC-2026-4354
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
        cyclonedx-py env -o "$SBOM_PATH"
        echo ""
        echo -e "${GREEN}SBOM generated: $SBOM_PATH${NC}"
        echo "SBOM format: CycloneDX JSON"
        compare_sbom
    else
        echo -e "${YELLOW}cyclonedx-py not installed. Skipping...${NC}"
    fi
    echo ""
}

# Function to compare the generated SBOM against the committed baseline
# (dependency-security spec: "SBOM SHALL be compared for unexpected changes").
# scripts/sbom_compare.py exits non-zero on added/removed components; with
# set -e that fails the scan. Without a committed baseline it prints a notice
# and exits 0 so CI stays green until sbom.baseline.json is committed.
compare_sbom() {
    echo -e "${GREEN}Comparing SBOM against baseline...${NC}"
    echo ""

    if [ ! -f "$SBOM_PATH" ]; then
        echo -e "${YELLOW}SBOM not found at $SBOM_PATH. Run the sbom command first.${NC}"
        return 0
    fi

    if [ -f "$SBOM_BASELINE_PATH" ]; then
        python3 "$SCRIPT_DIR/sbom_compare.py" --sbom "$SBOM_PATH" --baseline "$SBOM_BASELINE_PATH"
    else
        echo -e "${YELLOW}Notice: no SBOM baseline committed yet ($SBOM_BASELINE_PATH).${NC}"
        echo "Comparison is skipped (exit 0) until the baseline is committed."
        echo "Record one after reviewing the current SBOM with:"
        echo "  python3 $SCRIPT_DIR/sbom_compare.py --update-baseline"
    fi
    echo ""
}

# Function to scan SBOM for vulnerabilities
scan_sbom() {
    echo -e "${GREEN}Scanning SBOM for vulnerabilities...${NC}"
    echo ""
    
    if [ -f "$SBOM_PATH" ]; then
        if command -v pip-audit &> /dev/null; then
            pip-audit --requirement "$SBOM_PATH" "${PIP_AUDIT_IGNORE_ARGS[@]}"
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

# Function to check the dependency tree for conflicts.
# pipdeptree's fail warning mode (-w fail) exits non-zero when dependency
# problems (mismatched requirements, cycles) are found, per the
# dependency-security spec note ("pipdeptree --summary -w fail"). pip check is
# kept as an additional conflict check on installed requirements.
run_pipdeptree() {
    echo -e "${GREEN}Running pipdeptree dependency tree check...${NC}"
    echo ""

    if command -v pipdeptree &> /dev/null; then
        python -m pip check
        # -w fail is the documented contract (archived dependency-security
        # spec note, 2026-10-11). Tolerated exception: safetensors' wheel
        # metadata declares itself as a dependency (safetensors =>
        # safetensors), a benign upstream packaging bug pipdeptree reports
        # as a cycle (--exclude removes it from the tree summary but the
        # warning still trips -w fail's exit code). The stage fails on any
        # other dependency problem; pip check above still catches real
        # requirement conflicts on installed metadata.
        PDEPT_OUT="$(pipdeptree --summary -w fail 2>&1)" && pdept_rc=0 || pdept_rc=$?
        if [ "$pdept_rc" -ne 0 ]; then
            if [ "$(printf '%s\n' "$PDEPT_OUT" | grep -c '=>')" = "1" ] \
                && printf '%s\n' "$PDEPT_OUT" | grep -q 'safetensors => safetensors' \
                && printf '%s\n' "$PDEPT_OUT" | grep -qE 'conflicting dependencies:[[:space:]]+0' \
                && printf '%s\n' "$PDEPT_OUT" | grep -qE 'missing dependencies:[[:space:]]+0'; then
                echo "pipdeptree: only the known-benign safetensors self-reference cycle found; tolerated."
                printf '%s\n' "$PDEPT_OUT"
            else
                printf '%s\n' "$PDEPT_OUT"
                exit 1
            fi
        else
            printf '%s\n' "$PDEPT_OUT"
        fi
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
        echo "  pipdeptree Check dependency tree for conflicts (fails on dependency problems)"
        echo "  sbom      Generate SBOM (CycloneDX JSON) and compare against baseline"
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
