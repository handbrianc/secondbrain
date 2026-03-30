#!/bin/bash
# Dependency Validation Script for Pre-commit Hooks
# Validates dependency files and checks for security issues

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Exit codes
EXIT_SUCCESS=0
EXIT_WARNING=1
EXIT_FAILURE=2

# Validation options
STRICT_MODE=false
VERBOSE=false
CHECK_OUTDATED=true
CHECK_SECURITY=true
VALIDATE_SYNTAX=true

# Print usage
print_usage() {
    cat << EOF
SecondBrain Dependency Validation Script

Usage: $0 [OPTIONS]

Options:
    --no-outdated       Skip outdated dependency check
    --no-security       Skip security check
    --no-syntax         Skip syntax validation
    --strict            Fail on warnings (strict mode)
    -v, --verbose       Enable verbose output
    -h, --help          Show this help message

Exit Codes:
    0   All checks passed
    1   Warnings found (or failure in strict mode)
    2   Critical errors found

Examples:
    # Run all validations
    $0

    # Run without security checks
    $0 --no-security

    # Strict mode (fail on warnings)
    $0 --strict

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

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_failure() {
    echo -e "${RED}✗${NC} $1"
}

# Validate pyproject.toml syntax
validate_syntax() {
    log_info "Validating pyproject.toml syntax..."

    local EXIT_CODE=0

    # Check if file exists
    if [ ! -f "$PROJECT_ROOT/pyproject.toml" ]; then
        log_error "pyproject.toml not found"
        return $EXIT_FAILURE
    fi

    # Validate TOML syntax using Python
    if ! python3 << PYTHON_SCRIPT
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Installing tomli for TOML parsing...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "tomli"], check=True)
        import tomli as tomllib

with open("$PROJECT_ROOT/pyproject.toml", "rb") as f:
    tomllib.load(f)

print("TOML syntax is valid")
sys.exit(0)
PYTHON_SCRIPT
    then
        log_error "Invalid TOML syntax in pyproject.toml"
        return $EXIT_FAILURE
    fi

    log_success "pyproject.toml syntax is valid"
    return $EXIT_CODE
}

# Check for outdated critical dependencies
check_outdated() {
    log_info "Checking for outdated dependencies..."

    local WARNING_COUNT=0

    # Get outdated packages
    local OUTDATED=$(pip list --outdated --format=freeze 2>/dev/null | head -20)

    if [ -z "$OUTDATED" ]; then
        log_success "No outdated dependencies found"
        return $EXIT_SUCCESS
    fi

    # Count critical outdated packages (runtime dependencies)
    local CRITICAL_OUTDATED=$(echo "$OUTDATED" | while read -r line; do
        PKG_NAME=$(echo "$line" | cut -d'=' -f1 | cut -d' ' -f1)
        # Check if it's in runtime dependencies
        if grep -q "\"$PKG_NAME" "$PROJECT_ROOT/pyproject.toml" 2>/dev/null; then
            echo "$PKG_NAME"
        fi
    done | wc -l)

    if [ "$CRITICAL_OUTDATED" -gt 0 ]; then
        log_warn "$CRITICAL_OUTDATED runtime dependencies are outdated"
        WARNING_COUNT=$((WARNING_COUNT + CRITICAL_OUTDATED))

        if [ "$VERBOSE" = true ]; then
            echo ""
            echo "Outdated runtime dependencies:"
            echo "$OUTDATED" | while read -r line; do
                PKG_NAME=$(echo "$line" | cut -d'=' -f1 | cut -d' ' -f1)
                if grep -q "\"$PKG_NAME" "$PROJECT_ROOT/pyproject.toml" 2>/dev/null; then
                    echo "  - $line"
                fi
            done
            echo ""
        fi
    else
        log_success "Runtime dependencies are up to date"
    fi

    if [ "$WARNING_COUNT" -gt 0 ] && [ "$STRICT_MODE" = true ]; then
        return $EXIT_FAILURE
    fi

    return $EXIT_SUCCESS
}

# Run security checks
check_security() {
    log_info "Running quick security checks..."

    local EXIT_CODE=0
    local VULN_COUNT=0

    # Quick pip-audit check (non-verbose)
    if command -v pip-audit &> /dev/null; then
        log_verbose "Running pip-audit..."

        if ! pip-audit --quiet 2>/dev/null; then
            log_warn "pip-audit found vulnerabilities"
            VULN_COUNT=$((VULN_COUNT + 1))
            EXIT_CODE=$EXIT_WARNING
        fi
    else
        log_verbose "pip-audit not installed, skipping"
    fi

    # Check for known insecure packages
    local INSECURE_PACKAGES=(
        "pyyaml<5.4"
        "requests<2.20.0"
        "urllib3<1.24.2"
    )

    for pkg_spec in "${INSECURE_PACKAGES[@]}"; do
        PKG_NAME=$(echo "$pkg_spec" | cut -d'<' -f1)
        MIN_VERSION=$(echo "$pkg_spec" | cut -d'<' -f2)

        if pip show "$PKG_NAME" &>/dev/null; then
            CURRENT_VERSION=$(pip show "$PKG_NAME" | grep Version | cut -d' ' -f2)

            if [[ "$(printf '%s\n' "$MIN_VERSION" "$CURRENT_VERSION" | sort -V | head -n1)" == "$CURRENT_VERSION" ]] && [[ "$CURRENT_VERSION" != "$MIN_VERSION" ]]; then
                log_warn "$PKG_NAME $CURRENT_VERSION may have security vulnerabilities (upgrade to >= $MIN_VERSION)"
                VULN_COUNT=$((VULN_COUNT + 1))
                EXIT_CODE=$EXIT_WARNING
            fi
        fi
    done

    if [ "$VULN_COUNT" -eq 0 ]; then
        log_success "No known security vulnerabilities detected"
    else
        log_warn "Found $VULN_COUNT potential security issues"
    fi

    if [ "$STRICT_MODE" = true ] && [ "$EXIT_CODE" -eq $EXIT_WARNING ]; then
        return $EXIT_FAILURE
    fi

    return $EXIT_CODE
}

# Validate dependency tree
validate_tree() {
    log_info "Validating dependency tree..."

    local EXIT_CODE=0

    # Check for dependency conflicts
    if command -v pip-check &> /dev/null; then
        if ! pip-check 2>/dev/null | grep -q "none"; then
            log_warn "Dependency conflicts detected"
            EXIT_CODE=$EXIT_WARNING
        else
            log_success "No dependency conflicts detected"
        fi
    else
        log_verbose "pip-check not available, skipping dependency tree validation"
    fi

    return $EXIT_CODE
}

# Main validation function
run_validation() {
    local EXIT_CODE=0
    local STEP_EXIT_CODE=0

    echo ""
    echo "=========================================="
    echo "SecondBrain Dependency Validation"
    echo "=========================================="
    echo ""

    # Syntax validation
    if [ "$VALIDATE_SYNTAX" = true ]; then
        validate_syntax || STEP_EXIT_CODE=$?
        if [ $STEP_EXIT_CODE -ne $EXIT_SUCCESS ]; then
            EXIT_CODE=$STEP_EXIT_CODE
        fi
        echo ""
    fi

    # Outdated check
    if [ "$CHECK_OUTDATED" = true ]; then
        check_outdated || STEP_EXIT_CODE=$?
        if [ $STEP_EXIT_CODE -gt $EXIT_CODE ]; then
            EXIT_CODE=$STEP_EXIT_CODE
        fi
        echo ""
    fi

    # Security check
    if [ "$CHECK_SECURITY" = true ]; then
        check_security || STEP_EXIT_CODE=$?
        if [ $STEP_EXIT_CODE -gt $EXIT_CODE ]; then
            EXIT_CODE=$STEP_EXIT_CODE
        fi
        echo ""
    fi

    # Dependency tree validation
    validate_tree || STEP_EXIT_CODE=$?
    if [ $STEP_EXIT_CODE -gt $EXIT_CODE ]; then
        EXIT_CODE=$STEP_EXIT_CODE
    fi

    echo ""
    echo "=========================================="

    case $EXIT_CODE in
        0)
            echo -e "${GREEN}All dependency checks passed!${NC}"
            ;;
        1)
            echo -e "${YELLOW}Dependency checks completed with warnings${NC}"
            ;;
        *)
            echo -e "${RED}Dependency checks failed${NC}"
            ;;
    esac

    echo "=========================================="
    echo ""

    return $EXIT_CODE
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-outdated)
            CHECK_OUTDATED=false
            shift
            ;;
        --no-security)
            CHECK_SECURITY=false
            shift
            ;;
        --no-syntax)
            VALIDATE_SYNTAX=false
            shift
            ;;
        --strict)
            STRICT_MODE=true
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
            log_error "Unknown option: $1"
            print_usage
            exit 2
            ;;
    esac
done

# Run validation
run_validation
exit $?
