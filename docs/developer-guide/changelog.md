# Changelog

All notable changes to SecondBrain.

## [0.3.0] - 2024-01-15

### Added

- Circuit breaker pattern for service resilience
- Async API for high-throughput scenarios
- Chaos testing suite
- Security scanning integration (pip-audit, cyclonedx)
- Structured JSON logging with OpenTelemetry support
- Multicore document ingestion
- Comprehensive test coverage

### Changed

- Improved error messages
- Enhanced rate limiting
- Better progress indicators

### Fixed

- Memory leak in embedding cache
- Connection timeout handling
- Unicode encoding issues

## [0.2.0] - 2023-12-01

### Added

- Async embedding generation
- Circuit breaker for MongoDB and sentence-transformers
- Multicore document ingestion
- Test performance optimization guide

### Changed

- Improved chunking algorithm
- Better default configuration

### Fixed

- MongoDB connection pooling issues
- Embedding cache invalidation

## [0.1.0] - 2023-11-01

### Added

- Initial release
- Document ingestion (PDF, DOCX, PPTX, XLSX, HTML, Markdown)
- Semantic search with MongoDB vector search
- CLI with Click
- Basic configuration management
- Docker support

---

## Version Format

Following [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

## Changelog Guidelines

When contributing:

1. Add entry to appropriate section
2. Use clear, concise descriptions
3. Link to related issues/PRs
4. Follow existing format

## Previous Versions

See Git history for older versions.
