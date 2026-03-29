# Security Guide

Security best practices and guidelines for SecondBrain.

## Security Principles

### Local-First

- All document processing happens locally
- No data sent to external services
- User-controlled MongoDB connection
- Privacy by design

### Defense in Depth

- Input validation at all layers
- Type safety with Pydantic
- Secure default configuration
- Regular security audits

## Input Validation

### Document Validation

```python
from pydantic import BaseModel, Field, constr

class DocumentInput(BaseModel):
    title: constr(max_length=500)
    content: constr(max_length=1000000)
    metadata: dict = Field(default_factory=dict)
```

### Path Validation

```python
from pathlib import Path

def safe_path(base: Path, user_path: str) -> Path:
    """Prevent path traversal."""
    full_path = (base / user_path).resolve()
    if not str(full_path).startswith(str(base)):
        raise ValueError("Path traversal detected")
    return full_path
```

## Credential Management

### Environment Variables

```env
# .env (never commit!)
MONGODB_URI=mongodb://user:password@localhost:27017
JWT_SECRET=super-secret-key
```

### Loading Secrets

```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    mongodb_uri: str
    jwt_secret: str
    
    class Config:
        env_file = ".env"
        extra = "forbid"  # Prevent unknown env vars
```

## Dependency Security

### Scanning Tools

```bash
# Install security tools
pip install safety pip-audit bandit

# Run scans
safety check
pip-audit
bandit -r src/
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: ["-r", "src/"]
```

## MongoDB Security

### Authentication

```python
from pymongo import MongoClient

client = MongoClient(
    "mongodb://username:password@localhost:27017",
    authSource="admin"
)
```

### TLS/SSL

```python
client = MongoClient(
    "mongodb://localhost:27017",
    tls=True,
    tlsCAFile="/path/to/ca.pem",
    tlsCertificateKeyFile="/path/to/client.pem"
)
```

### Network Security

- Use private networks
- Restrict IP access
- Enable firewall rules
- Use VPN for remote access

## Error Handling

### Don't Leak Information

```python
# Good
try:
    doc = storage.get_document(doc_id)
except DocumentNotFoundError:
    raise HTTPException(status_code=404, detail="Document not found")

# Avoid
try:
    doc = storage.get_document(doc_id)
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))  # Leaks internals
```

## Audit Logging

### Security Events

```python
import logging

security_logger = logging.getLogger("security")

def log_auth_attempt(user_id: str, success: bool):
    security_logger.warning(
        f"Auth attempt: user={user_id} success={success}"
    )

def log_data_access(user_id: str, doc_id: str):
    security_logger.info(
        f"Data access: user={user_id} doc={doc_id}"
    )
```

## Vulnerability Response

### Reporting

Report vulnerabilities to:
- Email: security@example.com
- GitHub Security Advisories

### Response Timeline

- 24 hours: Acknowledgment
- 72 hours: Initial assessment
- 7 days: Patch development
- 14 days: Release

## Security Checklist

### Development

- [ ] Input validation implemented
- [ ] No hardcoded secrets
- [ ] Error messages don't leak info
- [ ] Dependencies up to date
- [ ] Security scans pass

### Deployment

- [ ] MongoDB authentication enabled
- [ ] TLS/SSL configured
- [ ] Firewall rules set
- [ ] Secrets managed securely
- [ ] Monitoring enabled

## Compliance

### Data Protection

- GDPR: Data stays local
- HIPAA: Not recommended for PHI
- SOC2: Audit logging available

## See Also

- [Security Policy](../SECURITY.md)
- [Vulnerability Reporting](security/vulnerability_report.md)
- [Dependency Management](../architecture/SBOM_ANALYSIS.md)
