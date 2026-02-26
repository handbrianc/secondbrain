## 1. Project Setup

- [ ] 1.1 Initialize Python project with pyproject.toml
- [ ] 1.2 Set up virtual environment and dependencies
- [ ] 1.3 Configure ruff (linting + formatting) with strict rules
- [ ] 1.4 Configure mypy with strict mode
- [ ] 1.5 Configure pytest with coverage
- [ ] 1.6 Set up pre-commit hooks
- [ ] 1.7 Run initial lint/type check and fix all warnings

## 2. Docker Infrastructure

- [ ] 2.1 Create Dockerfile for single executable build
- [ ] 2.2 Create docker-compose.yml with Ollama and MongoDB
- [ ] 2.3 Configure environment variables in compose file
- [ ] 2.4 Test Docker Compose startup
- [ ] 2.5 Verify Ollama embeddinggemma model availability

## 3. Core Modules

- [ ] 3.1 Create project structure (src/secondbrain/)
- [ ] 3.2 Implement config module (environment variables)
- [ ] 3.3 Implement logging module
- [ ] 3.4 Implement CLI entry point with Click

## 4. Document Ingestion

- [ ] 4.1 Integrate Docling DocumentConverter
- [ ] 4.2 Implement file discovery (recursive option)
- [ ] 4.3 Implement file type detection
- [ ] 4.4 Implement text extraction from documents
- [ ] 4.5 Implement text chunking (configurable size/overlap)
- [ ] 4.6 Implement batch processing with progress
- [ ] 4.7 Add error handling per file
- [ ] 4.8 Write tests for document ingestion module

## 5. Embedding Generation

- [ ] 5.1 Integrate Ollama client
- [ ] 5.2 Implement embedding generation for text
- [ ] 5.3 Add model pull on first use
- [ ] 5.4 Implement connection validation
- [ ] 5.5 Handle Ollama service unavailable
- [ ] 5.6 Write tests for embedding module

## 6. Vector Storage

- [ ] 6.1 Integrate PyMongo client
- [ ] 6.2 Implement MongoDB connection with env config
- [ ] 6.3 Create vector index for cosine similarity
- [ ] 6.4 Implement embedding storage with metadata
- [ ] 6.5 Implement bulk insert for efficiency
- [ ] 6.6 Write tests for storage module

## 7. Semantic Search

- [ ] 7.1 Implement search command
- [ ] 7.2 Generate query embedding via Ollama
- [ ] 7.3 Perform cosine similarity search in MongoDB
- [ ] 7.4 Add result formatting (default, verbose, JSON)
- [ ] 7.5 Add filter options (--source, --file-type)
- [ ] 7.6 Write tests for search module

## 8. Document Management

- [ ] 8.1 Implement list command (all, by source, by chunk-id)
- [ ] 8.2 Implement delete command (by source, by chunk-id, all)
- [ ] 8.3 Add pagination support for list
- [ ] 8.4 Add confirmation for destructive operations
- [ ] 8.5 Implement status command (statistics)
- [ ] 8.6 Write tests for management module

## 9. Quality Assurance

- [ ] 9.1 Run full test suite
- [ ] 9.2 Achieve 80%+ code coverage
- [ ] 9.3 Run security scans (bandit, safety)
- [ ] 9.4 Remediate all warnings (lint, type, test)
- [ ] 9.5 Fix any security vulnerabilities

## 10. Build & Release

- [ ] 10.1 Create PyInstaller build script
- [ ] 10.2 Build single executable
- [ ] 10.3 Generate SBOM using SPDX
- [ ] 10.4 Write comprehensive README
- [ ] 10.5 Create project documentation (code standards)

## 11. Documentation

- [ ] 11.1 Write README with installation and usage
- [ ] 11.2 Document CLI commands
- [ ] 11.3 Document configuration (environment variables)
- [ ] 11.4 Document Docker setup
- [ ] 11.5 Document development setup
