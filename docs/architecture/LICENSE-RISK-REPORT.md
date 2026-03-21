# License Risk Report

**Project**: secondbrain
**Generated**: 2026-03-21 00:25:33
**SBOM File**: sbom.json

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Dependencies** | 209 |
| **Unique Licenses** | 15 |
| **Unknown Licenses** | 0 |
| **High Risk Packages** | 3 |
| **Medium Risk Packages** | 4 |
| **Low Risk Packages** | 202 |

### Overall Risk Assessment: **REQUIRES REVIEW**
- **WARNING**: 3 packages use strong copyleft licenses (GPL/LGPL)

---

## Risk Classification

### HIGH RISK (Strong Copyleft)

**Count**: 3 packages

| Package | Version | License | Concern |
|---------|---------|---------|---------|
| pyinstaller | 6.19.0 | GPL-2.0-only | Strong copyleft - GPL requires open source |
| pyinstaller-hooks-contrib | 2026.3 | GPL-2.0-only | Strong copyleft - GPL requires open source |
| chardet | 5.2.0 | License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+) | Copyleft - may affect distribution |

### MEDIUM RISK (Weak Copyleft)

**Count**: 4 packages

| Package | Version | License | Concern |
|---------|---------|---------|---------|
| fqdn | 1.5.1 | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft - review distribution model |
| pathspec | 1.0.4 | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft - review distribution model |
| certifi | 2026.2.25 | MPL-2.0 | Weak copyleft - review distribution model |
| hypothesis | 6.151.9 | MPL-2.0 | Weak copyleft - review distribution model |

### LOW RISK (Permissive)

**Count**: 202 packages

Most dependencies use permissive licenses (MIT, Apache-2.0, BSD, ISC, etc.)


---

*Report generated from CycloneDX SBOM using automated license analysis.*
*Review date: 2026-03-21*