# Architecture Overview

This document provides an overview of SecondBrain's system architecture.

## System Components

### Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SecondBrain CLI                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Ingestor │  │ Embedder │  │  Search  │  │  Storage │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │              │             │          │
│       └─────────────┴──────────────┴─────────────┘          │
│                           │                                  │
│                    ┌──────▼──────┐                          │
│                    │   MongoDB   │                          │
│                    │  (Vectors)  │                          │
│                    └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### Component Descriptions

#### Document Ingestor
- **Purpose**: Parse and process documents
- **Technology**: Docling for document parsing
- **Features**: 
  - Multi-format support (PDF, DOCX, TXT)
  - Custom chunking strategies
  - Batch processing
  - Progress tracking

#### Embedding Engine
- **Purpose**: Generate vector embeddings
- **Technology**: Sentence Transformers
- **Features**:
  - Multiple model support
  - GPU acceleration
  - Batch encoding
  - Caching

#### Vector Storage
- **Purpose**: Store and retrieve embeddings
- **Technology**: MongoDB with Motor async driver
- **Features**:
  - Vector similarity search
  - Metadata filtering
  - Async operations
  - Connection pooling

#### Search Engine
- **Purpose**: Semantic search and retrieval
- **Technology**: MongoDB vector search
- **Features**:
  - Cosine similarity
  - Top-K results
  - Metadata filtering
  - Result ranking

### Data Flow

1. **Ingestion**: Document → Parser → Chunker → Embedder → Storage
2. **Search**: Query → Embedder → Vector Search → Results
3. **RAG**: Query → Search → Context → LLM → Response

## Technology Stack

### Core Dependencies
- **Python**: 3.11+
- **Click**: CLI framework
- **Pydantic**: Data validation
- **Rich**: Terminal UI

### Document Processing
- **Docling**: Document parsing and conversion
- **Sentence Transformers**: Text embeddings
- **Torch**: Deep learning framework

### Storage & Sync
- **MongoDB**: Vector database
- **Motor**: Async MongoDB driver
- **httpx**: Async HTTP client

### Observability
- **OpenTelemetry**: Distributed tracing
- **Pytest**: Testing framework
- **Ruff**: Code quality

## Deployment Architecture

### Local Deployment
```
┌─────────────────────┐
│   SecondBrain CLI   │
│  + MongoDB (local)  │
└─────────────────────┘
```

### Remote Deployment
```
┌─────────────────────┐      ┌─────────────────────┐
│   SecondBrain CLI   │──────│  MongoDB Atlas      │
└─────────────────────┘      └─────────────────────┘
```

### Docker Deployment
```
┌─────────────────────┐      ┌─────────────────────┐
│   SecondBrain CLI   │──────│  MongoDB Container  │
│   (Docker)          │      │  (Docker)           │
└─────────────────────┘      └─────────────────────┘
```

## Security Architecture

- **Local-first**: All processing happens locally
- **Encryption**: MongoDB TLS/SSL support
- **Authentication**: MongoDB authentication required
- **Input Validation**: Pydantic strict validation
- **Dependency Scanning**: Automated security checks

## Performance Considerations

### Embedding Generation
- GPU acceleration for faster encoding
- Batch processing for multiple documents
- Model caching to reduce load times

### Vector Search
- MongoDB vector index optimization
- Connection pooling for database access
- Async operations for non-blocking I/O

### Memory Management
- Streaming document processing
- Chunk-based embedding generation
- Garbage collection optimization

## Extensibility

### Plugin System
- Custom embedding models
- Custom storage backends
- Custom document parsers

### API Extensions
- Python SDK for programmatic access
- MCP server for AI assistants
- REST API (future)

## See Also

- [Data Flow](DATA_FLOW.md) - Detailed data flow analysis
- [Schema](SCHEMA.md) - Database schema details
- [SBOM Analysis](SBOM_ANALYSIS.md) - Dependency analysis
