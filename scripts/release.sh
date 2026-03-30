#!/bin/bash
# SecondBrain Release Script
# Automates versioning, changelog generation, and release creation

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
VERSION_FILE="src/secondbrain/__init__.py"
CHANGELOG_FILE="CHANGELOG.md"
PYPROJECT_FILE="pyproject.toml"

# Functions
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

show_help() {
    cat << EOF
SecondBrain Release Script

Usage: ./scripts/release.sh [command] [options]

Commands:
  bump <type>     Bump version (type: major, minor, patch)
  changelog       Generate changelog from git history
  release         Full release workflow
  current         Show current version
  help            Show this help

Examples:
  ./scripts/release.sh bump patch
  ./scripts/release.sh changelog
  ./scripts/release.sh release

EOF
}

# Get current version
get_current_version() {
    grep "^__version__" $VERSION_FILE | cut -d'"' -f2
}

# Bump version
bump_version() {
    local bump_type=$1
    local current=$(get_current_version)
    
    print_status "Current version: $current"
    
    # Parse version components
    IFS='.' read -r major minor patch <<< "$current"
    
    case $bump_type in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            print_error "Invalid bump type: $bump_type"
            echo "Use: major, minor, or patch"
            exit 1
            ;;
    esac
    
    local new_version="${major}.${minor}.${patch}"
    print_status "Bumping to version: $new_version"
    
    # Update version in __init__.py
    sed -i.bak "s/__version__ = \".*\"/__version__ = \"$new_version\"/" $VERSION_FILE
    rm -f "${VERSION_FILE}.bak"
    
    # Update version in pyproject.toml
    sed -i.bak "s/^version = \".*\"/version = \"$new_version\"/" $PYPROJECT_FILE
    rm -f "${PYPROJECT_FILE}.bak"
    
    print_success "Version updated to $new_version"
    
    # Commit changes
    git add $VERSION_FILE $PYPROJECT_FILE
    git commit -m "chore: bump version to $new_version"
    
    # Create tag
    git tag "v$new_version"
    
    print_success "Created tag: v$new_version"
    
    echo "$new_version"
}

# Generate changelog
generate_changelog() {
    print_status "Generating changelog..."
    
    local version=$1
    if [ -z "$version" ]; then
        version=$(get_current_version)
    fi
    
    # Create changelog header
    cat > /tmp/changelog_header.md << EOF
# Changelog

All notable changes to SecondBrain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

EOF
    
    # Get commits since last tag
    local last_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    
    if [ -n "$last_tag" ]; then
        print_status "Getting commits since $last_tag"
        commits=$(git log "$last_tag"..HEAD --oneline --no-merges)
    else
        print_status "Getting all commits (no previous tags)"
        commits=$(git log --oneline --no-merges)
    fi
    
    # Categorize commits
    local features=""
    local fixes=""
    local docs=""
    local refactor=""
    local chore=""
    
    while IFS= read -r line; do
        if [[ $line =~ ^[a-f0-9]+\ feat:\ (.*) ]]; then
            features="${features}- ${BASH_REMATCH[1]}\n"
        elif [[ $line =~ ^[a-f0-9]+\ fix:\ (.*) ]]; then
            fixes="${fixes}- ${BASH_REMATCH[1]}\n"
        elif [[ $line =~ ^[a-f0-9]+\ docs:\ (.*) ]]; then
            docs="${docs}- ${BASH_REMATCH[1]}\n"
        elif [[ $line =~ ^[a-f0-9]+\ refactor:\ (.*) ]]; then
            refactor="${refactor}- ${BASH_REMATCH[1]}\n"
        elif [[ $line =~ ^[a-f0-9]+\ (chore|test|ci):\ (.*) ]]; then
            chore="${chore}- ${BASH_REMATCH[2]}\n"
        fi
    done <<< "$commits"
    
    # Build changelog entry
    local date=$(date +%Y-%m-%d)
    local changelog_entry="## [${version}] - ${date}

### Added
${features:-- No new features}

### Fixed
${fixes:-- No bug fixes}

### Documentation
${docs:-- No documentation changes}

### Refactored
${refactor:-- No refactoring}

### Chores
${chore:-- No chores}

"
    
    # Prepend to changelog
    cat /tmp/changelog_header.md > $CHANGELOG_FILE
    echo "$changelog_entry" >> $CHANGELOG_FILE
    
    # Append existing changelog (if any)
    if [ -f $CHANGELOG_FILE ]; then
        tail -n +4 $CHANGELOG_FILE.bak >> $CHANGELOG_FILE 2>/dev/null || true
    fi
    
    print_success "Changelog generated for version $version"
}

# Full release workflow
do_release() {
    local bump_type=$1
    
    echo
    echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          SecondBrain Release Workflow                  ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
    echo
    
    # Check for uncommitted changes
    if ! git diff --quiet; then
        print_warning "You have uncommitted changes"
        read -p "Commit or stash them first? (press Enter to continue, Ctrl+C to cancel) "
    fi
    
    # Ensure we're on main branch
    local current_branch=$(git branch --show-current)
    if [ "$current_branch" != "main" ] && [ "$current_branch" != "master" ]; then
        print_error "Must be on main/master branch to release"
        exit 1
    fi
    
    # Pull latest changes
    print_status "Pulling latest changes..."
    git pull origin $current_branch
    
    # Bump version
    print_status "Bumping version..."
    local new_version=$(bump_version $bump_type)
    
    # Generate changelog
    print_status "Generating changelog..."
    generate_changelog $new_version
    git add $CHANGELOG_FILE
    git commit -m "docs: update changelog for v$new_version"
    
    # Run tests
    print_status "Running tests..."
    pytest -x -q || {
        print_error "Tests failed. Aborting release."
        exit 1
    }
    print_success "All tests passed"
    
    # Run linting
    print_status "Running linting..."
    ruff check . || {
        print_error "Linting failed. Aborting release."
        exit 1
    }
    print_success "Linting passed"
    
    # Push changes
    print_status "Pushing changes..."
    git push origin $current_branch
    git push origin v$new_version
    
    print_success "Release complete! Version $new_version"
    echo
    echo "Next steps:"
    echo "  1. Create GitHub release from tag v$new_version"
    echo "  2. Publish to PyPI: python -m build && python -m twine upload dist/*"
    echo "  3. Update documentation"
    echo
}

# Show current version
show_current() {
    local version=$(get_current_version)
    echo "Current version: $version"
}

# Main
case "${1:-help}" in
    bump)
        bump_version "${2:-patch}"
        ;;
    changelog)
        generate_changelog "${2:-}"
        ;;
    release)
        do_release "${2:-patch}"
        ;;
    current)
        show_current
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
