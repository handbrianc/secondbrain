# SecondBrain - Local Document Intelligence CLI

A privacy-first document intelligence CLI that ingests documents, generates embeddings, and provides semantic search over your documents using MongoDB and OpenAI-compatible embedding services.

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Why SecondBrain?

- **Privacy-First**: All document parsing, chunking, and storage happen locally
- **Multi-Format Support**: PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio
- **Fast & Scalable**: Multicore ingestion, async API, and optimized vector search
- **Semantic Search**: Natural language queries with relevance ranking
- **Production-Ready**: Circuit breaker, rate limiting, structured logging, and OpenTelemetry tracing

## Prerequisites

- Python 3.11+
- MongoDB (local or Docker)
- Docker (optional, for containerized setup)

## Quick Start

```bash
# 1. Install SecondBrain
pip install -e .

# 2. Start MongoDB
secondbrain start --wait

# 3. Ingest your first documents
secondbrain ingest ./documents/

# 4. Search semantically
secondbrain search "what is this about?"
```

## CLI Commands

```bash
# Ingest documents (required - positional arg is PATH)
secondbrain ingest ./documents/                  # single file
secondbrain ingest ./documents/ --recursive      # entire directory tree
secondbrain ingest ./documents/ --cores 4        # parallel with 4 CPU cores
secondbrain ingest ./documents/ --batch-size 20  # batch size for sequential processing

# Search the vector database (positional arg is QUERY)
secondbrain search "machine learning best practices"
secondbrain search "what is this about" --top-k 10
secondbrain search "intro" --file-type pdf --min-score 0.5

# List ingested documents
secondbrain ls                          # list first 100 documents
secondbrain ls --all                    # list all (up to MAX_LIST_LIMIT)
secondbrain ls --source "./report.pdf"  # filter by source file

# Delete documents
secondbrain delete --source "./report.pdf"   # delete by source
secondbrain delete --chunk-id <id>           # delete specific chunk
secondbrain delete --all                      # delete everything
secondbrain delete --all --yes                # skip confirmation

# Show database statistics
secondbrain status

# Check service health
secondbrain health
secondbrain health --output json

# Show performance metrics
secondbrain metrics                        # view all collected metrics
secondbrain metrics --reset               # reset all metrics

# Conversational Q&A with your documents
secondbrain chat "What is the main topic?"         # single query
secondbrain chat                                  # interactive REPL mode
secondbrain chat --session my-chat                # resume named session
secondbrain chat --list-sessions                  # list all sessions
secondbrain chat --history --session my-chat      # show session history
secondbrain chat --delete-session my-chat         # delete a session

# Manage the Docker stack
secondbrain start                   # start MongoDB via docker-compose
secondbrain start --wait            # wait for services to be fully ready
secondbrain start -f custom.yml     # use specific compose file

secondbrain stop                    # stop the docker-compose stack
secondbrain stop --remove-volumes   # also remove data volumes
```

Run `secondbrain --help` for the full command reference.

## Configuration

SecondBrain uses environment variables prefixed with `SECONDBRAIN_`:

```bash
# Required: MongoDB connection
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=embeddings

# Embedding provider
SECONDBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECONDBRAIN_EMBEDDING_BASE_URL=https://api.openai.com/v1
SECONDBRAIN_API_KEY=your-api-key

# Document processing
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=200

# Performance
SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true

# Logging
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=pretty
```

See `docs/getting-started/configuration.md` for the full configuration reference.

## Supported File Types

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF | `.pdf` | Text and tables extracted |
| Word | `.docx` | Full text extraction |
| PowerPoint | `.pptx` | Slide text and content |
| Excel | `.xlsx` | Tabular data |
| Images | `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp` | OCR with Docling |
| Audio | `.mp3`, `.wav`, `.m4a` | Transcription |
| HTML | `.html`, `.htm` | Web page content |
| Markdown | `.md` | Plain text |
| Plain Text | `.txt` | UTF-8 text |

## Architecture

```
Documents → Ingestor → Chunker → Embedder → MongoDB Vector Store
                              ↓
Search Query ← Searcher ← Embedder ← Query
```

Key components:
- **Document Ingestor** (`secondbrain ingest`) - parses and chunks supported file types
- **Embedding Engine** - OpenAI-compatible API for vector generation
- **Vector Storage** - MongoDB vector search with `$vectorSearch` for similarity retrieval
- **Chat** (`secondbrain chat`) - RAG pipeline for conversational Q&A

## Documentation

- [Getting Started](docs/getting-started/index.md) - Installation, setup, and first steps
- [User Guide](docs/user-guide/index.md) - Complete usage guide
- [CLI Reference](docs/user-guide/cli-reference.md) - All commands and options
- [Configuration](docs/getting-started/configuration.md) - Full configuration reference
- [Developer Guide](docs/developer-guide/index.md) - Dev setup and contributing
- [Architecture](docs/architecture/index.md) - System design

## License

MIT License - see [LICENSE](LICENSE.md).