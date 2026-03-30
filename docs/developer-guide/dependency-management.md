# Dependency Management Guide

This guide covers dependency management practices for the SecondBrain project, including automated updates, security scanning, and SBOM generation.

## Table of Contents

- [Overview](#overview)
- [Dependency Files](#dependency-files)
- [Checking for Updates](#checking-for-updates)
- [Applying Updates](#applying-updates)
- [Security Scanning](#security-scanning)
- [SBOM Generation](#sbom-generation)
- [Pre-commit Validation](#pre-commit-validation)
- [Troubleshooting](#troubleshooting)

## Overview

SecondBrain manages dependencies through `pyproject.toml` with the following categories:

- **Runtime dependencies**: Required for application functionality
- **Dev dependencies**: Tools for development, testing, and linting
- **Optional dependencies**: Feature-specific extras (e.g., `opentelemetry`)

### Dependency Management Tools

| Tool | Purpose | Installation |
|------|---------|--------------|
| `pip` | Package installation and management | Built-in |
| `pip-audit` | Security vulnerability scanning | `pip install pip-audit` |
| `safety` | Alternative vulnerability scanner | `pip install safety` |
| `bandit` | Static security analysis | `pip install bandit` |
| `cyclonedx-py` | SBOM generation | `pip install cyclonedx-bom` |

## Dependency Files

### pyproject.toml

Main dependency configuration file:

```toml
[project]
dependencies = [
    "click>=8.1.0",
    "docling>=2.81.0",
    # ... runtime dependencies
]

[project.optional-dependencies]
dev = [
    "ruff>=0.15.5",
    "pytest>=8.0.0",
    # ... dev dependencies
]
```

### Virtual Environment

Dependencies are installed in a virtual environment:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Install dependencies
pip install -e ".[dev]"
```

## Checking for Updates

### Automated Check Script

Use the `update_dependencies.sh` script to check for outdated dependencies:

```bash
# Basic check
./scripts/update_dependencies.sh check

# Check with JSON output
./scripts/update_dependencies.sh check --format json --output ./reports

# Verbose check including major versions
./scripts/update_dependencies.sh check --verbose --major
```

### Manual Check

```bash
# List outdated packages
pip list --outdated

# Filter for specific package
pip list --outdated | grep <package-name>
```

### Output Formats

The update script supports three output formats:

- **text**: Human-readable report (default)
- **json**: Machine-readable JSON for CI/CD integration
- **html**: Formatted HTML report for sharing

## Applying Updates

### Safe Updates (Minor/Patch Only)

```bash
# Apply safe updates automatically
./scripts/update_dependencies.sh update

# Dry run - see what would be updated
./scripts/update_dependencies.sh update --dry-run
```

### Full Update Workflow

```bash
# Check, update, and run tests
./scripts/update_dependencies.sh full --run-tests
```

### Manual Updates

```bash
# Update specific package
pip install --upgrade <package-name>

# Update all packages (use with caution)
pip install --upgrade $(pip list --outdated | tail -n +3 | awk '{print $1}')

# Update only runtime dependencies
pip install --upgrade $(grep -A 20 'dependencies = \[' pyproject.toml | grep '"' | cut -d'"' -f2)
```

### Best Practices

1. **Test after updates**: Always run tests after updating dependencies
2. **Review breaking changes**: Check changelogs for major version updates
3. **Update incrementally**: Update one package at a time for easier debugging
4. **Use lock files**: Consider using `pip-tools` or `poetry` for reproducible builds

## Security Scanning

### Automated Security Audit

```bash
# Run all security tools
./scripts/audit_dependencies.sh

# Run only pip-audit
./scripts/audit_dependencies.sh pip-audit

# Run only safety check
./scripts/audit_dependencies.sh safety

# Run only bandit static analysis
./scripts/audit_dependencies.sh bandit
```

### Output Formats

```bash
# JSON output for CI/CD
./scripts/audit_dependencies.sh --format json --output ./reports/security-audit

# HTML report
./scripts/audit_dependencies.sh --format html
```

### Security Tools

#### pip-audit

Scans installed packages for known vulnerabilities:

```bash
# Quick scan
pip-audit

# Full report with descriptions
pip-audit --desc on

# Scan specific requirements file
pip-audit --requirements requirements.txt
```

#### safety

Alternative vulnerability scanner:

```bash
# Basic check
safety check

# Full report
safety check --full-report

# JSON output
safety check --output json --output-file safety-report.json
```

#### bandit

Static analysis for security issues in Python code:

```bash
# Scan source code
bandit -r src/secondbrain -c pyproject.toml -ll

# JSON output
bandit -r src/secondbrain -c pyproject.toml -f json -o bandit-report.json
```

### Ignoring Vulnerabilities

Some vulnerabilities can be safely ignored in the local CLI context. These are configured in `pyproject.toml`:

```toml
[tool.safety]
ignore = [
    "CVE-2026-33230",  # nltk dev dependency - not in production
    "54843",           # transitive dependency - not exploitable
]
```

**Note**: Always document why a vulnerability is ignored and ensure it's truly not exploitable in your context.

## SBOM Generation

### Generating SBOM

```bash
# Generate SBOM in all formats
./scripts/generate_sbom.sh

# Generate only SPDX format
./scripts/generate_sbom.sh --format spdx

# Generate only CycloneDX format
./scripts/generate_sbom.sh --format cyclonedx

# Generate without dev dependencies
./scripts/generate_sbom.sh --no-dev

# Compare with previous SBOM
./scripts/generate_sbom.sh --compare
```

### Python Interface

```bash
# Generate SBOM using Python wrapper
python scripts/generate_sbom.py --format all --output ./reports/sbom

# Validate generated SBOM
python scripts/generate_sbom.py --validate
```

### SBOM Formats

#### SPDX (Software Package Data Exchange)

- **Format**: `sbom.spdx.json`
- **Purpose**: Standardized license compliance and supply chain security
- **Usage**: Legal compliance, vulnerability tracking

#### CycloneDX

- **Format**: `sbom.cyclonedx.json`
- **Purpose**: Software supply chain security
- **Usage**: Vulnerability management, dependency tracking

### SBOM Location

Generated SBOM files are stored in:

```
reports/sbom/
├── sbom.cyclonedx.json    # CycloneDX format
├── sbom.spdx.json         # SPDX format
└── sbom.cyclonedx.json.previous  # Previous version (for comparison)
```

## Pre-commit Validation

### Automatic Validation

Dependency validation runs automatically on every commit via pre-commit hooks:

```bash
# Pre-commit hook checks:
# - pyproject.toml syntax validation
# - Outdated dependency warnings
# - Security vulnerability checks
```

### Manual Validation

```bash
# Run validation manually
./scripts/validate_dependencies.sh

# Strict mode (fail on warnings)
./scripts/validate_dependencies.sh --strict

# Skip security checks
./scripts/validate_dependencies.sh --no-security

# Verbose output
./scripts/validate_dependencies.sh --verbose
```

### Pre-commit Configuration

View hook configuration in `.pre-commit-config.yaml`:

```yaml
- id: validate-dependencies
  name: Validate Dependencies
  entry: bash scripts/validate_dependencies.sh
  language: system
  pass_filenames: false
  always_run: true
  stages: [pre-commit]
```

## Troubleshooting

### Common Issues

#### "Virtual environment not activated"

**Problem**: Scripts warn about inactive virtual environment.

**Solution**:
```bash
source venv/bin/activate
```

#### "Tool not found: pip-audit"

**Problem**: Security scanning tools not installed.

**Solution**:
```bash
pip install -e ".[dev]"
```

Scripts will auto-install missing tools, but manual installation is recommended.

#### "Invalid TOML syntax"

**Problem**: `pyproject.toml` has syntax errors.

**Solution**:
```bash
# Validate TOML syntax
python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"

# Fix syntax errors (missing brackets, quotes, etc.)
```

#### "Dependency conflicts detected"

**Problem**: Conflicting version requirements.

**Solution**:
```bash
# Show dependency conflicts
pip check

# Resolve conflicts by updating version constraints
# in pyproject.toml and reinstalling
pip install -e ".[dev]"
```

#### "Vulnerabilities found but cannot update"

**Problem**: Security vulnerabilities in transitive dependencies.

**Solution**:
1. Check if vulnerability affects your usage context
2. Update direct dependencies (may pull fixed transitive deps)
3. Add to safety ignore list if not exploitable (with documentation)

### Getting Help

- Check script help: `./scripts/<script-name>.sh --help`
- Enable verbose mode: Add `--verbose` flag
- Review logs: Check output in `reports/` directory
- Open an issue: [GitHub Issues](https://github.com/your-org/secondbrain/issues)

## Quick Reference

### Common Commands

```bash
# Check dependencies
./scripts/update_dependencies.sh check

# Update dependencies safely
./scripts/update_dependencies.sh update

# Run security audit
./scripts/audit_dependencies.sh

# Generate SBOM
./scripts/generate_sbom.sh

# Validate dependencies
./scripts/validate_dependencies.sh
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VIRTUAL_ENV` | Virtual environment path | Auto-detected |
| `OUTPUT_DIR` | Report output directory | `reports/` |

### Report Locations

| Report Type | Location |
|-------------|----------|
| Dependency updates | `reports/dependency-updates/` |
| Security audit | `reports/security-audit/` |
| SBOM files | `reports/sbom/` |

## Related Documentation

- [Contributing Guide](../../CONTRIBUTING.md)
- [Security Guide](../security/index.md)
- [Development Setup](./development-setup.md)
- [pyproject.toml Reference](https://packaging.python.org/en/latest/specifications/pyproject-toml/)
