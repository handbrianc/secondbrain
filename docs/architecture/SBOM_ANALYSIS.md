# SBOM Analysis & Dependency Trade-offs

**Last Updated**: 2026-03-08 22:14
**SBOM File**: `docs/architecture/sbom.json` (0KB, CycloneDX 1.5)
**Total Production Dependencies**: 186

---

## Executive Summary

This document provides a comprehensive analysis of the Software Bill of Materials (SBOM) for SecondBrain, including license risk assessment, dependency trade-offs, and migration options.

### Current State

| Metric | Value |
|--------|-------|
| **Total Dependencies** | 186 |
| **Direct Dependencies** | 9 |
| **Transitive Dependencies** | 177 |
| **Install Size** | ~3GB (with PyTorch) |
| **High-Risk Licenses** | 3 ⚠️ |
| **Medium-Risk Licenses** | 3 ⚠️ |
| **Unknown Licenses** | 0 ✅ |
| **Low-Risk Licenses** | 180 ✅ |

---

## License Risk Assessment

### High Risk (GPL/LGPL)

| Package | License | Status | Concern |
|---------|---------|--------|---------|
| **pyinstaller** | GPL-2.0-only | Dev-only | Dev tool only |
| **pyinstaller-hooks-contrib** | GPL-2.0-only | Dev-only | Dev tool only |
| **chardet** | License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+) | Transitive | Weak copyleft - acceptable for internal use |

### Medium Risk (Weak Copyleft)

| Package | License | Reason |
|---------|---------|--------|
| **fqdn** | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Transitive dependency |
| **pathspec** | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Transitive dependency |
| **certifi** | MPL-2.0 | Required by httpx for HTTPS |

### Unknown Licenses

*All licenses identified.*

---

## Dependency Analysis

### Direct Dependencies

```toml
# pyproject.toml [project.dependencies]
click>=8.1.0
docling>=2.77.0
docling-core>=2.68.0
pymongo>=4.6.0
httpx>=0.27.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
rich>=14.0.0
python-dotenv>=1.2.2
```

---

## SBOM Generation

### Generating the SBOM

Run the analysis script:

```bash
python scripts/generate_sbom_analysis.py
```

This will:
1. Generate SBOM from current environment using CycloneDX
2. Analyze all licenses
3. Generate LICENSE-RISK-REPORT.md
4. Generate/update this SBOM_ANALYSIS.md
5. Generate license_analysis.json

---

## Compliance Notes

### High-Risk Packages

**chardet** (License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)): Transitive dependency via docling-core. LGPL allows linking from proprietary code. Acceptable for internal use.

**pyinstaller** (GPL-2.0-only): Build tool for creating distributable binaries. Not in production runtime. Safe to use for development.

**pyinstaller-hooks-contrib** (GPL-2.0-only): Build tool for creating distributable binaries. Not in production runtime. Safe to use for development.

### Medium-Risk Packages

The following packages use weak copyleft licenses (MPL-2.0, etc.):

- **certifi** (MPL-2.0): No viral effect on dependent code. Safe for MIT projects.
- **fqdn** (License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)): No viral effect on dependent code. Safe for MIT projects.
- **pathspec** (License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)): No viral effect on dependent code. Safe for MIT projects.

### Unknown License Packages

*All packages have identifiable licenses.*

---

## References

- [CycloneDX SBOM Specification](https://cyclonedx.org/)
- [MPL-2.0 License](https://www.mozilla.org/en-US/MPL/2.0/)
- [docling Project](https://github.com/docling-project/docling)

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-08 22:14 | SBOM updated via automated script |