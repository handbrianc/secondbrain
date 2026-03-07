# License Risk Report

**Project**: secondbrain
**Generated**: 2026-03-07 00:35:14
**SBOM File**: sbom.json

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Dependencies** | 181 |
| **Unique Licenses** | 18 |
| **Unknown Licenses** | 5 |
| **High Risk Packages** | 3 |
| **Medium Risk Packages** | 3 |
| **Low Risk Packages** | 170 |

### Overall Risk Assessment: **REQUIRES REVIEW**
- **WARNING**: 3 packages use strong copyleft licenses (GPL/LGPL)
- **WARNING**: 5 packages have unknown licenses requiring manual review

---

## Risk Classification

### HIGH RISK (Strong Copyleft)

**Count**: 3 packages

| Package | Version | License | Concern |
|---------|---------|---------|---------|
| pyinstaller | 6.19.0 | GPL-2.0-only | Strong copyleft - GPL requires open source |
| pyinstaller-hooks-contrib | 2026.1 | GPL-2.0-only | Strong copyleft - GPL requires open source |
| chardet | 5.2.0 | License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+) | Copyleft - may affect distribution |

### MEDIUM RISK (Weak Copyleft)

**Count**: 3 packages

| Package | Version | License | Concern |
|---------|---------|---------|---------|
| fqdn | 1.5.1 | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft - review distribution model |
| pathspec | 1.0.4 | License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft - review distribution model |
| certifi | 2026.2.25 | MPL-2.0 | Weak copyleft - review distribution model |

### LOW RISK (Permissive)

**Count**: 170 packages

---

## Packages Requiring Manual Review

**Count**: 5

The following packages have unknown or missing license metadata:

- **cryptography@46.0.5**
- **numpy@2.4.2**
- **packaging@26.0**
- **regex@2026.2.19**
- **tqdm@4.67.3**

---

*Report generated from CycloneDX SBOM using automated license analysis.*
*Review date: 2026-03-07*