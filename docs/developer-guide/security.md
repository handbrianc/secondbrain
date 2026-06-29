# Security Guide

Security considerations and best practices for deploying and using SecondBrain.

## Data Privacy

### Local Processing

All document processing happens locally:

- **Parsing**: Done on-host with Docling
- **Chunking**: Performed locally before storage
- **Embedding**: Sent to external API if using hosted models
- **Storage**: Vectors stored in your MongoDB instance

Understand which operations contact external services:

| Operation | External Contact | Data Shared |
|-----------|-----------------|-------------|
| Embedding generation | Embedding API | Text chunks for vectorization |
| LLM chat (RAG) | LLM API | Retrieved chunks + conversation |
| Application telemetry | Optional OTLP | Logs and traces |

### Sensitive Data Handling

Documents may contain sensitive information:

```bash
# Exclude directories with sensitive content
secondbrain ingest ./safe-docs --recursive

# Review source filter to prevent accidental ingestion
secondbrain delete --source "./passwords.txt"
```

### Audit Trail

Enable structured logging for compliance:

```bash
export SECONDBRAIN_LOG_FORMAT=json
export SECONDBRAIN_LOG_LEVEL=INFO
```

Logs capture operation metadata without document content.

## Credential Management

### API Keys

Store credentials securely:

```bash
# Environment variables (preferred for containers)
export SECONDBRAIN_OPENAI_API_KEY=sk-...

# .env file with restricted permissions (not in version control)
chmod 600 .env
```

### MongoDB Credentials

Use strong authentication:

```bash
# Connection string with credentials
mongodb://user:strong-password@host:27017/secondbrain

# TLS encryption
mongodb+srv://user:pass@cluster.mongodb.net/?tls=true
```

### Secret Rotation

Rotate API keys periodically:

1. Obtain new key from provider
2. Deploy updated credential
3. Verify functionality
4. Revoke old key

## Deployment Security

### Docker Security

```yaml
# docker-compose.prod.yml - production hardening
services:
  mongodb:
    image: mongo:7.0
    security_opt:
      - no-new-privileges:true
    read_only: false  # Needs writable volume for data
    cap_drop:
      - ALL
```

Run containers with least privilege:

```bash
docker run --cap-drop=ALL --security-opt=no-new-privileges secondbrain
```

### Network Isolation

Bind MongoDB to localhost in development:

```bash
mongod --bind_ip localhost
```

For network-accessible MongoDB, use firewall rules and TLS.

### File Permissions

Secure document directories:

```bash
# Restrict access to user only
chmod 700 ./documents/

# Restrict SecondBrain data directory
chmod 700 ~/.secondbrain/
```

## Dependency Vulnerabilities

### Automated Scanning

Regular vulnerability checks:

```bash
# Scan dependencies
pip install -e ".[security]"

# Check for vulnerabilities
safety check

# Check PyPI package health
pip-audit
```

### SBOM Generation

Generate Software Bill of Materials:

```bash
cyclonedx-bom -o sbom.json
```

Required for supply chain security compliance.

### Bandit Security Analysis

Static analysis for Python security issues:

```bash
bandit -r src/secondbrain/
```

## Rate Limiting

Protect against abuse and quota exhaustion:

```bash
# Configure rate limits
export SECONDBRAIN_RATE_LIMIT_ENABLED=true
export SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=10
export SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0
```

Monitor rate limit violations in logs.

## Input Validation

### File Type Validation

SecondBrain validates file extensions before processing:

```python
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx",
    ".html", ".md", ".txt", ...
}

# Reject unsupported types early
if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
    raise ValueError(f"Unsupported file type: {path.suffix}")
```

### Path Traversal Prevention

Sanitize file paths to prevent directory escapes:

```python
from pathlib import Path

resolved_path = Path(path).resolve()
allowed_base = Path("./data").resolve()

if not resolved_path.is_relative_to(allowed_base):
    raise ValueError("Path escape attempted")
```

### Query Injection Prevention

Search queries are treated as opaque strings:

```python
# Safe: query passed as literal value
filter = {"source": {"$eq": user_provided_source}}

# MongoDB handles escaping automatically
cursor = collection.find(filter)
```

## Security Checklist

Before production deployment:

- [ ] MongoDB bound to internal network
- [ ] Strong MongoDB credentials
- [ ] API keys secured in environment or vault
- [ ] Log format set to `json` for audit trails
- [ ] Rate limiting enabled
- [ ] `pip-audit` passes with no critical issues
- [ ] Docker runs with dropped capabilities
- [ ] File permissions restricted to owner

## Incident Response

If you suspect a security issue:

1. **Contain**: Rotate affected API keys immediately
2. **Assess**: Review logs for unauthorized access patterns
3. **Report**: Contact maintainers via GitHub Security advisories
4. **Remediate**: Follow published security bulletins

## Known Limitations

- **No access control**: Currently no per-user authentication
- **Local LLM bypass**: Traffic stays on-premises if using Ollama/local models
- **No encryption at rest**: MongoDB storage encryption depends on your MongoDB configuration