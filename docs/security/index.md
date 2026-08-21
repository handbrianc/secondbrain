# Security Guide

Security considerations for deploying and using SecondBrain.

## Threat Model

### In-Scope Threats

| Threat | Mitigation |
| -------- | ------------ |
| API key exposure | Environment variables, no hardcoding |
| Unauthorized Qdrant access | Authentication (optional `SECONDBRAIN_QDRANT_API_KEY`), network isolation |
| Malicious file ingestion | Input validation, path traversal prevention |
| Service denial | Rate limiting, resource bounds |
| Supply chain attacks | Dependency auditing, SBOM |

### Out-of-Scope

- Physical security of hosting infrastructure
- Social engineering attacks
- Qdrant本身的未加密传输 (unencrypted transit)

## Data Sensitivity

### Local Processing Guarantees

All document processing happens locally:

- **Parsing**: On-host via Docling library
- **Chunking**: Local algorithm with no network calls
- **Embedding generation**: Text chunks sent to external API (if using hosted LLM)
- **RAG chat**: Retrieved chunks sent to LLM API with conversation history

### Data That Leaves Your Machine

| Operation | External Destination | Data Shared |
| ----------- | --------------------- | ------------- |
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

### Qdrant Authentication

Require authentication for production:

```bash
export SECONDBRAIN_QDRANT_URL="http://localhost:6333"
export SECONDBRAIN_QDRANT_API_KEY="strong-random-api-key"  # optional
```

The Qdrant API key is passed as a bearer token on every request. If Qdrant is only reachable on
`localhost`, an API key is optional, but enabling one is recommended when the service is exposed on
a network.

### Conversations (SQLite)

Chat sessions and messages are stored in a local SQLite database file
(`~/.secondbrain/secondbrain.db` by default, configurable via `SECONDBRAIN_SQLITE_PATH`). The file
is embedded and local-only, so it is not exposed over the network. Protect it with filesystem
permissions:

```bash
chmod 600 ~/.secondbrain/secondbrain.db
```

### Least Privilege Principle

Use a dedicated Qdrant API key with the minimum permissions needed for the application. Avoid
sharing root credentials or the same key across unrelated services.

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

Search queries are passed as literals to Qdrant:

```python
# Filter constructed safely - query is opaque string
filter_doc = {"metadata.source": {"$eq": user_provided_filter}}
```

No SQL-like injection risk since Qdrant's HTTP/query protocol handles escaping.

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

## License Compliance

SecondBrain is distributed under the MIT License (see `LICENSE.md`). Its **direct**
dependencies are MIT/Apache-2.0/BSD compatible. However, the resolved dependency tree (see
`sbom.json` / `sbom.spdx`) includes several **transitive** dependencies carrying copyleft
licenses. These cannot be re-licensed and are not generally replaceable without forking or
re-architecting the ingestion/ML stack, so the project documents the following accepted risk:

| Package | License | Component Type | Risk Assessment |
| --------- | ---------- | --------------- | ----------------- |
| `pyinstaller`, `pyinstaller-hooks-contrib` | GPL-2.0-only | Build/packaging tooling | Not distributed with the app; used only in standalone build scripts |
| `paramiko` | LGPL-2.1 | Transitive SSH library | Weak copyleft (LGPL) — linking permitted with obligations; used only as a transitive dep |
| `certifi` | MPL-2.0 | CA bundle (transitive) | File-level weak copyleft; MPL-2.0 is permissive for static use |
| `hypothesis` | MPL-2.0 | Test tooling | Test-only, not shipped in the runtime artifact |
| `pytest-rerunfailures` | MPL-2.0 | Test tooling | Test-only, not shipped in the runtime artifact |

**Accepted-risk rationale:** These components are either (a) build/test-only and never
distributed in the runtime artifact, or (b) weakly-protective (LGPL-2.1, MPL-2.0) libraries
whose copyleft obligations apply to modifications of the library itself rather than to
SecondBrain's MIT code. No strong copyleft (GPL-3.0/AGPL) library is linked into the runtime
application.

**Mitigations:**

- Ensure the distributed package (wheel / container image) includes only runtime
  dependencies, never `pyinstaller`, `hypothesis`, or `pytest-rerunfailures`.
- Review `sbom.spdx` on every release to confirm the copyleft surface has not grown.
- If legal review requires it, replace `paramiko` with a permissively-licensed alternative or
  vendor it under LGPL terms.

## Known Residual Advisories (Accepted Risk)

Regular `pip-audit` / `safety` scans (see [Dependency Auditing](#dependency-auditing)) are
tracked in CI. The **feasible** transitive CVE fixes were applied and locked
(`urllib3>=2.7.0`, `setuptools>=83.0.0`, `idna>=3.18`, `cryptography>=50.0.0`, `pillow>=12.3.0`,
`starlette>=1.0.1`, `pydantic-settings>=2.14.2`). The advisories below remain and are
**documented as accepted risk** because the offending packages are either heavy ML/build
dependencies or transitively pinned by `docling` such that a forced upgrade risks breaking the
document-ingestion pipeline (verified — the upgrade path does not resolve without breaking the
build):

| Package | Advisories (count) | Why held back |
| ---------- | ------------------- | --------------- |
| `gitpython` | 15 | Transitive via docling-git; pin update conflicts with docling's dependency graph |
| `pyasn1` | 4 | Transitive (cryptography-related); fix version conflicts with pinned constraints |
| `nltk`, `aiohttp`, `twisted`, `docling`, `soupsieve`, `joserfc`, `paramiko`, `msgpack`, `h2`, `pymdown-extensions`, `torch` | 4-1 each | Heavy/transitive; forced upgrade is risky or unresolved against the pinned lock |

**Tracking:** These are monitored on every release via the regenerated `sbom.json` / `sbom.spdx`
and the CI security scan. They are not exploitable through the application's HTTP/CLI surface
(void shell injection is disabled; these are dependency-internal advisories).

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
