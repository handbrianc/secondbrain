#!/bin/bash
# Security Scan Script for SecondBrain
# Runs comprehensive security scanning on dependencies and code

set -e

echo "=========================================="
echo "SecondBrain Security Scan"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
        pip-audit --desc on --quiet
        echo ""
        echo -e "${GREEN}pip-audit completed successfully${NC}"
    else
        echo -e "${YELLOW}pip-audit not installed. Installing...${NC}"
        pip install pip-audit
        pip-audit --desc on --quiet
        echo ""
        echo -e "${GREEN}pip-audit completed successfully${NC}"
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
        cyclonedx-py -r -o sbom.json
        echo ""
        echo -e "${GREEN}SBOM generated: sbom.json${NC}"
        echo "SBOM format: SPDX JSON"
    else
        echo -e "${YELLOW}cyclonedx-py not installed. Installing...${NC}"
        pip install cyclonedx-bom
        cyclonedx-py -r -o sbom.json
        echo ""
        echo -e "${GREEN}SBOM generated: sbom.json${NC}"
    fi
    echo ""
}

# Function to scan SBOM for vulnerabilities
scan_sbom() {
    echo -e "${GREEN}Scanning SBOM for vulnerabilities...${NC}"
    echo ""
    
    if [ -f "sbom.json" ]; then
        if command -v pip-audit &> /dev/null; then
            pip-audit --requirement sbom.json
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

# Function to run all checks
run_all() {
    echo -e "${GREEN}Running ALL security checks...${NC}"
    echo ""
    
    generate_sbom
    run_pip_audit
    run_safety_check
    run_bandit
    
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
