# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in SecondBrain, please report it responsibly:

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email security@secondbrain.local with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any known mitigations

## Security Features

- **Environment-driven configuration**: Sensitive settings via environment variables
- **Input validation**: All user inputs validated before processing
- **Error handling**: Granular error types prevent information leakage
- **Rate limiting**: Ollama API rate limiting prevents abuse
- **Connection validation**: Service health checks with TTL caching

## Security Best Practices

1. Never commit API keys or credentials
2. Use the `.env` file for local configuration
3. Set strong credentials for MongoDB in production
4. Enable TLS for MongoDB connections
5. Keep dependencies updated (`pip install -U .`)

## Known Vulnerabilities & Mitigations

### Critical: docling-core CVE-2026-24009
- **Issue**: Remote Code Execution via unsafe YAML deserialization
- **Affected Versions**: docling-core < 2.48.4
- **Mitigation**: Upgrade to `docling-core>=2.48.4` (minimum version in pyproject.toml)
- **Status**: Fixed in current dependency specification

### Critical: MongoDB Server CVE-2025-14847 ("MongoBleed")
- **Issue**: Server-side vulnerability allowing unauthorized access
- **Affected MongoDB Server Versions**:
  - MongoDB 7.0: Upgrade to 7.0.28+
  - MongoDB 8.0: Upgrade to 8.0.17+
  - MongoDB 8.2: Upgrade to 8.2.3+
- **Note**: This is a MongoDB **server** vulnerability, not pymongo client
- **Action Required**: Ensure your MongoDB server instance is patched
- **Verification**: Check MongoDB server version with `mongod --version`

### Bandit Skips
The following bandit checks are intentionally skipped in `pyproject.toml`:
- **B101** (assert_used): CLI tools use assertions for development-time checks; not a security risk in this context
- **B602** (subprocess_with_shell): No subprocess calls with shell=True in codebase; skip is precautionary

## Acknowledgments

We thank the following for their security research:
- [Your Name Here]

## Related Documentation

- [Development Guide](./development.md) - Development workflow
- [Docker Setup](./docker.md) - Docker security
