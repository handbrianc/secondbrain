# Security Policy

## Security First

SecondBrain prioritizes the security of your data and system. This document outlines our approach to security and how to report vulnerabilities.

## Reporting a Vulnerability

We take all security vulnerabilities seriously. If you discover a security issue, please report it responsibly:

### Responsible Disclosure

**DO NOT** create public GitHub issues for security vulnerabilities.

Instead, report via:
- **GitHub Security Advisory**: [Report a vulnerability](https://github.com/your-org/secondbrain/security/advisories/new)
- **Email**: [INSERT SECURITY EMAIL]

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

We will acknowledge your report within 48 hours and provide a timeline for resolution.

## Security Measures

### Local-First Architecture

- All document processing happens locally
- No data is sent to external services
- MongoDB connection is user-controlled
- Embedding models run locally via Sentence Transformers

### Dependency Management

We maintain security through:

- **Regular Updates**: Dependencies are monitored and updated regularly
- **Security Scanning**: Automated scans with:
  - [Bandit](https://bandit.readthedocs.io/) - Python security linter
  - [Safety](https://pyup.io/safety/) - Vulnerability scanner
  - [pip-audit](https://pypi.org/project/pip-audit/) - pip vulnerability checker
  - [CodeQL](https://codeql.github.com/) - Semantic code analysis

- **SBOM Generation**: Software Bill of Materials via [CycloneDX](https://cyclonedx.org/)

### Pre-commit Security Hooks

```bash
# Run security checks before committing
pre-commit run --all-files

# This runs:
# - Bandit security scan
# - Safety vulnerability check
# - Ruff linting
```

### Type Safety

- Strict mypy configuration
- No `Any` types without justification
- Comprehensive type annotations
- Prevents entire class of runtime errors

### Input Validation

- Pydantic for data validation
- Strict input sanitization
- Path traversal prevention
- SQL injection prevention (MongoDB parameterization)

## Security Best Practices

### For Users

1. **Keep Dependencies Updated**: Regularly run `pip install --upgrade secondbrain`
2. **Use Environment Variables**: Never hardcode credentials
3. **Secure MongoDB**: Use authentication and encryption in production
4. **Limit Permissions**: Run with minimal required permissions
5. **Review SBOM**: Check Software Bill of Materials for known vulnerabilities

### For Developers

1. **Run Security Scans**: Include in CI/CD pipeline
2. **Review Dependencies**: Audit new dependencies before adding
3. **Follow OWASP**: Adhere to OWASP Top 10 guidelines
4. **Code Review**: All changes reviewed for security issues
5. **Test Security Paths**: Include security test cases

## Vulnerability Management

### Response Timeline

- **0-24 hours**: Initial assessment and acknowledgment
- **24-72 hours**: Reproduction and impact analysis
- **3-7 days**: Fix development and testing
- **7-14 days**: Release and disclosure

### Severity Levels

| Level | Response Time | Examples |
|-------|---------------|----------|
| Critical | 24-48 hours | RCE, data exfiltration |
| High | 3-5 days | Auth bypass, privilege escalation |
| Medium | 7-10 days | XSS, CSRF, info disclosure |
| Low | 14-30 days | Minor issues, best practices |

## Security Dependencies

We track and update security-critical dependencies:

- **Pydantic**: Data validation, strict mode
- **PyMongo/Motor**: MongoDB drivers, connection pooling
- **Click**: CLI framework, input handling
- **Rich**: Terminal output, XSS prevention
- **Docling**: Document parsing, sandboxed execution

## Compliance

SecondBrain follows security best practices from:

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE/SANS Top 25](https://cwe.mitre.org/data/sans-top-25.html)
- [NIST Secure Software Development Framework](https://www.nist.gov/ssdf)

## Contact

For security questions or concerns:
- Email: [INSERT SECURITY EMAIL]
- GitHub Discussions: [Security category](https://github.com/your-org/secondbrain/discussions/categories/security)

---

Last updated: March 2026
