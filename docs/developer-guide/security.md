# Security Guide

Security considerations and best practices for deploying and using SecondBrain.

## Data Privacy

### Local Processing

All document processing happens locally:

- **Parsing**: Done on-host with Docling
- **Chunking**: Performed locally before storage
- **Embedding**: Sent to external API if using hosted models
- **Storage**: Vectors stored in your Qdrant instance; conversations in a local SQLite file

Understand which operations contact external services:

| Operation | External Contact | Data Shared |
| ----------- | ----------------- | ------------- |
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

### Qdrant API Key

If your Qdrant instance requires authentication, configure the optional API key:

```bash
# Optional API key for Qdrant
export SECONDBRAIN_QDRANT_API_KEY=your-qdrant-api-key
```

### SQLite File Permissions

Conversation data is stored in a local SQLite file (default `~/.secondbrain/secondbrain.db`). Restrict access to the data directory:

```bash
chmod 700 ~/.secondbrain/
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
  qdrant:
    image: qdrant/qdrant
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

Keep Qdrant bound to localhost in development:

```bash
# Qdrant with an API key and localhost binding
SECONDBRAIN_QDRANT_API_KEY=...
SECONDBRAIN_QDRANT_URL=http://localhost:6333
```

For network-accessible Qdrant, use firewall rules and TLS.

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
# Safe: query vector is opaque; metadata filters use typed payload conditions
filter_ = {
    "must": [
        {"key": "source_file", "match": {"value": user_provided_source}},
    ]
}

# Qdrant handles the payload filter as structured data, not raw query strings
points = qdrant_client.query_points(collection_name="embeddings", query_filter=filter_, ...)
```

## Security Checklist

Before production deployment:

- [ ] Qdrant bound to internal network / localhost
- [ ] Optional Qdrant API key configured (`SECONDBRAIN_QDRANT_API_KEY`)
- [ ] SQLite data directory (`~/.secondbrain/`) permissions restricted to owner
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
- **Encryption at rest**: Qdrant and SQLite storage encryption depends on your deployment configuration
