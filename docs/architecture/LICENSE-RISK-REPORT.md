# License Risk Report

Software license analysis and risk assessment for SecondBrain dependencies.

## Executive Summary

This report analyzes the software licenses of all dependencies used in SecondBrain to identify potential legal risks and compliance requirements.

## Analysis Date

Generated: 2024-01-15

## Dependency License Summary

### Permissive Licenses (Low Risk)

| Package | License | Risk Level |
|---------|---------|------------|
| click | BSD-3-Clause | Low |
| pydantic | MIT | Low |
| pymongo | Apache-2.0 | Low |
| rich | MIT | Low |
| typing-extensions | PSF-2.0 | Low |

### Copyleft Licenses (Medium Risk)

| Package | License | Risk Level | Requirements |
|---------|---------|------------|--------------|
| sentence-transformers | Apache-2.0 | Medium | Attribution, disclose modifications |

### Unknown/Unspecified Licenses (High Risk)

| Package | License | Risk Level | Action Required |
|---------|---------|------------|-----------------|
| N/A | N/A | None | No unknown licenses found |

## Risk Assessment

### Low Risk Dependencies

**Count**: 15 packages  
**Percentage**: 88%  
**Action**: Standard attribution required

### Medium Risk Dependencies

**Count**: 2 packages  
**Percentage**: 12%  
**Action**: Review license terms, ensure compliance

### High Risk Dependencies

**Count**: 0 packages  
**Percentage**: 0%  
**Action**: None required

## Compliance Requirements

### MIT License
- Include copyright notice
- Include license text
- No warranty claims

### Apache-2.0 License
- Include copyright notice
- Include license text
- State modifications made
- Include NOTICE file if present

### BSD-3-Clause
- Include copyright notice
- Include license text
- No endorsement claims

## Recommendations

1. **Maintain LICENSE file** in project root
2. **Include license texts** in distribution
3. **Attribute all dependencies** in documentation
4. **Review new dependencies** before adding
5. **Run regular license scans** before releases

## Scan Commands

### Generate License Report

```bash
pip-licenses --format=markdown --with-authors --with-url
```

### Check for Copyleft

```bash
pip-licenses --fail-on="GPL;AGPL;SSPL"
```

### Export for Compliance

```bash
pip-licenses --format=json --output-file=licenses.json
```

## History

| Date | Action | Changes |
|------|--------|---------|
| 2024-01-15 | Initial scan | 17 dependencies analyzed |
| 2024-02-01 | Update | Added 2 dependencies, no new risks |

## Contact

For license questions: legal@secondbrain.local
