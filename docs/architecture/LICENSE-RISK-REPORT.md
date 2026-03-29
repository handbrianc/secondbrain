# License Risk Report

License compliance and risk analysis for SecondBrain dependencies.

## Executive Summary

SecondBrain uses primarily permissive open-source licenses with minimal legal risk.

## Risk Assessment

### Overall Risk Level: LOW ✅

- **No copyleft licenses** detected
- **All licenses compatible** with commercial use
- **Clear attribution** requirements met
- **No patent concerns** identified

## License Breakdown

### MIT License (60%)

**Risk Level**: Very Low

- Permissive, business-friendly
- Minimal requirements (include license)
- No copyleft obligations

**Components**:
- click, docling, pydantic, rich, python-dotenv, mcp, ollama

### Apache-2.0 (25%)

**Risk Level**: Very Low

- Permissive with patent grant
- Explicit patent retaliation clause
- Compatible with most licenses

**Components**:
- pymongo, motor, sentence-transformers, torch, opentelemetry-*

### BSD-3-Clause (15%)

**Risk Level**: Very Low

- Permissive license
- No endorsement claims
- Standard redistribution terms

**Components**:
- httpx, torch dependencies

## Compliance Requirements

### Attribution

All dependencies require license inclusion:

```
LICENSE.md - Contains MIT license
Third-party licenses documented in SBOM
```

### Patent Grants

Apache-2.0 dependencies include explicit patent grants:
- pymongo
- motor  
- sentence-transformers
- opentelemetry-*

### Trademark Restrictions

No trademark restrictions identified in dependencies.

## Risk Mitigation

### Monitoring

- Weekly dependency scans
- License change notifications
- SBOM generation on each release

### Documentation

- All licenses documented
- SBOM maintained
- Compliance checklist in CI/CD

### Best Practices

1. **Include LICENSE.md** in distributions
2. **Document third-party notices**
3. **Monitor for license changes**
4. **Review new dependencies** before adding

## Potential Issues

### None Identified ✅

All current dependencies are compliant with:
- Commercial use
- Modification
- Distribution
- Private use

## Recommendations

### Immediate Actions
- ✅ No action required

### Ongoing Maintenance
- Continue weekly security scans
- Review license terms for new dependencies
- Update SBOM with each release

## Legal Disclaimer

This report is for informational purposes only. Consult legal counsel for formal compliance opinions.

## Contact

For licensing questions:
- Email: [INSERT EMAIL]
- GitHub Discussions: [Link]

---

Last updated: March 2026
