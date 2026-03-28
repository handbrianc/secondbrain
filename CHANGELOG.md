# Changelog

All notable changes to SecondBrain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Property-based testing with Hypothesis for query sanitization and config validation
- Comprehensive security scanning with Bandit, Safety, and pip-audit
- SBOM generation with CycloneDX
- Circuit breaker pattern for resilience
- Rate limiting for service protection
- OpenTelemetry tracing support
- MCP (Model Context Protocol) server integration
- Conversational Q&A with session management

### Changed
- Upgraded all security-critical dependencies to latest patched versions
- Improved error handling with proper logging in exception handlers
- Enhanced test coverage with edge case testing

### Fixed
- CLI batch size validation tests using proper temporary directories
- Silent exception handling in embedding generation (Bandit B112)
- Missing pytest-timeout dependency in development environment

## [0.4.0] - 2026-03-27

### Added
- Async document ingestion API
- Multi-format document support (PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, audio)
- Smart chunking with configurable sizes and overlap
- Multicore processing for parallel ingestion
- Semantic search with cosine similarity
- Conversational chat with local LLMs (Ollama)
- Session persistence for multi-turn conversations
- Health checks for service connectivity
- Status and metrics commands
- JSON output format for all commands
- Progress indicators for long-running operations

### Changed
- Migrated to PEP 621 compliant pyproject.toml
- Improved type annotations with mypy strict mode
- Enhanced documentation with 40+ markdown files
- Reorganized CLI into modular structure

### Fixed
- Memory efficiency with streaming chunk processing
- Connection pooling for MongoDB
- Embedding cache for performance optimization

## [0.3.0] - 2026-02-15

### Added
- Initial document ingestion with sentence-transformers
- MongoDB vector storage
- Basic semantic search
- Click-based CLI
- Docker Compose setup

### Changed
- Improved error messages
- Better logging configuration

## [0.2.0] - 2026-01-20

### Added
- Document converter with Docling
- Chunking strategies
- Basic testing infrastructure

## [0.1.0] - 2026-01-01

### Added
- Project scaffolding
- Basic configuration system
- Development setup guidelines

[Unreleased]: https://github.com/your-username/secondbrain/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/your-username/secondbrain/releases/tag/v0.4.0
[0.3.0]: https://github.com/your-username/secondbrain/releases/tag/v0.3.0
[0.2.0]: https://github.com/your-username/secondbrain/releases/tag/v0.2.0
[0.1.0]: https://github.com/your-username/secondbrain/releases/tag/v0.1.0
