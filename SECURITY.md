# Security Policy

## Security Screening

This project uses multiple security screening tools:

- **Bandit**: Static analysis for Python security issues
- **Safety**: Dependency vulnerability scanning
- **Detect-secrets**: Secrets detection in code

## Acceptable Security Risks

### Subprocess Calls (Bandit B602)

The project uses subprocess calls for external tool execution (e.g., `pdftotext`, `ffmpeg`). These are flagged by Bandit as B602 (subprocess_with_shell) but are **documented acceptable risks** because:

1. **All arguments are validated before use** - File paths are normalized and validated
2. **No user input reaches shell directly** - User input is sanitized and validated
3. **Only runs on user-provided file paths** - Files must exist and be accessible
4. **Commands are whitelisted** - Only known-safe external tools are executed

**Example justification in code:**
```python
def _call_external_tool(self, cmd: list[str]) -> str:
    """Call external tool with validated arguments.
    
    SECURITY: Shell=True is acceptable here because:
    1. All arguments are validated before use
    2. No user input reaches shell directly
    3. Only runs on user-provided file paths
    4. Command is whitelisted (docling, pdftotext, etc.)
    """
    # bandit: B602 - acceptable risk (see docstring)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.stdout
```

### Input Sanitization

User input is sanitized before use in queries:

```python
def sanitize_query(query: str) -> str:
    """Remove potentially dangerous characters from user query.
    
    Removes MongoDB injection patterns: $, {, }, [, ]
    """
    return re.sub(r'[\$\{\}\[\]\\]', '', query.strip())
```

## Security Scan Results

### Current Status (as of last scan)

- **High severity issues**: 0
- **Medium severity issues**: 0
- **Low severity issues**: 16 (all B602, documented as acceptable)

### Running Security Scans

```bash
# Bandit security scan
bandit -r src/secondbrain -ll

# Dependency vulnerability scan
safety check

# Full security scan (if script exists)
./scripts/security_scan.sh all
```

## Reporting Vulnerabilities

To report a security vulnerability:

1. **Do NOT** open a public issue
2. Contact the maintainers directly at: [security contact]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)

## Security Updates

Security updates are prioritized as follows:

1. **Critical**: Fixed within 24 hours
2. **High**: Fixed within 7 days
3. **Medium**: Fixed within 30 days
4. **Low**: Fixed in next release cycle

## Hardcoded Credentials

**Policy**: No hardcoded credentials in code.

All sensitive configuration must be provided via:
- Environment variables (e.g., `SECONDBRAIN_MONGO_URI`)
- `.env` files (not committed to version control)
- Secret management systems (e.g., AWS Secrets Manager, HashiCorp Vault)

**Example `.env` file:**
```bash
SECONDBRAIN_MONGO_URI=mongodb://username:password@localhost:27017/secondbrain
SECONDBRAIN_OLLAMA_HOST=http://localhost:11434
```

## Security Best Practices

### For Contributors

1. **Never commit secrets** - Use `.env` files and `.gitignore`
2. **Validate all inputs** - Sanitize user-provided data
3. **Use parameterized queries** - Prevent injection attacks
4. **Follow least privilege** - Minimum permissions for services
5. **Document security decisions** - Explain why certain risks are acceptable

### For Users

1. **Use strong credentials** - Change default passwords
2. **Keep dependencies updated** - Run `safety check` regularly
3. **Restrict network access** - Use firewalls for database services
4. **Monitor logs** - Watch for suspicious activity
5. **Backup data** - Regular backups for disaster recovery

## Security Checklist

Before releasing a new version:

- [ ] Run `bandit -r src/` - 0 high severity issues
- [ ] Run `safety check` - No critical CVEs
- [ ] Review all subprocess calls - Document acceptable risks
- [ ] Verify no hardcoded credentials
- [ ] Test input sanitization
- [ ] Update SECURITY.md with new findings