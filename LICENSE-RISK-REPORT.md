# License Risk Report

**Project**: secondbrain
**Generated**: 2026-03-08 00:14:31
**SBOM File**: sbom.json

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Dependencies** | 126 |
| **Unique Licenses** | 14 |
| **Unknown Licenses** | 4 |
| **High Risk Packages** | 0 |
| **Medium Risk Packages** | 1 |
| **Low Risk Packages** | 121 |

### Overall Risk Assessment: **REQUIRES REVIEW**
- **WARNING**: 4 packages have unknown licenses requiring manual review

---

## Risk Classification

### HIGH RISK (Strong Copyleft)

**Count**: 0 packages

*No high-risk licenses found.*

### MEDIUM RISK (Weak Copyleft)

**Count**: 1 packages

| Package | Version | License | Concern |
|---------|---------|---------|---------|
| certifi | 2026.2.25 | MPL-2.0 | Weak copyleft - review distribution model |

### LOW RISK (Permissive)

**Count**: 121 packages

---

## Packages Requiring Manual Review

**Count**: 4

The following packages have unknown or missing license metadata:

- **numpy@2.4.2**
- **packaging@26.0**
- **regex@2026.2.28**
- **tqdm@4.67.3**

---

*Report generated from CycloneDX SBOM using automated license analysis.*
*Review date: 2026-03-08*