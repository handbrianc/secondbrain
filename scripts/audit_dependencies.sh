#!/bin/bash
# Security Audit Script for SecondBrain Dependencies
# Runs comprehensive security scanning using multiple tools

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default options
SCAN_ALL=true
FAIL_ON_CRITICAL=true
FAIL_ON_HIGH=false
OUTPUT_FORMAT="text"
OUTPUT_DIR="$PROJECT_ROOT/reports/security-audit"
VERBOSE=false
SKIP_SBOM=false

# Print usage information
print_usage() {
    cat << EOF
SecondBrain Dependency Security Audit Script

Usage: $0 [OPTIONS] [TOOL]

Tools:
    all         Run all security tools (default)
    pip-audit   Run pip-audit dependency scan
    safety      Run safety vulnerability check
    bandit      Run bandit static analysis
    audit       Alias for pip-audit

Options:
    -f, --format FORMAT    Output format: text, json, html (default: text)
    -o, --output DIR       Output directory for reports (default: reports/security-audit)
    --fail-on-high         Fail on high severity vulnerabilities
    --no-fail              Never fail on vulnerabilities (report only)
    --skip-sbom            Skip SBOM generation
    -v, --verbose          Enable verbose output
    --generate-sbom-only   Only generate SBOM, skip scanning
    --scan-sbom-only       Only scan existing SBOM

Examples:
    # Run all security audits
    $0

    # Run only pip-audit
    $0 pip-audit

    # Generate SBOM and scan it
    $0 --generate-sbom-only && $0 --scan-sbom-only

    # JSON output with strict failure mode
    $0 --format json --fail-on-high

EOF
}

# Log functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

log_tool() {
    echo -e "${CYAN}[TOOL]${NC} $1"
}

# Check if virtual environment is activated
check_venv() {
    if [ -z "$VIRTUAL_ENV" ]; then
        log_warn "Virtual environment not activated. Scanning system Python packages."
        return 1
    fi
    return 0
}

# Ensure output directory exists
ensure_output_dir() {
    mkdir -p "$OUTPUT_DIR"
}

# Install tool if not available
install_tool() {
    local TOOL="$1"
    local PACKAGE="$2"

    if ! command -v "$TOOL" &> /dev/null; then
        log_warn "$TOOL not found. Installing $PACKAGE..."
        pip install -q "$PACKAGE"
        log_info "$TOOL installed successfully"
    fi
}

# Generate SBOM
generate_sbom() {
    log_info "Generating Software Bill of Materials (SBOM)..."
    ensure_output_dir

    install_tool "cyclonedx-py" "cyclonedx-bom"

    local SBOM_FILE="$OUTPUT_DIR/sbom.json"
    cyclonedx-py environment -o "$SBOM_FILE"

    log_info "SBOM generated: $SBOM_FILE"
}

# Run pip-audit
run_pip_audit() {
    log_tool "Running pip-audit..."
    ensure_output_dir

    install_tool "pip-audit" "pip-audit"

    local REPORT_FILE="$OUTPUT_DIR/pip-audit-report.txt"
    local JSON_REPORT="$OUTPUT_DIR/pip-audit-report.json"
    local VULN_COUNT=0

    if [ "$OUTPUT_FORMAT" = "json" ]; then
        log_info "Generating JSON report..."
        pip-audit --format json > "$JSON_REPORT" 2>&1 || true
        
        # Count vulnerabilities
        VULN_COUNT=$(python3 -c "
import json
try:
    with open('$JSON_REPORT', 'r') as f:
        data = json.load(f)
    print(len([v for v in data if isinstance(v, dict)]))
except:
    print(0)
")
    else
        log_info "Generating text report..."
        pip-audit --desc on > "$REPORT_FILE" 2>&1 || true
        
        # Count vulnerabilities
        VULN_COUNT=$(grep -c "Known vulnerable" "$REPORT_FILE" 2>/dev/null || echo "0")
    fi

    echo ""
    if [ "$VULN_COUNT" -gt 0 ]; then
        log_error "Found $VULN_COUNT vulnerabilities"
        return 1
    else
        log_info "No vulnerabilities found"
        return 0
    fi
}

# Run safety check
run_safety_check() {
    log_tool "Running safety vulnerability check..."
    ensure_output_dir

    install_tool "safety" "safety"

    local REPORT_FILE="$OUTPUT_DIR/safety-report.txt"
    local JSON_REPORT="$OUTPUT_DIR/safety-report.json"
    local VULN_COUNT=0

    if [ "$OUTPUT_FORMAT" = "json" ]; then
        log_info "Generating JSON report..."
        safety check --output json --output-file "$JSON_REPORT" 2>&1 || true
        
        # Count vulnerabilities
        VULN_COUNT=$(python3 -c "
import json
try:
    with open('$JSON_REPORT', 'r') as f:
        data = json.load(f)
    if isinstance(data, list):
        print(len(data))
    elif isinstance(data, dict) and 'vulnerabilities' in data:
        print(len(data['vulnerabilities']))
    else:
        print(0)
except:
    print(0)
")
    else
        log_info "Generating text report with full details..."
        safety check --full-report > "$REPORT_FILE" 2>&1 || true
        
        # Count vulnerabilities
        VULN_COUNT=$(grep -c "vulnerable" "$REPORT_FILE" 2>/dev/null || echo "0")
    fi

    echo ""
    if [ "$VULN_COUNT" -gt 0 ]; then
        log_error "Found $VULN_COUNT vulnerable packages"
        return 1
    else
        log_info "No vulnerable packages found"
        return 0
    fi
}

# Run bandit
run_bandit() {
    log_tool "Running bandit static analysis..."
    ensure_output_dir

    install_tool "bandit" "bandit"

    local REPORT_FILE="$OUTPUT_DIR/bandit-report.txt"
    local JSON_REPORT="$OUTPUT_DIR/bandit-report.json"
    local ISSUE_COUNT=0

    if [ "$OUTPUT_FORMAT" = "json" ]; then
        log_info "Generating JSON report..."
        bandit -r src/secondbrain -c pyproject.toml -f json -o "$JSON_REPORT" 2>&1 || true
        
        # Count issues
        ISSUE_COUNT=$(python3 -c "
import json
try:
    with open('$JSON_REPORT', 'r') as f:
        data = json.load(f)
    print(len(data.get('results', [])))
except:
    print(0)
")
    else
        log_info "Generating text report..."
        bandit -r src/secondbrain -c pyproject.toml -ll > "$REPORT_FILE" 2>&1 || true
        
        # Count issues
        ISSUE_COUNT=$(grep -c "Issue:" "$REPORT_FILE" 2>/dev/null || echo "0")
    fi

    echo ""
    if [ "$ISSUE_COUNT" -gt 0 ]; then
        log_warn "Found $ISSUE_COUNT security issues"
        return 1
    else
        log_info "No security issues found"
        return 0
    fi
}

# Scan SBOM for vulnerabilities
scan_sbom() {
    log_tool "Scanning SBOM for vulnerabilities..."
    ensure_output_dir

    local SBOM_FILE="$OUTPUT_DIR/sbom.json"

    if [ ! -f "$SBOM_FILE" ]; then
        log_error "SBOM not found. Generate SBOM first with --generate-sbom-only"
        return 1
    fi

    install_tool "pip-audit" "pip-audit"

    local REPORT_FILE="$OUTPUT_DIR/sbom-scan-report.txt"

    pip-audit --requirement "$SBOM_FILE" > "$REPORT_FILE" 2>&1 || true

    local VULN_COUNT=$(grep -c "Known vulnerable" "$REPORT_FILE" 2>/dev/null || echo "0")

    echo ""
    if [ "$VULN_COUNT" -gt 0 ]; then
        log_error "Found $VULN_COUNT vulnerabilities in SBOM"
        return 1
    else
        log_info "No vulnerabilities found in SBOM"
        return 0
    fi
}

# Generate summary report
generate_summary() {
    local TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    local SUMMARY_FILE="$OUTPUT_DIR/summary.json"

    ensure_output_dir

    python3 << PYTHON_SCRIPT
import json
import os
from datetime import datetime

output_dir = "$OUTPUT_DIR"
results = {
    "metadata": {
        "generated_at": "$TIMESTAMP",
        "project": "secondbrain",
        "version": "0.4.0"
    },
    "tools_run": [],
    "vulnerabilities": {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0
    },
    "status": "pass"
}

# Check pip-audit results
pip_audit_file = os.path.join(output_dir, "pip-audit-report.json")
if os.path.exists(pip_audit_file):
    try:
        with open(pip_audit_file, 'r') as f:
            data = json.load(f)
            results["tools_run"].append("pip-audit")
            results["vulnerabilities"]["total"] = len([v for v in data if isinstance(v, dict)])
    except:
        pass

# Check safety results
safety_file = os.path.join(output_dir, "safety-report.json")
if os.path.exists(safety_file):
    try:
        with open(safety_file, 'r') as f:
            data = json.load(f)
            results["tools_run"].append("safety")
            if isinstance(data, list):
                results["vulnerabilities"]["total"] = results["vulnerabilities"].get("total", 0) + len(data)
    except:
        pass

# Check bandit results
bandit_file = os.path.join(output_dir, "bandit-report.json")
if os.path.exists(bandit_file):
    try:
        with open(bandit_file, 'r') as f:
            data = json.load(f)
            results["tools_run"].append("bandit")
            issues = data.get("results", [])
            results["vulnerabilities"]["bandit_issues"] = len(issues)
    except:
        pass

# Determine overall status
if results["vulnerabilities"].get("total", 0) > 0:
    results["status"] = "fail"

with open("$SUMMARY_FILE", 'w') as f:
    json.dump(results, f, indent=2)

print(json.dumps(results, indent=2))
PYTHON_SCRIPT
}

# Run all tools
run_all() {
    local EXIT_CODE=0
    local VULN_COUNT=0

    ensure_output_dir

    echo ""
    echo "=========================================="
    echo "SecondBrain Security Audit"
    echo "=========================================="
    echo ""

    # Generate SBOM first
    if [ "$SKIP_SBOM" = false ]; then
        generate_sbom
        echo ""
    fi

    # Run pip-audit
    log_info "=== pip-audit ==="
    if ! run_pip_audit; then
        EXIT_CODE=1
    fi
    echo ""

    # Run safety
    log_info "=== Safety ==="
    if ! run_safety_check; then
        EXIT_CODE=1
    fi
    echo ""

    # Run bandit
    log_info "=== Bandit ==="
    if ! run_bandit; then
        EXIT_CODE=1
    fi
    echo ""

    # Generate summary
    log_info "=== Summary ==="
    generate_summary
    echo ""

    # Final status
    echo "=========================================="
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}All security audits passed!${NC}"
    else
        echo -e "${RED}Security audits found issues${NC}"
    fi
    echo "=========================================="
    echo ""
    log_info "Reports saved to: $OUTPUT_DIR"

    return $EXIT_CODE
}

# Parse command line arguments
TOOL="all"
while [[ $# -gt 0 ]]; do
    case $1 in
        all|pip-audit|safety|bandit|audit)
            TOOL="$1"
            if [ "$TOOL" = "audit" ]; then
                TOOL="pip-audit"
            fi
            shift
            ;;
        -f|--format)
            OUTPUT_FORMAT="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --fail-on-high)
            FAIL_ON_HIGH=true
            shift
            ;;
        --no-fail)
            FAIL_ON_CRITICAL=false
            FAIL_ON_HIGH=false
            shift
            ;;
        --skip-sbom)
            SKIP_SBOM=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --generate-sbom-only)
            TOOL="sbom-only"
            shift
            ;;
        --scan-sbom-only)
            TOOL="scan-sbom-only"
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Execute tool
case $TOOL in
    all)
        check_venv || true
        run_all
        ;;
    pip-audit|audit)
        check_venv || true
        run_pip_audit
        ;;
    safety)
        check_venv || true
        run_safety_check
        ;;
    bandit)
        check_venv || true
        run_bandit
        ;;
    sbom-only)
        check_venv || true
        generate_sbom
        ;;
    scan-sbom-only)
        check_venv || true
        scan_sbom
        ;;
    help)
        print_usage
        exit 0
        ;;
    *)
        log_error "Unknown tool: $TOOL"
        print_usage
        exit 1
        ;;
esac

exit 0
