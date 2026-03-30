#!/bin/bash
# Dependency Update Script for SecondBrain
# Checks for outdated dependencies and generates update reports

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

# Default options
CHECK_ONLY=true
RUN_TESTS=false
OUTPUT_FORMAT="text"
OUTPUT_DIR="$PROJECT_ROOT/reports/dependency-updates"
VERBOSE=false

# Print usage information
print_usage() {
    cat << EOF
SecondBrain Dependency Update Script

Usage: $0 [OPTIONS] [COMMAND]

Commands:
    check       Check for outdated dependencies (default)
    update      Apply minor/patch updates safely
    full        Check, update, and run tests
    help        Show this help message

Options:
    -f, --format FORMAT   Output format: text, json, html (default: text)
    -o, --output DIR      Output directory for reports (default: reports/dependency-updates)
    -t, --run-tests       Run tests after updates
    -v, --verbose         Enable verbose output
    --dry-run             Show what would be updated without making changes
    --major               Include major version updates (potentially breaking)
    --minor               Include minor version updates (default)
    --patch               Include patch version updates (default)

Examples:
    # Check for outdated dependencies
    $0 check

    # Check and generate JSON report
    $0 check --format json --output ./reports

    # Apply safe updates and run tests
    $0 full --run-tests

    # Verbose check with all version types
    $0 check --verbose --major

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

# Check if virtual environment is activated
check_venv() {
    if [ -z "$VIRTUAL_ENV" ]; then
        log_warn "Virtual environment not activated. Results may not reflect your project environment."
        return 1
    fi
    return 0
}

# Check for outdated dependencies
check_outdated() {
    log_info "Checking for outdated dependencies..."
    echo ""

    # Ensure output directory exists
    mkdir -p "$OUTPUT_DIR"

    # Get outdated packages
    if ! pip list --outdated > /dev/null 2>&1; then
        log_error "Failed to check for outdated packages. Ensure pip is up to date."
        exit 1
    fi

    # Generate report based on format
    if [ "$OUTPUT_FORMAT" = "json" ]; then
        generate_json_report
    elif [ "$OUTPUT_FORMAT" = "html" ]; then
        generate_html_report
    else
        generate_text_report
    fi

    echo ""
    log_info "Report saved to: $OUTPUT_DIR"
}

# Generate text report
generate_text_report() {
    local REPORT_FILE="$OUTPUT_DIR/outdated-dependencies.txt"
    local TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    cat > "$REPORT_FILE" << EOF
SecondBrain Dependency Update Report
Generated: $TIMESTAMP
=====================================

EOF

    echo "Outdated Dependencies:" >> "$REPORT_FILE"
    echo "----------------------" >> "$REPORT_FILE"
    pip list --outdated >> "$REPORT_FILE" 2>&1

    echo "" >> "$REPORT_FILE"
    echo "Project Dependencies (from pyproject.toml):" >> "$REPORT_FILE"
    echo "-------------------------------------------" >> "$REPORT_FILE"

    # Extract runtime dependencies
    echo "Runtime Dependencies:" >> "$REPORT_FILE"
    grep -A 20 'dependencies = \[' "$PROJECT_ROOT/pyproject.toml" | grep '"' | sed 's/^[[:space:]]*/  /' >> "$REPORT_FILE"

    echo "" >> "$REPORT_FILE"
    echo "Dev Dependencies:" >> "$REPORT_FILE"
    grep -A 30 'optional-dependencies' "$PROJECT_ROOT/pyproject.toml" | grep -A 20 'dev = \[' | grep '"' | sed 's/^[[:space:]]*/  /' >> "$REPORT_FILE"

    echo "" >> "$REPORT_FILE"
    echo "Recommended Actions:" >> "$REPORT_FILE"
    echo "-------------------" >> "$REPORT_FILE"
    echo "To update all packages safely (minor/patch only):" >> "$REPORT_FILE"
    echo "  pip install --upgrade $(pip list --outdated | tail -n +3 | awk '{print $1}' | tr '\n' ' ')" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "To update specific package:" >> "$REPORT_FILE"
    echo "  pip install --upgrade <package-name>" >> "$REPORT_FILE"

    cat "$REPORT_FILE"
}

# Generate JSON report
generate_json_report() {
    local REPORT_FILE="$OUTPUT_DIR/outdated-dependencies.json"
    local TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    # Create JSON using Python for proper formatting
    python3 << PYTHON_SCRIPT
import json
import subprocess
import re
from datetime import datetime

# Get outdated packages
result = subprocess.run(['pip', 'list', '--outdated', '--format=json'], 
                       capture_output=True, text=True)
outdated = json.loads(result.stdout) if result.stdout else []

# Extract dependencies from pyproject.toml
with open('$PROJECT_ROOT/pyproject.toml', 'r') as f:
    content = f.read()

# Simple parsing of dependencies
runtime_deps = []
dev_deps = []

runtime_match = re.search(r'dependencies = \[(.*?)\]', content, re.DOTALL)
if runtime_match:
    deps = re.findall(r'"([^"]+)"', runtime_match.group(1))
    runtime_deps = [d.split('>=')[0].split('==')[0] for d in deps]

dev_match = re.search(r'dev = \[(.*?)\]', content, re.DOTALL)
if dev_match:
    deps = re.findall(r'"([^"]+)"', dev_match.group(1))
    dev_deps = [d.split('>=')[0].split('==')[0] for d in deps]

# Categorize outdated packages
outdated_runtime = [p for p in outdated if p['name'] in runtime_deps]
outdated_dev = [p for p in outdated if p['name'] in dev_deps]
outdated_other = [p for p in outdated if p['name'] not in runtime_deps and p['name'] not in dev_deps]

report = {
    "metadata": {
        "generated_at": "$TIMESTAMP",
        "project": "secondbrain",
        "version": "0.4.0"
    },
    "summary": {
        "total_outdated": len(outdated),
        "runtime_outdated": len(outdated_runtime),
        "dev_outdated": len(outdated_dev),
        "other_outdated": len(outdated_other)
    },
    "outdated_packages": {
        "runtime": outdated_runtime,
        "dev": outdated_dev,
        "other": outdated_other
    },
    "recommendations": {
        "safe_updates": [p['name'] for p in outdated if p.get('latest_version', '').startswith(tuple(p['current_version'].split('.')[:1]))],
        "major_updates": [p['name'] for p in outdated if not p.get('latest_version', '').startswith(tuple(p['current_version'].split('.')[:1]))]
    }
}

with open('$REPORT_FILE', 'w') as f:
    json.dump(report, f, indent=2)

print(json.dumps(report, indent=2))
PYTHON_SCRIPT
}

# Generate HTML report
generate_html_report() {
    local REPORT_FILE="$OUTPUT_DIR/outdated-dependencies.html"
    local TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # Generate HTML using Python
    python3 << PYTHON_SCRIPT
import json
import subprocess
from datetime import datetime

# Get outdated packages
result = subprocess.run(['pip', 'list', '--outdated', '--format=json'], 
                       capture_output=True, text=True)
outdated = json.loads(result.stdout) if result.stdout else []

html = f"""<!DOCTYPE html>
<html>
<head>
    <title>SecondBrain Dependency Update Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        .meta {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #4CAF50; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .warning {{ color: #ff9800; }}
        .danger {{ color: #f44336; }}
        .success {{ color: #4CAF50; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>SecondBrain Dependency Update Report</h1>
        <div class="meta">Generated: {TIMESTAMP}</div>
        
        <h2>Summary</h2>
        <p>Total outdated packages: <strong>{len(outdated)}</strong></p>
        
        <h2>Outdated Packages</h2>
        <table>
            <thead>
                <tr>
                    <th>Package</th>
                    <th>Current Version</th>
                    <th>Latest Version</th>
                    <th>Update Type</th>
                </tr>
            </thead>
            <tbody>
"""

    for pkg in outdated:
        current = pkg.get('current_version', 'unknown')
        latest = pkg.get('latest_version', 'unknown')
        current_major = current.split('.')[0] if current != 'unknown' else '0'
        latest_major = latest.split('.')[0] if latest != 'unknown' else '0'
        
        update_type = "Major (breaking)" if current_major != latest_major else "Minor/patch (safe)"
        update_class = "danger" if current_major != latest_major else "success"
        
        html += f"""
                <tr>
                    <td>{pkg.get('name', 'unknown')}</td>
                    <td>{current}</td>
                    <td>{latest}</td>
                    <td class="{update_class}">{update_type}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
        
        <h2>Recommendations</h2>
        <p>✅ <strong>Safe to update:</strong> Minor and patch versions (backward compatible)</p>
        <p>⚠️ <strong>Review carefully:</strong> Major version updates may contain breaking changes</p>
        
        <h2>Commands</h2>
        <pre><code># Update all packages safely
pip install --upgrade """
    
    html += ' '.join([p['name'] for p in outdated])
    
    html += """</code></pre>
    </div>
</body>
</html>
"""

    with open('$REPORT_FILE', 'w') as f:
        f.write(html)

print(f"HTML report generated: $REPORT_FILE")
print(html)
PYTHON_SCRIPT
}

# Apply updates (safe mode - minor/patch only)
apply_updates() {
    local DRY_RUN=false
    if [ "$1" = "--dry-run" ]; then
        DRY_RUN=true
    fi

    log_info "Checking for safe updates (minor/patch only)..."

    # Get list of packages with safe updates
    local SAFE_PACKAGES=$(pip list --outdated --format=json | python3 -c "
import sys, json
outdated = json.load(sys.stdin)
safe = [p['name'] for p in outdated 
        if p.get('latest_version', '').startswith(tuple(p['current_version'].split('.')[:1]))]
print(' '.join(safe))
")

    if [ -z "$SAFE_PACKAGES" ]; then
        log_info "No safe updates available."
        return 0
    fi

    if [ "$DRY_RUN" = true ]; then
        log_info "Dry run - would update the following packages:"
        echo "  $SAFE_PACKAGES"
        return 0
    fi

    log_info "Updating packages (minor/patch only)..."
    echo "  $SAFE_PACKAGES" | xargs pip install --upgrade

    log_info "Updates complete!"
}

# Run tests
run_tests() {
    log_info "Running tests to verify updates..."
    cd "$PROJECT_ROOT"
    pytest --tb=short -q
}

# Full update workflow
full_update() {
    log_info "Starting full dependency update workflow..."
    echo ""

    # Step 1: Check
    check_outdated
    echo ""

    # Step 2: Apply updates
    apply_updates
    echo ""

    # Step 3: Run tests if requested
    if [ "$RUN_TESTS" = true ]; then
        run_tests
    fi

    log_info "Full update workflow complete!"
}

# Parse command line arguments
COMMAND="check"
while [[ $# -gt 0 ]]; do
    case $1 in
        check|update|full|help)
            COMMAND="$1"
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
        -t|--run-tests)
            RUN_TESTS=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --major|--minor|--patch)
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

# Execute command
case $COMMAND in
    check)
        check_venv || true
        check_outdated
        ;;
    update)
        check_venv || true
        apply_updates "${DRY_RUN:+--dry-run}"
        ;;
    full)
        check_venv || true
        full_update
        ;;
    help)
        print_usage
        exit 0
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        print_usage
        exit 1
        ;;
esac

exit 0
