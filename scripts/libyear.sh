#!/bin/bash
# Libyear Dependency Freshness Report for SecondBrain
# Measures the libyear metric (release lag between the version in use and the
# latest release, in years, summed across dependencies - https://libyear.com)
# using pylibyear, for two views:
#   - pyproject.toml   : declared direct dependencies + optional extras (floors)
#   - requirements.txt : fully resolved/locked tree (pip-compile output)

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure we're in the project root
cd "$PROJECT_ROOT"

# JSON artifacts (project root, like sbom.json; see .gitignore)
PYPROJECT_REPORT="libyear.json"
LOCKED_REPORT="libyear-locked.json"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated.${NC}"
    echo "Activate the virtual environment before measuring dependency freshness."
    echo ""
fi

# Print a compact console summary from a libyear JSON report
print_summary() {
    local report="$1"

    if ! command -v jq &> /dev/null; then
        echo -e "${YELLOW}jq not installed - console summary skipped; report: $report${NC}"
        echo ""
        return 0
    fi

    echo -e "${GREEN}Total libyears behind:${NC} $(jq -r '.total_libyears_behind' "$report") across $(jq -r '.libraries | length' "$report") libraries"
    echo "Top stale dependencies:"
    jq -r '.libraries | sort_by(.libyears_behind | tonumber) | reverse | .[0:5][] as $lib | "  \($lib.library) \($lib.current_version) -> \($lib.latest_version) (\($lib.libyears_behind) libyears)"' "$report"
    echo ""
}

# Measure libyears for one dependency view
# Arguments: 1=label, 2=libyear subcommand (toml|text), 3=dependency file, 4=report file
run_libyear() {
    local label="$1"
    local subcommand="$2"
    local target="$3"
    local report="$4"

    echo -e "${GREEN}Measuring libyears: $label${NC}"
    echo ""

    if ! command -v libyear &> /dev/null; then
        echo -e "${YELLOW}libyear (pylibyear) not installed. Skipping...${NC}"
        echo "Install with: pip install -e \".[security]\""
        echo ""
        return 0
    fi

    if [ ! -f "$target" ]; then
        echo -e "${YELLOW}$target not found. Skipping...${NC}"
        echo ""
        return 0
    fi

    rm -f "$report"

    # --sort: largest libyears first; --json: machine-readable report;
    # EXTRA_ARGS (e.g. --fail-over N) pass through for threshold gating.
    libyear "$subcommand" "$target" --sort --json "$report" "${EXTRA_ARGS[@]}"
    echo ""
    echo -e "${GREEN}libyear report written: $report${NC}"
    echo ""
    print_summary "$report"
}

run_all() {
    run_libyear "declared dependencies (pyproject.toml)" toml pyproject.toml "$PYPROJECT_REPORT"
    run_libyear "locked dependency tree (requirements.txt)" text requirements.txt "$LOCKED_REPORT"

    echo "=========================================="
    echo -e "${GREEN}Libyear measurement complete!${NC}"
    echo "=========================================="
    echo "  - Declared report: $PYPROJECT_REPORT"
    echo "  - Locked report:   $LOCKED_REPORT"
    echo "  Smaller totals = fresher dependencies."
    echo "  Gate a threshold with: $0 all --fail-over 20"
}

# First argument selects the view; the rest pass through to libyear
MODE="${1:-all}"
EXTRA_ARGS=()
if [ "$#" -gt 0 ]; then
    shift
    EXTRA_ARGS=("$@")
fi

case "$MODE" in
    pyproject)
        run_libyear "declared dependencies (pyproject.toml)" toml pyproject.toml "$PYPROJECT_REPORT"
        ;;
    requirements)
        run_libyear "locked dependency tree (requirements.txt)" text requirements.txt "$LOCKED_REPORT"
        ;;
    all)
        run_all
        ;;
    help)
        echo "SecondBrain Libyear Dependency Freshness Script"
        echo ""
        echo "Usage: $0 [command] [libyear options]"
        echo ""
        echo "Commands:"
        echo "  pyproject    Measure declared dependencies (pyproject.toml)"
        echo "  requirements Measure the locked dependency tree (requirements.txt)"
        echo "  all          Measure both views (default)"
        echo "  help         Show this help message"
        echo ""
        echo "Options (passed through to libyear):"
        echo "  --fail-over N   Exit non-zero when total libyears exceed N (CI gate)"
        echo ""
        echo "Reports: libyear.json (declared), libyear-locked.json (locked)"
        ;;
    *)
        echo "Unknown command: $MODE"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
