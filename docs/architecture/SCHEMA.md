# Database Schema Reference

MongoDB schema structure for SecondBrain.

## Collections

### `embeddings`

Main collection storing document chunks and their vector embeddings.

#### Document Structure

```json
{
  "_id": ObjectId("..."),
  "document_id": "uuid-v4-string",
  "chunk_index": 0,
  "content": "Text content of this chunk...",
  "embedding": [0.123, -0.456, 0.789, ...],
  "metadata": {
    "filename": "document.pdf",
    "file_type": "pdf",
    "source_path": "/absolute/path/to/document.pdf",
    "file_size": 45678,
    "ingested_at": "2024-01-15T10:30:00Z",
    "chunk_size": 4096,
    "model_used": "all-MiniLM-L6-v2"
  }
}
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | ObjectId | Yes | MongoDB auto-generated ID |
| `document_id` | string | Yes | UUID identifying source document |
| `chunk_index` | int | Yes | Zero-based index within document |
| `content` | string | Yes | Text content of the chunk |
| `embedding` | array[float] | Yes | Vector embedding (384 or 768 dims) |
| `metadata.filename` | string | Yes | Original file name |
| `metadata.file_type` | string | Yes | File extension (pdf, md, etc.) |
| `metadata.source_path` | string | Yes | Absolute path to source file |
| `metadata.file_size` | int | No | File size in bytes |
| `metadata.ingested_at` | datetime | Yes | ISO 8601 timestamp |
| `metadata.chunk_size` | int | No | Chunk size used for this chunk |
| `metadata.model_used` | string | No | Embedding model identifier |

#### Indexes

```javascript
// Compound index for document queries
db.embeddings.createIndex({ document_id: 1, chunk_index: 1 })

// Index for file type filtering
db.embeddings.createIndex({ "metadata.file_type": 1 })

// Index for ingestion date
db.embeddings.createIndex({ "metadata.ingested_at": -1 })

// Text index for keyword search (fallback)
db.embeddings.createIndex({ content: "text" })
```

## Query Examples

### Find All Chunks for a Document

```javascript
db.embeddings.find({
  document_id: "uuid-v4-string"
}).sort({ chunk_index: 1 })
```

### Search by File Type

```javascript
db.embeddings.find({
  "metadata.file_type": "pdf"
})
```

### Find Recent Documents

```javascript
db.embeddings.find({
  "metadata.ingested_at": {
    $gte: new Date("2024-01-01")
  }
}).sort({ "metadata.ingested_at": -1 })
```

### Vector Similarity Search

```javascript
// Using MongoDB vector search (7.0+)
db.embeddings.aggregate([
  {
    $vectorSearch: {
      queryVector: [0.123, -0.456, ...],
      path: "embedding",
      numCandidates: 100,
      limit: 10
    }
  }
])
```

## Data Lifecycle

### Ingestion

1. Generate UUID for document
2. Split document into chunks
3. Generate embeddings for each chunk
4. Insert all chunks with same `document_id`

### Deletion

```javascript
// Delete all chunks for a document
db.embeddings.deleteMany({
  document_id: "uuid-v4-string"
})
```

### Update

```javascript
// Re-ingest document (delete + insert)
db.embeddings.deleteMany({ document_id: "uuid" })
// Then insert new chunks
```

## Size Estimates

### Per-Chunk Storage

- **Content**: ~2KB average
- **Embedding**: 1.5KB (384 dims × 4 bytes)
- **Metadata**: ~500 bytes
- **MongoDB overhead**: ~1KB

**Total**: ~5KB per chunk

### Database Size

```
100 documents × 10 chunks × 5KB = 5MB
1,000 documents × 10 chunks × 5KB = 50MB
10,000 documents × 10 chunks × 5KB = 500MB
```

## Backup & Restore

### Backup

```bash
mongodump --db secondbrain --out ./backup/
```

### Restore

```bash
mongorestore --db secondbrain ./backup/secondbrain/
```

## Migration Notes

### Schema Versioning

Current schema version: 1.0

Future migrations may include:
- Additional metadata fields
- Optimized index structures
- Partitioning strategies

## Best Practices

1. **Use UUIDs** for `document_id` to avoid conflicts
2. **Index frequently queried fields**
3. **Monitor collection size** for performance
4. **Regular backups** before bulk operations
5. **Use projection** to limit returned fields
