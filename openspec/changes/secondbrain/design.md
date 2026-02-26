## Context

The secondbrain project is a CLI-only document intelligence tool that:
- Ingests documents using Docling (PDF, DOCX, PPTX, XLSX, HTML, Markdown, etc.)
- Generates embeddings using Ollama with `embeddinggemma:latest` model
- Stores vectors in MongoDB for semantic search
- Provides CLI commands: ingest, search, list, delete

### Current State
- This is a new greenfield project
- No existing codebase
- Docker Compose will manage Ollama and MongoDB containers

### Constraints
- CLI-only application (not a server)
- Single executable build
- Must follow 12-factor app principles
- Minimum 80% test coverage
- 100% security scan compliance
- All linting warnings must be remediated
- Must generate and manage SBOM

### Stakeholders
- Developers using the CLI tool
- DevOps teams deploying via Docker

## Goals / Non-Goals

**Goals:**
- Create a production-ready Python CLI tool using Click
- Support all Docling-supported document types
- Implement semantic search using Ollama embeddings
- Store vectors in MongoDB with proper metadata
- Provide complete Docker Compose setup for local development
- Achieve 80%+ test coverage with all linting/type warnings resolved
- Generate SBOM using SPDX standard

**Non-Goals:**
- HTTP/REST API server (CLI only)
- User authentication/authorization (local tool)
- Web UI or GUI
- Multi-user support
- Cloud deployment (local-first)

## Decisions

### 1. Python CLI Framework: Click
**Decision:** Use Click over argparse or Typer.

**Rationale:**
- Click provides declarative command structure that scales well
- Built-in support for subcommands (ingest, search, list, delete)
- Better testing support via CliRunner
- Industry standard for Python CLI tools (used by Flask, Docker, etc.)

**Alternatives Considered:**
- **argparse**: Too verbose, requires manual subcommand handling
- **Typer**: Based on Typtime, adds complexity, less battle-tested

### 2. Document Processing: Docling
**Decision:** Use Docling for document parsing and text extraction.

**Rationale:**
- Supports all required formats (PDF, DOCX, PPTX, XLSX, HTML, Markdown, etc.)
- Provides consistent output format via DoclingDocument
- Advanced PDF understanding with OCR and table structure
- Active open-source project with good maintenance

**Alternatives Considered:**
- **PyMuPDF (fitz)**: Good for PDF but limited to PDF only
- **python-docx**: Only handles DOCX, would need multiple libraries

### 3. Embeddings: Ollama with embeddinggemma
**Decision:** Use Ollama as the embedding service with embeddinggemma:latest model.

**Rationale:**
- Ollama provides local embedding generation (privacy-friendly)
- embeddinggemma is a high-quality embedding model
- Easy to swap models (nomic-embed-text, etc.) via configuration
- Runs in Docker, consistent across environments (12-factor)

**Alternatives Considered:**
- **OpenAI API**: Requires API key, not local, costs money
- **HuggingFace Transformers**: Requires more setup, no Docker container

### 4. Vector Storage: MongoDB
**Decision:** Use MongoDB with vector search capabilities.

**Rationale:**
- MongoDB 5.0+ supports vector search with $vectorSearch
- Well-established database with excellent Python driver (pymongo)
- Docker container available (12-factor compliant)
- Flexible metadata storage alongside vectors

**Alternatives Considered:**
- **Qdrant**: Good vector DB but adds another dependency
- **Pinecone**: Cloud-only, not local
- **Chroma**: Good but less mature than MongoDB

### 5. Docker Orchestration: Docker Compose
**Decision:** Use Docker Compose to manage Ollama and MongoDB containers.

**Rationale:**
- Single command to start all services
- Environment variable configuration
- Ensures consistent local dev environment (12-factor)
- Easy to add to CI/CD

### 6. Build System: PyInstaller
**Decision:** Use PyInstaller to create single executable.

**Rationale:**
- Produces standalone binary (no Python installation needed)
- Cross-platform support
- Works well with Click-based CLIs

**Alternatives Considered:**
- **cx_Freeze**: Good but less popular
- **py2exe**: Windows only

### 7. Testing: Pytest with Coverage
**Decision:** Use pytest with pytest-cov for coverage measurement.

**Rationale:**
- Industry standard for Python testing
- Easy integration with Click's CliRunner
- Coverage plugin is mature

### 8. Linting: Ruff
**Decision:** Use Ruff for linting and formatting.

**Rationale:**
- 10-100x faster than flake8/isort
- Single tool for both linting and formatting
- Strict configuration for zero warnings
- Built-in mypy integration available

**Alternatives Considered:**
- **flake8 + black + isort**: Multiple tools, slower
- **pylint**: More verbose, slower

## Risks / Trade-offs

### Risk: Ollama Model Availability
**Risk:** The embeddinggemma model may not be available or may require specific pulling.
**Mitigation:** Include model pull in Docker Compose startup, add fallback to nomic-embed-text.

### Risk: MongoDB Vector Search Performance
**Risk:** Vector search on large collections may be slow without proper indexing.
**Mitigation:** Create vector index on ingestion, use approximate nearest neighbor (ANN) index.

### Risk: Large Document Processing
**Risk:** Processing large PDFs may cause memory issues.
**Mitigation:** Implement chunking with configurable size, process in batches.

### Risk: Cross-Platform Executable
**Risk:** PyInstaller executables are platform-specific.
**Mitigation:** Provide build scripts for each target platform (Windows, macOS, Linux).

### Risk: Docling Memory Usage
**Risk:** Docling can be memory-intensive for large documents.
**Mitigation:** Configure chunking, add memory limits in Docker if needed.

## Migration Plan

### Phase 1: Project Setup
- Initialize Python project with pyproject.toml
- Set up virtual environment
- Configure ruff, mypy, pytest

### Phase 2: Core Implementation
- Implement document ingestion (Docling integration)
- Implement embedding generation (Ollama client)
- Implement vector storage (MongoDB client)
- Implement CLI commands (Click)

### Phase 3: Quality Assurance
- Write tests for all modules
- Achieve 80%+ coverage
- Run security scans (bandit, safety)
- Fix all linting/type warnings

### Phase 4: Build & Release
- Create PyInstaller build script
- Generate SBOM
- Create Docker Compose file
- Write README

### Rollback Strategy
- If build fails, revert to last working commit
- If tests fail, do not merge
- If security scan finds issues, do not release until fixed

## Open Questions

1. **Chunking Strategy**: Should we use semantic chunking (by paragraph) or fixed-size chunks?
   - Recommendation: Start with fixed-size (512 chars) with overlap, add semantic later if needed

2. **Embedding Dimensions**: embeddinggemma produces 384-dimensional vectors. Is this sufficient?
   - Yes, this is standard for most use cases

3. **Search Results**: How many results to return by default?
   - Recommendation: Default top-k=5, configurable via CLI flag
