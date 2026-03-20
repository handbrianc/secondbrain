# Migration Guide

This guide provides migration instructions for upgrading SecondBrain across major versions.

## Version 0.2.0 → 0.3.0

### New Features in 0.3.0

This release adds extensive resilience, security, and documentation improvements:

- **Circuit Breaker Pattern**: Automatic service failure handling with MongoDB and sentence-transformers
- **Async API**: Full asynchronous document ingestion and search
- **Chaos Testing**: Comprehensive chaos and concurrency test suites
- **Security Scanning**: Integrated pip-audit, cyclonedx SBOM generation
- **Enhanced Logging**: Structured JSON logging with OpenTelemetry tracing

### Breaking Changes

**None** - This release maintains full backward compatibility with the existing API.

### Migration Steps

#### 1. Update Dependencies

```bash
pip install -e ".[dev]"
```

Or with pinned versions:

```bash
pip install -r requirements-dev.txt
```

#### 2. Enable Circuit Breaker (Optional)

Circuit breaker is enabled by default. To customize thresholds:

```python
from secondbrain.utils.circuit_breaker import CircuitBreakerConfig

# Custom configuration
config = CircuitBreakerConfig(
    failure_threshold=10,      # Failures before opening circuit
    success_threshold=5,       # Successes before closing circuit
    recovery_timeout=60.0,     # Seconds before half-open state
    half_open_max_calls=10     # Max calls in half-open state
)
```

#### 3. Migrate to Async API (Optional)

The sync API remains fully supported. To use async:

```python
import asyncio
from secondbrain.storage.async_storage import AsyncDocumentStorage

async def main():
    storage = AsyncDocumentStorage()
    
    # Async ingestion
    await storage.ingest_document(
        doc_id="doc-1",
        content="Document content",
        metadata={"source": "test"}
    )
    
    # Async search
    results = await storage.search(
        query_embedding=[0.1] * 768,
        top_k=5
    )

asyncio.run(main())
```

#### 4. Configure Security Scanning

Run initial security scan:

```bash
./scripts/security_scan.sh all
```

Generate SBOM:

```bash
./scripts/security_scan.sh sbom
```

#### 5. Enable Structured Logging

Set environment variable:

```bash
export SECONDBRAIN_LOG_FORMAT=json
```

## Version 0.1.0 → 0.2.0

### Breaking Changes

None. This was an additive release.

### New Features

- Async embedding generation
- Circuit breaker for service resilience
- Multicore document ingestion
- Comprehensive test coverage

## Migration Checklist

Before upgrading:

- [ ] Review changelog for breaking changes
- [ ] Backup MongoDB database
- [ ] Test in staging environment
- [ ] Verify MongoDB compatibility (8.0+)
- [ ] Ensure Python version (3.11+)

After upgrading:

- [ ] Run `secondbrain health` to verify services
- [ ] Run security scan: `./scripts/security_scan.sh all`
- [ ] Run tests: `pytest -m "not slow"`
- [ ] Verify document ingestion works
- [ ] Verify search functionality

## Rollback Procedure

If you need to rollback:

```bash
# Install previous version
pip install secondbrain==0.2.0

# Restore database from backup if needed
mongorestore --uri="mongodb://localhost:27017" backup_directory/
```

## Support

For migration issues:
1. Check troubleshooting guide: [troubleshooting.md](getting-started/troubleshooting.md)
2. Review logs: `secondbrain health --verbose`
3. Open an issue with migration details
