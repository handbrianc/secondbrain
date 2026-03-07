# Changelog

All notable changes to SecondBrain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-02

### Added
- Multi-format document ingestion (PDF, DOCX, PPTX, XLSX, HTML, Markdown, etc.)
- Semantic embeddings using Ollama with embeddinggemma model
- MongoDB-backed vector storage with cosine similarity search
- CLI-first design with rich terminal output
- Async support for embeddings and storage operations
- Rate limiting and connection caching
- Comprehensive test suite

### Changed
- Removed default MongoDB credentials in docker-compose.yml

### Fixed
- Added timeouts to all HTTP calls
- Instance-level rate limiters
- URI validation for MongoDB and Ollama
- Specific exception handling instead of bare except clauses

## Template for Future Releases

### [Unreleased]

### Added
- 

### Changed
- 

### Fixed
- 

### Deprecated
- 

### Removed
- 

### Security
- 
