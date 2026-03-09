# Architecture Documentation

Technical architecture and system design for SecondBrain.

## Overview

This section provides deep technical documentation for developers and architects:

- [Data Flow](./DATA_FLOW.md) - System architecture and data pipelines
- [Schema Reference](./SCHEMA.md) - Database structure

## System Components

### Core Components

1. **CLI Interface** - Click-based command-line tool
2. **Document Ingestor** - Multi-format document processing
3. **Embedding Engine** - Ollama integration for vector generation
4. **Storage Layer** - MongoDB vector storage
5. **Search Engine** - Semantic search with cosine similarity

### Data Flow

```
Documents → Ingestor → Chunking → Embeddings → MongoDB → Search
```

See [Data Flow Documentation](./DATA_FLOW.md) for detailed diagrams.

## Database Schema

SecondBrain uses MongoDB for vector storage:

- **embeddings** collection - Document chunks and vectors
- Indexes on: `document_id`, `file_type`, `chunk_index`

See [Schema Reference](./SCHEMA.md) for complete schema details.

## Design Decisions

### Why MongoDB?

- Native vector search capabilities
- Scalable and production-ready
- Flexible schema for document metadata
- Easy deployment via Docker

### Why Ollama?

- Local embedding generation (privacy)
- No API costs
- Support for multiple embedding models
- Easy setup and maintenance

## Performance Considerations

- **Batch Processing**: Process documents in parallel
- **Connection Caching**: Reduce connection overhead
- **Rate Limiting**: Protect Ollama API
- **Chunk Optimization**: Adjust chunk size for your use case

See [Building & Performance](../developer-guide/building.md) for optimization tips.

## Security

- Environment-based configuration
- Input validation and sanitization
- Rate limiting protection
- Connection health checks

See [Security Guide](../developer-guide/security.md) for details.

## Related Documentation

- [Developer Guide](../developer-guide/index.md) - Development workflows
- [API Reference](../api-reference/index.md) - Code-level documentation
- [Getting Started](../getting-started/index.md) - New users
- [Async API Guide](../developer-guide/async-api.md) - Asynchronous programming
