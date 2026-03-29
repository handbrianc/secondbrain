# Changelog

All notable changes to SecondBrain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of SecondBrain v0.4.0
- Semantic search with sentence transformers
- Document ingestion via Docling
- MongoDB vector storage with Motor async support
- MCP server integration for AI assistants
- Rich terminal output
- Batch processing support
- GPU acceleration for embeddings
- Custom chunking configuration
- Export functionality (JSON format)
- OpenTelemetry tracing support
- Circuit breaker pattern for resilience
- Property-based testing with Hypothesis
- Security scanning with Bandit, Safety, and pip-audit
- SBOM generation with CycloneDX
- Docker support for deployment

### Changed
- Upgraded to Docling 2.81.0 for improved document parsing
- Enhanced async API for better performance
- Improved error handling and context messages
- Updated type checking configuration

### Fixed
- Memory leak in batch ingestion
- Type errors in MongoDB operations
- Race conditions in async processing
- Security vulnerabilities in dependencies

### Security
- Added security scanning to pre-commit hooks
- Implemented circuit breaker for external calls
- Enhanced credential management
- Regular dependency updates with safety checks

## [0.4.0] - 2026-03-28

### Added
- Full async/await API support
- MCP server for AI assistant integration
- OpenTelemetry instrumentation
- Circuit breaker pattern implementation
- Property-based testing with Hypothesis
- Comprehensive security scanning
- SBOM generation capabilities
- Docker deployment support

### Changed
- Migrated to Docling 2.81.0
- Enhanced type safety across codebase
- Improved error messages with context
- Optimized vector search performance

### Fixed
- Memory leaks in batch processing
- Type errors in MongoDB async operations
- Race conditions in concurrent ingestion
- Security vulnerabilities in transitive dependencies

## [0.3.0] - 2026-03-20

### Added
- Basic semantic search functionality
- Document ingestion pipeline
- MongoDB vector storage
- CLI interface with Click
- Rich terminal output

### Changed
- Improved embedding model configuration
- Enhanced configuration management

### Fixed
- Initial bug fixes and stability improvements

## [0.2.0] - 2026-03-15

### Added
- Pre-commit hooks configuration
- CI/CD pipeline setup
- Comprehensive test suite

### Changed
- Refactored core architecture
- Improved code quality metrics

## [0.1.0] - 2026-03-10

### Added
- Initial project structure
- Basic document ingestion
- Simple search functionality

---

[Unreleased]: https://github.com/your-org/secondbrain/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/your-org/secondbrain/releases/tag/v0.4.0
[0.3.0]: https://github.com/your-org/secondbrain/releases/tag/v0.3.0
[0.2.0]: https://github.com/your-org/secondbrain/releases/tag/v0.2.0
[0.1.0]: https://github.com/your-org/secondbrain/releases/tag/v0.1.0
