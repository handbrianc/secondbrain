# Schema Reference

MongoDB document schemas and index definitions for SecondBrain.

## Primary Collection: `embeddings`

Stores all ingested document chunks with their vector representations.

### Document Schema

```javascript
{
  "_id": ObjectId,           // MongoDB auto-assigned ID

  // Primary identifiers
  "chunk_id": "uuid-string", // Stable UUID for deduplication

  // Position within source
  "chunk_index": 0,          // Sequence number in source document

  // Content (compressed if text_compression_enabled)
  "text": "Extracted chunk text content...",
  "text_compressed": false,  // Boolean flag
  "compression_algo": null,  // "gzip" | "brotli" | "zstd" if compressed

  // Vector representation (always stored as array, not Binary)
  "vector": [0.123, -0.456, 0.789, ...],  // float32[]
  "vector_dtype": "float32",               // "float32" or "float64"

  // Timestamp
  "created_at": ISODate("2024-01-15T10:30:00Z"),

  // Metadata
  "metadata": {
    "source": "/path/to/document.pdf",  // Absolute file path
    "page": 3,                           // 1-based page number
    "file_type": "pdf",                  // Extension without dot
    "size": 1048576,                     // Original file size in bytes

    // Optional fields
    "checksum": "sha256:abc123...",     // If computed
    "language": "en"                      // Detected language
  }
}
```

### Field Types Summary

| Field | Type | Constraints |
|-------|------|-------------|
| `_id` | ObjectId | Auto-generated, unique |
| `chunk_id` | String | UUID v4 format |
| `chunk_index` | Integer | Non-negative |
| `text` | String | UTF-8 |
| `text_compressed` | Boolean | Default false |
| `vector` | Array | Length equals EMBEDDING_DIMENSIONS |
| `vector_dtype` | String | "float32" or "float64" |
| `created_at` | Date | UTC |
| `metadata.source` | String | Valid file path |
| `metadata.page` | Integer | Positive |
| `metadata.file_type` | String | Normalized extension |
| `metadata.size` | Integer | Bytes |

## Sessions Collection: `sessions`

Stores conversation history for the chat command.

### Document Schema

```javascript
{
  "_id": ObjectId,

  "session_id": "user-specified-id or uuid",
  "messages": [
    {
      "role": "user",
      "content": "What is the capital of France?",
      "timestamp": ISODate("2024-01-15T10:30:00Z")
    },
    {
      "role": "assistant",
      "content": "The capital of France is Paris.",
      "timestamp": ISODate("2024-01-15T10:30:05Z"),
      "sources": [
        {
          "chunk_id": "...",
          "source": "/path/to/doc.pdf",
          "page": 42,
          "score": 0.89
        }
      ]
    }
  ],

  "created_at": ISODate("2024-01-15T10:30:00Z"),
  "updated_at": ISODate("2024-01-15T10:30:05Z")
}
```

## Index Definitions

### Primary Vector Index

Optimizes similarity search operations:

```javascript
db.embeddings.createIndex(
  { "vector": "cosineSimilarity" },  // or "euclidean" or "dotProduct"
  {
    name: "vector_index",
    numDimensions: 1536,        // Must match EMBEDDING_DIMENSIONS
    replace: false              // Fail if exists with different specs
  }
)
```

Alternative for older MongoDB versions:

```javascript
db.embeddings.createIndex(
  { "vector": "2dsphere" },
  {
    name: "vector_index_legacy",
    numSubTrees: 100
  }
)
```

### Secondary Indexes

Speed up metadata filtering:

```javascript
// Source file lookup (common filter)
db.embeddings.createIndex(
  { "metadata.source": 1 },
  { name: "idx_source", background: true }
)

// Compound index for document-ordered retrieval
db.embeddings.createIndex(
  { "metadata.source": 1, "chunk_index": 1 },
  { name: "idx_source_chunk", unique: true, background: true }
)

// File type filtering
db.embeddings.createIndex(
  { "metadata.file_type": 1 },
  { name: "idx_file_type", background: true }
)

// Creation time for retention policies
db.embeddings.createIndex(
  { "created_at": 1 },
  { name: "idx_created", expireAfterSeconds: null, background: true }
)
```

### Session Indexes

```javascript
// Session lookup by ID
db.sessions.createIndex(
  { "session_id": 1 },
  { name: "idx_session_id", unique: true }
)

// Recent sessions for listing
db.sessions.createIndex(
  { "updated_at": -1 },
  { name: "idx_recent" }
)
```

## Storage Calculations

### Vector Storage Per Document

Given default EMBEDDING_DIMENSIONS=1536 and float32 (4 bytes):

```
Bytes per vector = 1536 × 4 = 6,144 bytes (~6 KB)

Plus overhead:
- text field: varies by chunk size (4096 chars = ~4 KB)
- metadata: ~200 bytes
- MongoDB document overhead: ~200 bytes

Total estimate per chunk: ~11-12 KB
```

### Compression Savings

With STORAGE_COMPRESSION_ENABLED=true (zstd):

| Compression | Text Reduction | Vector Reduction |
|-------------|---------------|------------------|
| None | 0% | N/A |
| gzip | 60-80% | ~20% |
| brotli | 65-85% | ~25% |
| zstd | 60-80% | ~20% |

## Migration Notes

### Adding text_compressed Field

```javascript
// Version 0.4.0 adds compression capability
db.embeddings.updateMany(
  { "text_compressed": { "$exists": false } },
  { "$set": { "text_compressed": false } }
)
```

### Vector Format Change (v0.3 → v0.4)

Previously vectors were stored as BSON Binary. Now stored as JSON arrays for compatibility with newer MongoDB versions and vector search.

Migration is manual: re-ingest affected documents.

### Index Recreation After Schema Change

Some index changes require recreation:

```javascript
// Drop old index
db.embeddings.dropIndex("old_index_name")

// Create new with corrected specification
db.embeddings.createIndex(...)
```