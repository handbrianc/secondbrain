# ADR-002: MongoDB for Vector Storage

**Status**: Accepted  
**Created**: 2026-03-30  
**Authors**: SecondBrain Team  
**Deciders**: Architecture Team

## Context

SecondBrain requires a vector database to store document embeddings for semantic search. The solution must:

- Support vector similarity search (cosine similarity, dot product)
- Handle large document collections (10,000+ documents)
- Provide async/await support for high-performance CLI operations
- Maintain all data locally for privacy
- Scale efficiently as document count grows
- Support metadata filtering alongside vector search

## Decision

**Choose MongoDB with the vector search capability** for the following reasons:

### Technical Justification

1. **Native Vector Search**: MongoDB 6.0+ includes native vector search with `$vectorSearch` aggregation stage, supporting:
   - Cosine similarity, dot product, and Euclidean distance
   - Hybrid search (vector + keyword)
   - Metadata filtering with vector queries

2. **Async Support**: Motor library provides full async/await support, essential for:
   - Non-blocking CLI operations
   - Concurrent document ingestion
   - High-performance search queries

3. **Local Deployment**: MongoDB can run locally via Docker or standalone, ensuring:
   - All data stays on user's machine
   - No cloud dependencies
   - Full control over data

4. **Schema Flexibility**: MongoDB's document model accommodates:
   - Variable-length embeddings
   - Rich metadata structures
   - Nested document data

5. **Performance**: Benchmarks show MongoDB vector search performs comparably to specialized vector databases for datasets <1M vectors:
   - ~10-50ms query latency for 10K documents
   - ~50-100ms query latency for 100K documents

### Implementation Details

```python
# Collection structure
{
  "_id": ObjectId,
  "document_id": str,           # Unique document identifier
  "content": str,               # Text content/chunk
  "embedding": [float],         # Vector embeddings (384-1536 dimensions)
  "metadata": {                 # Additional metadata
    "source": str,
    "file_type": str,
    "timestamp": datetime,
    "custom_fields": dict
  },
  "collection": str,            # User-defined collection name
  "embedding_model": str        # Model used for embeddings
}
```

**Index Configuration**:
```python
from pymongo import ASCENDING, DESCENDING
from pymongo.operations import SearchIndex

# Vector search index
vector_index = {
  "name": "vector_search",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      {
        "type": "vector",
        "numDimensions": 384,  # Configurable based on embedding model
        "similarity": "cosine",
        "path": "embedding"
      },
      {
        "type": "filter",
        "path": "collection"
      },
      {
        "type": "filter", 
        "path": "metadata.source"
      }
    ]
  }
}
```

## Consequences

### Positive

- **Single Database**: No need for separate vector database + document store
- **Local-First**: Fully supports privacy requirements
- **Async-Native**: Motor integration provides non-blocking operations
- **Metadata Filtering**: Can filter by collection, source, date, etc.
- **Operational Simplicity**: One technology stack to maintain

### Negative

- **Vector Size Limit**: MongoDB has a 16MB document limit (not an issue for typical embeddings <10KB)
- **Limited Index Types**: Only supports HNSW for vector search (not IVF-PQ)
- **Memory Requirements**: Vector indexes are memory-intensive (~1GB per 100K vectors)

### Risks

- **MongoDB Version**: Requires MongoDB 6.0+ for vector search
- **Resource Usage**: Vector search can be memory-intensive
- **Not Specialized**: May not match performance of dedicated vector DBs at massive scale (>1M vectors)

## Alternatives Considered

### 1. ChromaDB
**Pros**: Purpose-built for embeddings, simple API, local-first  
**Cons**: Limited metadata filtering, smaller ecosystem, less mature async support

### 2. Qdrant
**Pros**: High-performance vector search, excellent filtering, gRPC support  
**Cons**: Separate service required, more operational overhead, steeper learning curve

### 3. Pinecone/Weaviate Cloud
**Pros**: Managed service, excellent performance  
**Cons**: Cloud-only (violates privacy requirement), ongoing costs

### 4. PostgreSQL + pgvector
**Pros**: ACID compliance, familiar SQL, good ecosystem  
**Cons**: Slower vector search than MongoDB, more complex setup for async

## References

- [MongoDB Vector Search Documentation](https://www.mongodb.com/docs/atlas/atlas-vector-search/)
- [Motor Async MongoDB Driver](https://motor.readthedocs.io/)
- [ADR-001: CLI Consolidation](./ADR-001-cli-consolidation.md)
- Performance benchmarks in `docs/performance-testing.md`
