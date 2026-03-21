# Security Guidelines

Security best practices for SecondBrain development.

## Secure Coding Practices

### Input Validation

Always validate user input:

```python
from pydantic import BaseModel, Field, validator

class IngestRequest(BaseModel):
    path: str = Field(..., min_length=1)
    chunk_size: int = Field(default=4096, ge=512, le=8192)
    
    @validator("path")
    def validate_path(cls, v):
        # Prevent path traversal
        path = Path(v).resolve()
        if not path.is_absolute():
            raise ValueError("Path must be absolute")
        return str(path)
```

### Error Handling

Don't expose internal details:

```python
try:
    result = process()
except Exception as e:
    logger.error(f"Processing failed: {e}", exc_info=True)
    raise CLIError("Failed to process document")
```

### Secrets Management

Never hardcode secrets:

```python
# Good
from secondbrain.config import Config
config = Config()
mongo_uri = config.mongo_uri  # From environment

# Avoid
mongo_uri = "mongodb://admin:password@localhost:27017"
```

## Dependency Security

### Regular Scans

```bash
# Full security scan (automatically cleans old reports)
./scripts/security_scan.sh all

# Individual security checks
./scripts/security_scan.sh audit    # pip-audit dependency scan
./scripts/security_scan.sh safety   # Safety vulnerability check
./scripts/security_scan.sh bandit   # Code security scan
./scripts/security_scan.sh sbom     # Generate SBOM

# Generate SBOM separately
./scripts/generate-sbom.sh

# Clean up old reports manually
./scripts/cleanup_reports.sh
```

### Report Management

Security and SBOM reports are automatically cleaned before each scan. The cleanup script removes:

- JSON report files (`*report*.json`, `*security*.json`, `*sbom*.json`, etc.)
- Markdown report files (`*report*.md`, `*security*.md`, `*vulnerability*.md`, etc.)
- Old SBOM files (`sbom.json`, `sbom.spdx`)

Reports are generated in:
- `docs/security/` - Security scan reports and analysis
- `site/security/` - Published security documentation

### Update Dependencies

```bash
# Check for updates
pip list --outdated

# Update safely
pip install --upgrade <package>
```

## Configuration Security

### Environment Variables

```bash
# .env (add to .gitignore)
SECONDBRAIN_MONGO_URI=mongodb://user:strong_password@localhost:27017
SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:11434
```

### Secure Defaults

```python
class Config(BaseSettings):
    # Secure by default
    rate_limit_enabled: bool = True
    circuit_breaker_enabled: bool = True
    log_level: str = "INFO"  # Not DEBUG in production
```

## API Security

### Rate Limiting

```python
from secondbrain.utils.circuit_breaker import CircuitBreaker

@CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60
)
async def call_embedding_api(text: str):
    ...
```

### Authentication (Future)

```python
# Plan for API authentication
# JWT tokens, API keys, etc.
```

## Data Security

### Encryption at Rest

MongoDB supports encryption:

```bash
# Enable MongoDB encryption
# Configure in MongoDB settings
```

### Encryption in Transit

```bash
# Use TLS for MongoDB connections
SECONDBRAIN_MONGO_URI=mongodb+srv://user:pass@cluster/?ssl=true
```

## Logging Security

### Don't Log Sensitive Data

```python
# Good
logger.info(f"Processed document: {doc_id}")

# Avoid
logger.info(f"Processed document with URI: {mongo_uri}")
```

### Sanitize Logs

```python
def sanitize_log(message: str) -> str:
    # Remove credentials, tokens, etc.
    return re.sub(r"password=[^&]+", "password=***", message)
```

## Security Checklist

Before release:

- [ ] All inputs validated
- [ ] No hardcoded secrets
- [ ] Error messages sanitized
- [ ] Dependencies scanned
- [ ] Rate limiting enabled
- [ ] Circuit breakers configured
- [ ] Logs don't expose secrets
- [ ] TLS enabled in production
- [ ] Security tests pass

## Incident Response

### If Vulnerability Found

1. **Assess** impact
2. **Disclose** responsibly
3. **Patch** quickly
4. **Document** in changelog
5. **Notify** users if needed

### Reporting

Email: security@secondbrain.local

## Security Tools

| Tool | Purpose | Command |
|------|---------|---------|
| pip-audit | Dependency vulnerabilities | `pip-audit` |
| bandit | Code security | `bandit -r src/` |
| safety | Dependency check | `safety check` |
| cyclonedx | SBOM generation | `cyclonedx-py environment` |

## SBOM & Dependency Analysis

- [SBOM Analysis](../architecture/SBOM_ANALYSIS.md) - Complete dependency inventory
- [License Risk Report](../architecture/LICENSE-RISK-REPORT.md) - License compliance status

## Next Steps

- [Security Guide](../security/index.md) - User security
- [Security Reports](../security/index.md#security-reports) - Latest scan results
- [Configuration](configuration.md) - Secure configuration
