# Proposal: secondbrain CLI Tool

## Why

A local document intelligence tool is needed that allows users to ingest documents, generate embeddings using Ollama with the embeddinggemma model, and store vectors in MongoDB for semantic search. The tool should be a CLI-only application (not a server), following industry best practices including 12-factor app principles, high test coverage, security compliance, and SBOM management.

## What Changes

- Create `secondbrain` CLI tool with the following commands:
  - `ingest` - Ingest documents into the vector database
  - `search` - Perform semantic search on ingested content
  - `list` - List ingested documents/chunks
  - `delete` - Delete documents from the vector database
- Support all document types supported by Docling:
  - PDF (with OCR and table structure support)
  - DOCX (Word documents)
  - PPTX (PowerPoint presentations)
  - XLSX (Excel spreadsheets)
  - HTML/XHTML
  - Markdown
  - AsciiDoc
  - LaTeX
  - CSV
  - Images (PNG, JPEG, TIFF, BMP, WEBP)
  - Audio (WAV, MP3)
  - WebVTT (video text tracks)
  - XML (USPTO patents, JATS XML for scientific articles)
  - Docling JSON
- Use Ollama with `embeddinggemma:latest` for generating embeddings
- Use MongoDB for vector storage
- Docker Compose to manage Ollama and MongoDB containers
- Single executable CLI build (no server required)
- Follow 12-factor app principles
- Maintain >= 80% test coverage
- 100% security scan compliance (all severities)
- Generate and maintain SBOM (Software Bill of Materials)
- Include comprehensive README documentation

## Capabilities

### New Capabilities

- **document-ingestion**: Parse and process documents using Docling, chunk content, generate embeddings via Ollama, and store in MongoDB
- **embedding-generation**: Use embeddinggemma:latest model via Ollama API to generate semantic embeddings
- **vector-storage**: Store embeddings in MongoDB with metadata (source file, page number, chunk text)
- **semantic-search**: Perform cosine similarity search on stored embeddings
- **document-management**: List and delete ingested documents/chunks from the database

### Modified Capabilities

- None at this time (new project)

## Impact

### Codebase

- Python CLI application using Click framework
- Docling for document parsing
- Ollama client for embeddings
- PyMongo or mongoflake for MongoDB connection
- Dockerfile for single executable build
- Docker Compose for container orchestration

### Dependencies

- **Python**: 3.11+
- **Docling**: Document parsing
- **Ollama**: Embedding generation (embeddinggemma:latest)
- **MongoDB**: Vector storage
- **PyTest**: Testing framework
- **Coverage**: Test coverage measurement
- **Bandit**: Security scanning
- **Safety/Snyk**: SBOM generation

### External Systems

- Ollama Docker container (embeddinggemma:latest)
- MongoDB Docker container (with vector search support)

### Technical Requirements (12-Factor Compliance)

1. **Codebase**: Single git repository, tracked in version control
2. **Dependencies**: Explicitly declare and isolate all dependencies in requirements.txt/pyproject.toml
3. **Config**: Store configuration in environment variables (MongoDB URI, Ollama URL, etc.)
4. **Backing Services**: Treat MongoDB and Ollama as attached resources via URLs
5. **Build/Release/Run**: Separate build (compile to executable) from release (bundle with config)
6. **Processes**: Stateless CLI - no in-memory state between invocations
7. **Port Binding**: Not applicable (CLI tool, not web server)
8. **Concurrency**: CLI tool - process-based for batch operations
9. **Disposability**: Fast startup and shutdown - CLI commands execute quickly
10. **Dev/Prod Parity**: Docker containers ensure consistent environments
11. **Logs**: Log to stdout, use structured logging for CLI output
12. **Admin Processes**: Built-in CLI commands for management tasks
12. **Admin Processes**: Built-in CLI commands for management tasks

### Code Quality Requirements

- **Linting**: Use ruff for linting with strict configuration
- **Formatting**: Use ruff formatter for consistent code style
- **Type Checking**: Use mypy with strict mode enabled
- **Warning Remediation**: All warnings must be remediated - no warnings allowed in:
  - Linting (ruff)
  - Type checking (mypy)
  - Testing (pytest warnings)
  - Security scans (bandit, safety)
- **Pre-commit Hooks**: Enforce linting, formatting, and type checking before commits
### Quality Requirements

- **Test Coverage**: Minimum 80% code coverage
- **Security**: 100% compliance - zero vulnerabilities allowed (any severity)
- **SBOM**: Generate and maintain Software Bill of Materials using SPDX standard
- **Build**: Single executable using PyInstaller or similar

### Docker Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   secondbrain  │     │     MongoDB    │
│   CLI Tool      │────▶│  (vector store)│
│                 │     │                 │
└─────────────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│     Ollama      │
│ (embeddinggemma) │
└─────────────────┘
```

## Implementation Notes

### CLI Commands Design

```bash
# Ingest documents
secondbrain ingest /path/to/docs/
secondbrain ingest --recursive /path/to/docs/

# Semantic search
secondbrain search "query text"
secondbrain search "query text" --top-k 5

# List content
secondbrain list
secondbrain list --source file.pdf
secondbrain list --chunk-id <id>

# Delete content
secondbrain delete --source file.pdf
secondbrain delete --chunk-id <id>
secondbrain delete --all
```

### Configuration (Environment Variables)

- `SECONDBRAIN_MONGO_URI`: MongoDB connection string (default: mongodb://localhost:27017)
- `SECONDBRAIN_MONGO_DB`: Database name (default: secondbrain)
- `SECONDBRAIN_MONGO_COLLECTION`: Collection name (default: embeddings)
- `SECONDBRAIN_OLLAMA_URL`: Ollama API URL (default: http://localhost:11434)
- `SECONDBRAIN_MODEL`: Embedding model (default: embeddinggemma:latest)
- `SECONDBRAIN_CHUNK_SIZE`: Chunk size for document splitting (default: 512)
- `SECONDBRAIN_CHUNK_OVERLAP`: Chunk overlap for splitting (default: 50)

### Embedding Storage Schema

```json
{
  "chunk_id": "uuid",
  "source_file": "document.pdf",
  "page_number": 1,
  "chunk_text": "extracted text content...",
  "embedding": [0.1, 0.2, ...],
  "metadata": {
    "file_type": "pdf",
    "ingested_at": "2024-01-01T00:00:00Z",
    "chunk_index": 0
  }
}
```
