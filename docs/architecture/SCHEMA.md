# Schema Reference

Qdrant payload and SQLite schemas for SecondBrain.

## Vector Collection: `embeddings`

Stores all ingested document chunks with their vector representations as Qdrant points. The default collection name is `embeddings`, configured via `SECONDBRAIN_QDRANT_COLLECTION`.

### Point Schema

Each chunk is a Qdrant point: a vector plus a payload. All chunk metadata lives in the payload so search needs one round trip.

```json
{
  "id": 18446744073709551616,
  "vector": [0.123, -0.456, 0.789, ...],
  "payload": {
    "chunk_id": "46ec0cd0-9a3e-4c5a-9c4a-0a5a0f43b7a2",
    "source_file": "/path/to/document.pdf",
    "page_number": 3,
    "chunk_text": "Extracted chunk text content...",
    "element_type": "body",
    "chunk_role": "body",
    "section_label": "Introduction",
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

### Field Types Summary

| Field | Stored In | Type | Constraints |
| ------- | ---------- | ------ | ------------- |
| `id` | Point ID | Unsigned int | Qdrant auto-assigned |
| `vector` | Point vector | float32[] | Length equals EMBEDDING_DIMENSIONS |
| `chunk_id` | Payload | String | UUID v4 format |
| `source_file` | Payload | String | Valid file path |
| `page_number` | Payload | Integer | Positive |
| `chunk_text` | Payload | String | UTF-8 |
| `element_type` | Payload | String \| null | Enum values (see below) |
| `chunk_role` | Payload | String \| null | Legacy role |
| `section_label` | Payload | String \| null | Section heading/context |

## element_type

Structural role of a chunk within its parent document. Introduced in v2.x (structural enhancement).

**Type**: `string | null`

**Values**:

| Value | Description |
| ------- | ------------- |
| `"navigation"` | Navigation elements (menus, breadcrumbs, TOC buttons) |
| `"heading"` | Section headings and titles |
| `"toc_entry"` | Table of contents entries |
| `"caption"` | Captions for figures, tables, images |
| `"body"` | Body text paragraphs |
| `"table_row"` | Table cell content |
| `"table_caption"` | Caption within or beneath a table |

**Note**: `chunk_role` is retained in the payload for backwards compatibility with documents ingested prior to v2.x. New documents set `element_type`.

## Conversations: SQLite

Conversation history for the chat command is persisted to SQLite (`ConversationStorage` at `src/secondbrain/conversation/storage_sqlite.py`). The default database path is `~/.secondbrain/secondbrain.db`, configured via `SECONDBRAIN_SQLITE_PATH`.

### `sessions` Table

| Column | Type | Constraints |
| ------- | ------- | ------------- |
| `session_id` | TEXT | Primary key |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC |

### `messages` Table

| Column | Type | Constraints |
| ------- | ------- | ------------- |
| `id` | INTEGER | Primary key, auto-increment |
| `session_id` | TEXT | Foreign key to `sessions` |
| `role` | TEXT | `user` or `assistant` |
| `content` | TEXT | Message text |
| `timestamp` | DATETIME | UTC |
| `sources` | TEXT | JSON-serialized source citations (chunk_id, source, page, score) |

## Vector Index

Qdrant builds a vector index on the `embeddings` collection automatically from the point vector dimension and distance metric:

- **Distance metric**: Cosine similarity
- **Dimensions**: Match EMBEDDING_DIMENSIONS (default 1536)

Payload fields are indexed for metadata filtering (for example, `source_file`, `page_number`, `element_type`, `section_label`).

## Storage Calculations

### Vector Storage Per Document

Given default EMBEDDING_DIMENSIONS=1536 and float32 (4 bytes):

```
Bytes per vector = 1536 × 4 = 6,144 bytes (~6 KB)

Plus overhead:
- chunk_text: varies by chunk size (4096 chars = ~4 KB)
- payload metadata: ~200 bytes
- Qdrant per-point overhead

Total estimate per chunk: ~11-12 KB
```

### Compression Savings

With STORAGE_COMPRESSION_ENABLED=true (zstd):

| Compression | Text Reduction | Vector Reduction |
| ------------- | --------------- | ------------------ |
| None | 0% | N/A |
| gzip | 60-80% | ~20% |
| brotli | 65-85% | ~25% |
| zstd | 60-80% | ~20% |

## Migration Notes

### Vector Format Change (v0.3 → v0.4)

Previously vectors were stored as BSON Binary in MongoDB. Now stored as plain float arrays in Qdrant points during the MongoDB→Qdrant migration.

Migration is manual: re-ingest affected documents.

### Index Recreation After Schema Change

Some index changes require recreation:

```bash
# Drop and recreate a collection after a schema change
qdrant_client.recreate_collection(...)
```
