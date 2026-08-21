# Migrations Guide

Schema migration procedures for SecondBrain.

## Overview

SecondBrain stores data in two places: vector data in **Qdrant** (collection `embeddings`, default) and conversations
in **SQLite** (default path `~/.secondbrain/secondbrain.db`). Migrations handle:

- Payload schema changes in the `embeddings` Qdrant collection
- Collection / index configuration changes
- SQLite schema changes for conversations
- Data transformations for new features

## Migration Philosophy

- **Forward-only migrations**: Old data remains readable with current code
- **Backward compatibility**: Previous versions may not read new schemas
- **Idempotent operations**: Re-running a migration should be safe

## Current Schema Version

As of version 0.4.0, the current Qdrant payload includes:

```json
{
  "chunk_id": "uuid-string",
  "source_file": "/path/to/document.pdf",
  "page_number": 3,
  "chunk_text": "Extracted chunk text content...",
  "element_type": "body",
  "chunk_role": "body",
  "section_label": "Introduction"
}
```

Qdrant collection configuration:

- Collection: `embeddings` (default)
- Vector size: EMBEDDING_DIMENSIONS (default 1536)
- Distance: Cosine

SQLite (conversations):

- `sessions` table (session_id, created_at, updated_at)
- `messages` table (id, session_id, role, content, timestamp, sources)

## Common Migrations

### Adding a New Payload Field

New payload fields can be added without recreating the collection; points written after the change carry the field:

```python
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")
# Upsert points with the new payload field
client.upsert(collection_name="embeddings", points=[...])
```

### Recreating a Collection After a Payload/Schema Change

Some changes (for example, a new vector dimension) require recreating the collection:

```python
client.recreate_collection(
    collection_name="embeddings",
    vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
)
```

## Performing Migrations

### Re-ingesting Documents

Because chunk vectors and payloads are written by the ingestion pipeline, the primary migration path is to re-ingest
affected documents:

```bash
# Delete affected documents
secondbrain delete --source "/path/to/document.pdf"

# Re-ingest with the new schema
secondbrain ingest "/path/to/document.pdf"
```

### Programmatic Migration

For automated deployments:

```python
from qdrant_client import QdrantClient

def migrate_add_source_hash():
    """Add computed hash to payload for deduplication."""
    client = QdrantClient(url="http://localhost:6333")

    # Scroll points and rewrite payloads with the new field
    points, _ = client.scroll(collection_name="embeddings", limit=100)
    for point in points:
        point.payload["content_hash"] = compute_hash(point.payload["chunk_text"])
        client.set_payload(
            collection_name="embeddings",
            payload=point.payload,
            points=[point.id],
        )

    client.close()
```

## Rollback Procedures

### Restoring Payload Fields

When payload fields were only added (not removed), rollback just means stopping the write of the new field. For data
loss scenarios, restore from backup before re-ingesting.

Cannot automatically restore deleted payload fields. Ensure backups exist before irreversible operations.

## Pre-Migration Checklist

Before applying migrations:

- [ ] Back up vector data (Qdrant snapshot or point export)
- [ ] Back up the SQLite database (`cp ~/.secondbrain/secondbrain.db backup.db`)
- [ ] Review migration steps in staging environment
- [ ] Schedule maintenance window for large datasets
- [ ] Notify users of potential downtime
- [ ] Have rollback plan ready

## Post-Migration Verification

After migration:

1. Verify application still works:

```bash
secondbrain status
secondbrain search "test query"
```

1. Check for errors in logs

2. Confirm expected performance characteristics

3. Monitor error tracking for new migration-related bugs

## Historical Note: MongoDB → Qdrant + SQLite

MongoDB has been fully removed from SecondBrain. The app previously stored vectors and documents in MongoDB (using
`$vectorSearch`) and later migrated to **Qdrant for vector storage** and **SQLite for conversation sessions**. The
Mongo backends, `config/mongo.py` (MongoMixin), and the `pymongo`/`motor`/`bson` dependencies were deleted.

At the time of the migration, development setup used an `init-mongo` script; that is no longer needed. Development now
starts the Qdrant service:

```bash
secondbrain start --wait   # starts the secondbrain-qdrant container
```
