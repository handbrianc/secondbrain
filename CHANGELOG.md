# Changelog

All notable changes to SecondBrain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-19

### Added

#### Resilience & Reliability
- **Circuit Breaker Pattern**: Automatic service failure handling for MongoDB and sentence-transformers
  - Configurable failure and success thresholds
  - Automatic recovery with half-open state
  - Prevents cascade failures during service outages
  - See `examples/circuit_breaker_usage.py` for usage

- **Enhanced Error Handling**: 
  - CircuitBreakerError exception for open circuit state
  - Graceful degradation with fallback strategies
  - Retry logic with exponential backoff support

#### Testing
- **Chaos Testing Suite** (`tests/test_chaos/`):
  - Service failure scenarios (MongoDB, sentence-transformers)
  - Network partition simulation and recovery
  - Circuit breaker response testing
  - Graceful degradation validation

- **Concurrency Testing Suite** (`tests/test_concurrency/`):
  - Concurrent ingestion race condition detection
  - Concurrent search under load
  - Thread safety validation
  - Batch operation concurrency

#### Security
- **Security Scanning Infrastructure**:
  - `scripts/security_scan.sh` for comprehensive security checks
  - pip-audit integration for dependency vulnerability detection
  - cyclonedx SBOM generation for supply chain security
  - pre-commit hook for cyclonedx-bom

- **Documentation**:
  - `requirements-dev.txt` with pinned versions
  - SBOM generation and scanning procedures

#### Documentation
- **Migration Guide** (`docs/migration.md`):
  - Version upgrade instructions
  - Breaking changes documentation
  - Migration checklist
  - Rollback procedures

- **Troubleshooting Guide** (`docs/getting-started/troubleshooting.md`):
  - Common installation issues
  - Runtime error resolution
  - Performance optimization tips
  - Security scanning issues

- **Examples** (`examples/`):
  - `circuit_breaker_usage.py` - Circuit breaker patterns
  - `async_ingestion_example.py` - Async API usage
  - `tracing_example.py` - OpenTelemetry integration

### Changed

- Updated README.md with new features (circuit breaker, async API, structured logging)
- Enhanced development dependencies with pip-audit
- Added cyclonedx pre-commit hook for SBOM generation

### Security

- Added pip-audit to dev dependencies
- Integrated cyclonedx-bom for SBOM generation
- Created security scanning workflow

### Development

- Added chaos and concurrency test suites
- Enhanced test coverage for resilience patterns
- Updated pre-commit configuration

---

## [0.2.0] - 2025-12-01

### Added

- **Async API**: Full asynchronous document ingestion and search
  - `AsyncDocumentStorage` for non-blocking operations
  - `AsyncEmbeddingGenerator` for async embedding generation
  - See `docs/developer-guide/async-api.md` for details

- **Multicore Processing**: Parallel document ingestion
  - Configurable CPU core count via `--cores` flag
  - Environment variable `SECONDBRAIN_MAX_WORKERS`
  - Significant performance improvements for large document sets

- **Rate Limiting**: Protection for sentence-transformers API
  - Automatic request throttling
  - Configurable rate limits

### Changed

- Improved error messages with more context
- Enhanced logging with timestamps and structured format

### Fixed

- Fixed MongoDB connection recovery issues
- Improved handling of duplicate documents

---

## [0.1.0] - 2024-06-15

### Added

- Initial release
- Multi-format document ingestion (PDF, DOCX, PPTX, XLSX, HTML, Markdown)
- Semantic search with sentence-transformers embeddings
- MongoDB vector storage
- CLI interface with Click
- Basic health checks
- Docker Compose setup for local development

### Features

- Document ingestion with chunking
- Vector embedding generation
- Cosine similarity search
- Document listing and deletion
- Database statistics

[0.3.0]: https://github.com/your-org/secondbrain/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/your-org/secondbrain/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/your-org/secondbrain/releases/tag/v0.1.0
