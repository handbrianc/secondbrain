# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Progress indicators for batch document processing operations
- Embedding cache to reduce redundant sentence-transformers API calls
- Shell completion scripts for bash, zsh, and fish
- Prometheus metrics export for monitoring performance and cache hit rates

### Changed
- Consolidated duplicate `build_search_pipeline()` function into single source
- Enhanced MongoDB connection pooling configuration
- Improved error messages with additional context

### Fixed
- Connection timeout handling in async operations
- Cache invalidation edge cases

### Security
- Enhanced input validation for search queries
- Improved path traversal protection

## [0.1.0] - 2026-03-05

### Added
- Initial release of SecondBrain CLI
- Multi-format document ingestion (PDF, DOCX, PPTX, XLSX, HTML, Markdown, etc.)
- Semantic search using sentence-transformers embeddings with `embeddinggemma:latest` model
- MongoDB-backed vector storage with cosine similarity search
- Full async support for embedding generation and storage operations
- Rate limiting for sentence-transformers API protection
- Connection caching with configurable TTL
- Rich terminal output with formatted tables and progress
- Health check endpoint for service availability monitoring
- Command-line interface with intuitive commands:
  - `ingest` - Add documents to the vector database
  - `search` - Perform semantic search queries
  - `list` - List ingested documents/chunks
  - `delete` - Remove documents from the database
  - `status` - Display database statistics
  - `health` - Check service health status
- Comprehensive test suite with 90%+ coverage
- Type-safe configuration using Pydantic Settings
- Environment-driven configuration (12-factor app)
- Pre-commit hooks for code quality
- Security scanning with Bandit and Safety
- Docker Compose setup for MongoDB and sentence-transformers services

### Changed
- Initial implementation with production-ready architecture
- Strict type checking with mypy
- Comprehensive error handling with specific exception types
- Document chunking with configurable size and overlap
- Duplicate detection using text hashing

### Security
- Input sanitization for search queries
- Path traversal prevention
- File size limits (100MB maximum)
- Validation for MongoDB URI and sentence-transformers URL formats

### Documentation
- Comprehensive README with installation and usage instructions
- Code standards documentation (./code-standards.md)
- Contribution guidelines (./contributing.md)
- Security policy (./security.md)
- Data schema documentation (../architecture/SCHEMA.md)
- Migration guide (./migrations.md)

## Related Documentation

- [Development Guide](./development.md) - Development workflow
- [Contributing](./contributing.md) - How to contribute
