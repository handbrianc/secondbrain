# MongoDB Schema Documentation

This document describes the database schema used by SecondBrain.

## Database Structure

### Database Name
- Default: `secondbrain`
- Configurable via `SECONDBRAIN_MONGO_DB` environment variable

### Collection Name
- Default: `embeddings`
- Configurable via `SECONDBRAIN_MONGO_COLLECTION` environment variable

## Document Structure

Each document in the `embeddings` collection stores a single chunk of text with its embedding vector.

```json
{
  "_id": ObjectId,
  "chunk_id": "uuid-string",
  "source_file": "/path/to/source/document.pdf",
  "page_number": 1,
  "chunk_text": "The actual text content of this chunk...",
  "embedding": [0.123, -0.456, 0.789, ...],
  "metadata": {
    "file_type": "pdf",
    "ingested_at": "2024-03-01T12:00:00+00:00",
    "chunk_index": 0
  },
  "version": 1
}
```

### Field Details

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | ObjectId | Auto-generated | MongoDB internal document ID |
| `chunk_id` | string (UUID) | Yes | Unique identifier for the chunk |
| `source_file` | string | Yes | Path to the source file |
| `page_number` | integer | Yes | Page number in the source document (1-indexed) |
| `chunk_text` | string | Yes | The text content of this chunk |
| `embedding` | float array | Yes | Vector embedding (384 dimensions for all-MiniLM-L6-v2) |
| `metadata.file_type` | string | Yes | Document type (pdf, docx, image, etc.) |
| `metadata.ingested_at` | string (ISO8601) | Yes | Timestamp of ingestion |
| `metadata.chunk_index` | integer | Yes | Original chunk index in the document |
| `version` | integer | Yes | Schema version for migrations |

## Indexes

### Vector Search Index
Named: `embedding_index`

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 384,
      "similarity": "cosine"
    }
  ]
}
```

This index enables efficient cosine similarity search on embedding vectors.

### Regular Indexes
No additional regular indexes are created by default. For query optimization, consider adding indexes on:
- `source_file` - for file-based filtering
- `metadata.file_type` - for file type filtering

## Schema Versioning

### Current Version
- Version: `1`

### Version Field Usage
The `version` field allows for incremental schema evolution. When upgrading the schema:

1. New documents are written with the incremented version number
2. Existing documents retain their original version
3. Migration scripts can process documents by version

### Migration Process
See `../guide/MIGRATIONS.md` for migration procedures.

## Data Types

| Python Type | MongoDB Type | Notes |
|-------------|--------------|-------|
| `str` | String | UUID strings, file paths, text content |
| `int` | Integer | Page numbers, chunk indices |
| `float` | Double | Embedding vector components |
| `datetime` | String | ISO8601 formatted timestamps |

## Constraints

- `embedding` vector must have exactly 384 dimensions (matches all-MiniLM-L6-v2 model)
- `source_file` should be an absolute path for consistent lookups
- `chunk_id` must be unique (UUIDv4 format)

## Query Patterns

### Vector Search
```javascript
db.embeddings.aggregate([
  {
    $vectorSearch: {
      queryVector: [0.1, 0.2, ...],
      path: "embedding",
      numCandidates: 100,
      limit: 5,
      index: "embedding_index"
    }
  },
  { $match: { source_file: { $regex: ".*.pdf" } } }
])
```

### Filter by Source File
```javascript
db.embeddings.find({ source_file: "/path/to/document.pdf" })
```

### List All Chunks
```javascript
db.embeddings.find(
  {},
  { _id: 0, chunk_id: 1, source_file: 1, page_number: 1, chunk_text: 1 }
).skip(0).limit(50)
```

## Storage Estimates

For a typical document:
- Chunk size: ~4096 characters
- Embedding size: 384 floats × 8 bytes = 3072 bytes
- Overhead: ~1KB per document

Estimate: ~1.5KB per chunk × 100,000 chunks = ~150MB

## Backward Compatibility

Breaking changes to the schema should be avoided. When changes are necessary:
1. Increment the `version` field
2. Provide migration scripts
3. Maintain backward-compatible read logic

## Related Documentation

- [Architecture Overview](./index.md) - System architecture
- [Data Flow](./DATA_FLOW.md) - Data flow documentation
- [Development Guide](../developer-guide/development.md) - Development workflow
