# Security Guide

Security considerations for deploying and using SecondBrain.

## Threat Model

### In-Scope Threats

| Threat | Mitigation |
|--------|------------|
| API key exposure | Environment variables, no hardcoding |
| Unauthorized MongoDB access | Authentication, network isolation |
| Malicious file ingestion | Input validation, path traversal prevention |
| Service denial | Rate limiting, resource bounds |
| Supply chain attacks | Dependency auditing, SBOM |

### Out-of-Scope

- Physical security of hosting infrastructure
- Social engineering attacks
- MongoDB本身的未加密传输 (unencrypted transit) |

## Data Sensitivity

### Local Processing Guarantees

All document processing happens locally:

- **Parsing**: On-host via Docling library
- **Chunking**: Local algorithm with no network calls
- **Embedding generation**: Text chunks sent to external API (if using hosted LLM)
- **RAG chat**: Retrieved chunks sent to LLM API with conversation history

### Data That Leaves Your Machine

| Operation | External Destination | Data Shared |
|-----------|---------------------|-------------|
| Embedding (OpenAI-compatible) | Your configured API endpoint | Text chunks for vectorization |
| Embedding (local Ollama) | localhost only | No external transmission |
| LLM Chat (OpenAI/Anthropic) | Respective API | Retrieved chunks + conversation |
| Telemetry (if enabled) | Your OTLP collector | Structured logs/traces |

## Secure Configuration

### API Keys

**Strong recommendation**: Use environment variables:

```bash
export SECONDBRAIN_EMBEDDING_API_KEY="sk-..."
```

**Acceptable**: `.env` file with restrictive permissions:

```bash
chmod 600 .env  # User read/write only
```

**Forbidden**: Committing credentials to version control:

```bash
# .gitignore should include
.env
*.log
```

### MongoDB Authentication

Require authentication for production:

```bash
mongodb://user:password@host:27017/?authSource=admin
```

Use TLS for remote connections:

```bash
mongodb+srv://user:password@cluster.mongodb.net/?tls=true
```

### Least Privilege Principle

Create dedicated MongoDB users:

```javascript
// Read-write user for application
db.createUser({
  user: "secondbrain_app",
  pwd: "strong-random-password",
  roles: [
    { role: "readWrite", db: "secondbrain" },
    { role: "dbAdmin", db: "secondbrain" }
  ]
})
```

Avoid using MongoDB's `root` account.

## Input Validation

### File Type Restrictions

Only documented file types are accepted:

```python
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx",
    ".html", ".htm", ".md", ".txt",
    ".csv", ".xml", ".json", ".png",
    ".jpg", ".jpeg", ".tiff", ".tif",
    ".bmp", ".webp", ".wav", ".mp3", ".vtt"
}
```

Attempting to ingest unsupported types raises `ValueError` immediately.

### Path Traversal Prevention

Paths are resolved canonically before processing:

```python
from pathlib import Path

resolved_path = Path(user_input_path).resolve()

# Verify within allowed directory tree
if not is_safe_path(resolved_path, allowed_base):
    raise ValueError("Path traversal attempt detected")
```

### Query Sanitization

Search queries are passed as literals to MongoDB:

```python
# Filter constructed safely - query is opaque string
filter_doc = {"metadata.source": {"$eq": user_provided_filter}}
```

No SQL-like injection risk since MongoDB wire protocol handles escaping.

## Rate Limiting

Protection against API quota exhaustion:

```bash
# Configure rate limiter
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS=10  # per window
SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS=1.0
```

Monitor rate limit events in application logs.

## File Size Limits

Prevents memory exhaustion from huge documents:

```bash
SECONDBRAIN_MAX_FILE_SIZE_BYTES=104857600  # 100 MB default
```

Attempts to process oversized files are rejected immediately.

## Dependency Auditing

### Regular Checks

```bash
# Install audit tooling
pip install -e ".[security]"

# Check for vulnerabilities
safety check

# Scan code for security issues
bandit -r src/secondbrain/

# Generate SBOM for supply chain review
cyclonedx-bom -o sbom.json
```

### CI/CD Integration

Automate security scanning:

```yaml
# GitHub Actions example
- name: Security audit
  run: |
    pip install safety bandit
    safety check || true
    bandit -r src/ --failxit || true
```

## Docker Security

### Non-Root Containers

Run application containers as non-root where possible:

```yaml
# docker-compose.yml
services:
  secondbrain-app:
    image: secondbrain:0.4.0
    user: "1000:1000"
```

### Capability Dropping

Minimal Linux capabilities:

```bash
docker run --cap-drop=ALL secondbrain
```

### Read-Only Root Filesystem

Unless write access is needed:

```yaml
services:
  app:
    read_only: true
    tmpfs:
      - /tmp
```

## Monitoring and Alerting

### Suspicious Activity Patterns

Alert on:

- High volume of authentication failures
- Unusual query patterns (potential probe)
- Resource exhaustion (memory, CPU spikes)
- Rate limit violations trending upward

### Logging

Structured logging for forensics:

```bash
SECONDBRAIN_LOG_FORMAT=json
SECONDBRAIN_LOG_LEVEL=INFO
```

Logs do not contain document content by default.

## Incident Response

If a security incident is suspected:

1. **Immediate containment**
   - Rotate exposed API keys
   - Revoke compromised credentials
   - Isolate affected services

2. **Assessment**
   - Review access logs for unauthorized use
   - Identify accessed documents
   - Determine blast radius

3. **Recovery**
   - Redeploy with patched configuration
   - Monitor for recurrence

4. **Reporting**
   - Document timeline
   - File security advisory if a library vulnerability

## Disclosure Policy

For security vulnerabilities in SecondBrain itself:

1. Report privately via GitHub Security Advisories
2. Allow 30 days for fix development
3. Coordinate disclosure on fix availability