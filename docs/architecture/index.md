# Architecture Documentation

Technical architecture and system design for SecondBrain.

## Overview

This section provides deep technical documentation for developers and architects:

| Document | Description |
|----------|-------------|
| [Data Flow](DATA_FLOW.md) | System architecture and data pipelines |
| [Schema Reference](SCHEMA.md) | Database structure and models |
| [SBOM Analysis](SBOM_ANALYSIS.md) | Software Bill of Materials & dependency analysis |
| [License Risk Report](LICENSE-RISK-REPORT.md) | License compliance & risk assessment |

## System Components

### Core Components

1. **CLI Interface** - Click-based command-line tool
2. **Document Ingestor** - Multi-format document processing
3. **Embedding Engine** - sentence-transformers integration for vector generation
4. **Storage Layer** - MongoDB vector storage
5. **Search Engine** - Semantic search with cosine similarity

### Data Flow

```
Documents → Ingestor → Chunking → Embeddings → MongoDB → Search
```

See [Data Flow Documentation](DATA_FLOW.md) for detailed diagrams.

## Database Schema

SecondBrain uses MongoDB for vector storage:

- **embeddings** collection - Document chunks and vectors
- Indexes on: `document_id`, `file_type`, `chunk_index`

See [Schema Reference](SCHEMA.md) for complete schema details.

## Design Decisions

### Why MongoDB?

- Native vector search capabilities
- Scalable and production-ready
- Flexible schema for document metadata
- Easy deployment via Docker

### Why sentence-transformers?

- Local embedding generation (privacy)
- No API costs
- Support for multiple embedding models
- Easy setup and maintenance

## Performance Characteristics

### Vector Search Complexity

The `build_search_pipeline()` function performs ** brute-force cosine similarity** over all document vectors. This has important implications:

| Metric | Value |
|--------|-------|
| **Time Complexity** | O(n·d) where n = documents, d = embedding dimensions |
| **Space Complexity** | O(1) additional space per query |
| **Scaling Behavior** | Linear in corpus size |

#### Recommendations

- **Recommended for**: Corpora < 100,000 documents
- **Acceptable for**: Medium workloads with modest hardware
- **Not recommended for**: Large-scale production with millions of documents

#### Migration Path for Scale

For larger workloads, consider:
1. **MongoDB Atlas Search** (paid tier) — native $vectorSearch operator with HNSW indexes
2. **External vector database** — Qdrant, Weaviate, Pinecone, Milvus

### General Performance Tips

- **Batch Processing**: Process documents in parallel
- **Connection Caching**: Reduce connection overhead
- **Rate Limiting**: Protect sentence-transformers API
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
- [API Reference](../api/index.md) - Code-level documentation
- [Getting Started](../getting-started/index.md) - New users
- [Async API Guide](../developer-guide/async-api.md) - Asynchronous programming
