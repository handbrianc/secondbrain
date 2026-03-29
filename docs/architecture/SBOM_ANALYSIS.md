# SBOM Analysis

Software Bill of Materials (SBOM) for SecondBrain.

## Overview

This document provides a comprehensive inventory of all software components and dependencies used in SecondBrain.

## Runtime Dependencies

### Core Dependencies

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| click | >=8.1.0 | CLI framework | BSD-3-Clause |
| docling | >=2.81.0 | Document parsing | MIT |
| docling-core | >=2.48.4 | Document utilities | MIT |
| pymongo | >=4.6.0 | MongoDB driver | Apache-2.0 |
| motor | >=3.0.0 | Async MongoDB | Apache-2.0 |
| httpx | >=0.28.1 | HTTP client | BSD-3-Clause |
| pydantic | >=2.0.0 | Data validation | MIT |
| pydantic-settings | >=2.0.0 | Settings management | MIT |
| rich | >=14.0.0 | Terminal UI | MIT |
| python-dotenv | >=1.2.2 | Environment config | BSD-3-Clause |
| sentence-transformers | >=5.0.0 | Text embeddings | Apache-2.0 |
| torch | >=2.0.0 | Deep learning | BSD-3-Clause |
| opentelemetry-api | >=1.20.0 | Tracing | Apache-2.0 |
| opentelemetry-sdk | >=1.20.0 | Tracing SDK | Apache-2.0 |
| ollama | >=0.1.0 | LLM integration | MIT |
| mcp | >=1.0.0 | MCP server | MIT |

## Development Dependencies

### Testing

| Package | Purpose |
|---------|---------|
| pytest | Test runner |
| pytest-asyncio | Async test support |
| pytest-cov | Coverage reporting |
| pytest-benchmark | Performance testing |
| pytest-xdist | Parallel test execution |
| pytest-hypothesis | Property-based testing |
| mongomock | MongoDB mocking |

### Code Quality

| Package | Purpose |
|---------|---------|
| ruff | Linting & formatting |
| mypy | Type checking |
| bandit | Security scanning |
| vulture | Dead code detection |

### Security

| Package | Purpose |
|---------|---------|
| safety | Vulnerability scanning |
| pip-audit | pip vulnerability check |
| cyclonedx-bom | SBOM generation |

### Documentation

| Package | Purpose |
|---------|---------|
| mkdocs | Documentation generator |
| mkdocstrings | Auto-generated docs |
| mkdocs-material | Documentation theme |

## License Compliance

### Permissive Licenses

**MIT License** (Majority of dependencies)
- Allows commercial use, modification, distribution
- Requires license inclusion

**Apache-2.0**
- Allows commercial use, modification, distribution
- Includes patent grant
- Requires license and copyright notice

**BSD-3-Clause**
- Allows commercial use, modification, distribution
- Requires license inclusion
- No endorsement claims

### Copyleft Licenses

No copyleft (GPL, LGPL, AGPL) dependencies detected.

## Security Vulnerabilities

### Current Status

All known vulnerabilities have been addressed:

- Regular security scans via Safety and pip-audit
- Automated dependency updates
- Manual review of critical updates

### Scanning Schedule

- **Pre-commit**: Bandit, Safety
- **CI/CD**: Full security scan
- **Weekly**: Dependency update check

## Dependency Updates

### Update Policy

1. **Critical Security**: Immediate update
2. **High Priority**: Within 7 days
3. **Medium Priority**: Within 30 days
4. **Low Priority**: Monthly review

### Update Process

```bash
# Check for outdated packages
pip list --outdated

# Update specific package
pip install --upgrade package-name

# Run security scan
safety check

# Generate SBOM
cyclonedx-py -o sbom.json
```

## Third-Party Notices

### Sentence Transformers

Uses pre-trained models from Hugging Face. Each model has its own license.

### Docling

Document parsing technology powered by IBM.

### MongoDB

Uses MongoDB Atlas or self-hosted MongoDB instances.

## SBOM Generation

Generate updated SBOM:

```bash
# Install CycloneDX
pip install cyclonedx-bom

# Generate SBOM
cyclonedx-py -r -o sbom.json

# Output in SPDX format
cyclonedx-py -r --format spdx -o sbom.spdx
```

## Compliance

SecondBrain complies with:
- Open Source Initiative (OSI) standards
- SPDX format for SBOM
- NIST Software Supply Chain Security

## Contact

For licensing questions:
- Email: [INSERT EMAIL]
- GitHub Issues: [Link to issues]

---

Last updated: March 2026
