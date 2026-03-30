# SecondBrain Scripts

This directory contains utility scripts for development, testing, and maintenance.

## Table of Contents

- [Dependency Management Scripts](#dependency-management-scripts)
- [Security Scanning Scripts](#security-scanning-scripts)
- [Benchmarking Scripts](#benchmarking-scripts)
- [Build & Maintenance Scripts](#build--maintenance-scripts)

---

## Dependency Management Scripts

### `update_dependencies.sh`

Check for outdated dependencies and generate update reports.

```bash
# Check for outdated dependencies
./scripts/update_dependencies.sh check

# Generate JSON report
./scripts/update_dependencies.sh check --format json --output ./reports

# Apply safe updates (minor/patch only)
./scripts/update_dependencies.sh update

# Full workflow: check, update, and run tests
./scripts/update_dependencies.sh full --run-tests

# Show help
./scripts/update_dependencies.sh --help
```

**Output**: Reports in `reports/dependency-updates/`

**Formats**: text (default), json, html

### `audit_dependencies.sh`

Run comprehensive security scanning on dependencies.

```bash
# Run all security tools
./scripts/audit_dependencies.sh

# Run specific tool
./scripts/audit_dependencies.sh pip-audit
./scripts/audit_dependencies.sh safety
./scripts/audit_dependencies.sh bandit

# Generate SBOM only
./scripts/audit_dependencies.sh --generate-sbom-only

# JSON output for CI/CD
./scripts/audit_dependencies.sh --format json --output ./reports/security-audit

# Show help
./scripts/audit_dependencies.sh --help
```

**Output**: Reports in `reports/security-audit/`

**Tools**: pip-audit, safety, bandit

### `generate_sbom.sh` / `generate_sbom.py`

Generate Software Bill of Materials (SBOM) in multiple formats.

```bash
# Generate SBOM in all formats
./scripts/generate_sbom.sh

# Generate only SPDX format
./scripts/generate_sbom.sh --format spdx

# Generate only CycloneDX format
./scripts/generate_sbom.sh --format cyclonedx

# Compare with previous SBOM
./scripts/generate_sbom.sh --compare

# Using Python wrapper
python scripts/generate_sbom.py --format all --validate

# Show help
./scripts/generate_sbom.sh --help
python scripts/generate_sbom.py --help
```

**Output**: Reports in `reports/sbom/`

**Formats**: SPDX 2.3 JSON, CycloneDX JSON

### `validate_dependencies.sh`

Validate dependencies for pre-commit hooks.

```bash
# Run all validations
./scripts/validate_dependencies.sh

# Strict mode (fail on warnings)
./scripts/validate_dependencies.sh --strict

# Skip specific checks
./scripts/validate_dependencies.sh --no-security

# Verbose output
./scripts/validate_dependencies.sh --verbose

# Show help
./scripts/validate_dependencies.sh --help
```

**Checks**: TOML syntax, outdated dependencies, security vulnerabilities

---

## Security Scanning Scripts

### `security_scan.sh`

Comprehensive security scanning wrapper.

```bash
# Run all security checks
./scripts/security_scan.sh

# Run specific check
./scripts/security_scan.sh audit
./scripts/security_scan.sh safety
./scripts/security_scan.sh bandit
./scripts/security_scan.sh sbom

# Show help
./scripts/security_scan.sh help
```

---

## Benchmarking Scripts

### `run_benchmarks.sh`

Main benchmark runner with multiple modes:

```bash
# Run benchmarks only
./scripts/run_benchmarks.sh run

# Run and compare against baseline
./scripts/run_benchmarks.sh compare

# Run and save as new baseline
./scripts/run_benchmarks.sh baseline

# Full regression check
./scripts/run_benchmarks.sh full
```

### `benchmark_compare.py`

Benchmark comparison tool for detecting regressions:

```bash
# Compare current results against baseline
python scripts/benchmark_compare.py compare \
    --current benchmark-results.json \
    --baseline benchmarks/baselines/main.json \
    --threshold 0.10

# Save new baseline
python scripts/benchmark_compare.py save-baseline \
    --input benchmark-results.json \
    --name main
```

### `pre-commit-benchmark.sh`

Pre-commit hook for automatic regression checking:

```bash
# Enable in .pre-commit-config.yaml
# See docs/performance-testing.md for setup
```

---

## Build & Maintenance Scripts

### `build.sh`

Build the project for distribution.

```bash
# Build distribution packages
./scripts/build.sh
```

### `validate.sh`

Run validation checks.

```bash
# Run validation
./scripts/validate.sh
```

### `cleanup_reports.sh`

Clean up old report files.

```bash
# Clean old reports
./scripts/cleanup_reports.sh
```

### `cleanup_coverage.sh`

Clean up coverage reports.

```bash
# Clean coverage data
./scripts/cleanup_coverage.sh
```

### `start_test_services.sh` / `stop_test_services.sh`

Manage test services (MongoDB, etc.).

```bash
# Start test services
./scripts/start_test_services.sh

# Stop test services
./scripts/stop_test_services.sh
```

---

## Configuration

### Dependency Management

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `VIRTUAL_ENV` | Virtual environment path | Auto-detected |
| `OUTPUT_DIR` | Report output directory | `reports/` |

### Benchmarking

Environment variables:

- `BENCHMARK_BASELINE` - Baseline file path (default: `benchmarks/baselines/main.json`)
- `BENCHMARK_THRESHOLD` - Regression threshold 0.0-1.0 (default: 0.10)
- `BENCHMARK_OUTPUT` - Results output file (default: `benchmark-results.json`)
- `BENCHMARK_SKIP` - Skip benchmark check (set to "1" to skip)
- `BENCHMARK_FAST` - Fast mode for pre-commit (set to "1" for quick checks)

---

## Report Locations

| Report Type | Location |
|-------------|----------|
| Dependency updates | `reports/dependency-updates/` |
| Security audit | `reports/security-audit/` |
| SBOM files | `reports/sbom/` |
| Benchmark results | `benchmark-results.json` |
| Coverage reports | `htmlcov/` |

---

## Documentation

- [Dependency Management Guide](../docs/developer-guide/dependency-management.md)
- [Performance Testing Guide](../docs/performance-testing.md)
- [Security Guide](../docs/security/index.md)
- [Developer Guide](../docs/developer-guide/index.md)
