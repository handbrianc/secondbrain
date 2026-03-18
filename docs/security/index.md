# Security Guide

Security best practices and policies for SecondBrain.

## Security Policy

### Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ |

### Reporting Vulnerabilities

If you discover a security vulnerability:

1. **DO NOT** create a public GitHub issue
2. Email responsibly to: security@secondbrain.local
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Known mitigations (if any)

## Security Features

SecondBrain includes several security features:

### Environment-Based Configuration

Sensitive settings are configured via environment variables:
```bash
SECONDBRAIN_MONGO_URI=mongodb://user:pass@host:27017
```

### Input Validation

All user inputs are validated:
- MongoDB URI format
- sentence-transformers URL format
- File paths (prevents path traversal)
- Search queries (sanitization)

### Error Handling

Granular error types prevent information leakage:
- Specific error messages
- No stack traces in production
- Controlled error responses

### Rate Limiting

Built-in rate limiting protects against:
- API abuse
- Denial of service
- Resource exhaustion

### Connection Validation

Health checks with TTL caching:
- Service availability monitoring
- Connection pool management
- Automatic reconnection

## Security Best Practices

### For Users

1. **Never commit credentials**
   - Use `.env` files for local configuration
   - Add `.env` to `.gitignore`

2. **Use strong credentials**
   - MongoDB: Strong passwords
   - Enable authentication in production

3. **Enable TLS**
   - Use TLS for MongoDB connections in production
   - Validate certificates

4. **Keep dependencies updated**
   ```bash
   pip install -U secondbrain
   ```

5. **Regular security scans**
   ```bash
   bandit -r src/
   safety check
   ```

### For Developers

1. **Validate all inputs**
   - Use Pydantic for type validation
   - Sanitize user-provided data

2. **Handle errors securely**
   - Don't expose internal details
   - Log errors securely

3. **Use secure defaults**
   - Secure by default configuration
   - Principle of least privilege

4. **Review dependencies**
   - Check for known vulnerabilities
   - Use `safety` and `bandit`

## Known Vulnerabilities

### Current Dependencies

Check for known vulnerabilities:
```bash
pip install safety
safety check
```

### Bandit Security Scanning

Run bandit to check for common issues:
```bash
bandit -r src/secondbrain/
```

See [Bandit Report](./bandit_report.json) for recent scan results.

## Security Checklist

Before deploying to production:

- [ ] Use strong MongoDB credentials
- [ ] Enable TLS for database connections
- [ ] Configure firewall rules
- [ ] Set up monitoring and alerts
- [ ] Regular dependency updates
- [ ] Security scan with bandit
- [ ] Review error handling
- [ ] Test authentication/authorization

## Compliance

### Data Privacy

- All data stored locally (no cloud)
- No data transmitted externally
- User controls all data

### Logging

- Sensitive data not logged
- Configurable log levels
- Secure log storage

## Incident Response

If you suspect a security incident:

1. **Isolate** - Disconnect affected systems
2. **Assess** - Determine scope of impact
3. **Report** - Contact security team
4. **Remediate** - Fix vulnerability
5. **Document** - Record incident details

## Related Documentation

- [Configuration](../getting-started/configuration.md) - Secure configuration
- [Developer Guide](../developer-guide/index.md) - Development security
- [Changelog](../developer-guide/changelog.md) - Security updates

## Acknowledgments

We thank the security research community for responsible disclosure.

---

For security questions or concerns, contact: security@secondbrain.local