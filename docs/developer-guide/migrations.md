# Migrations Guide

Database migration procedures for SecondBrain.

## Overview

SecondBrain stores all data in MongoDB. Migrations handle:

- Schema changes to the `embeddings` collection
- Index modifications
- Data transformations for new features

## Migration Philosophy

- **Forward-only migrations**: Old data remains readable with current code
- **Backward compatibility**: Previous versions may not read new schemas
- **Atomic operations**: Each migration is idempotent where possible

## Current Schema Version

As of version 0.4.0, the current schema includes:

```javascript
{
  "_id": ObjectId,
  "chunk_id": String,          // UUID
  "chunk_index": Integer,
  "text": String,              // May be compressed
  "vector": Array[Float],      // Embedding vector
  "metadata": {
    "source": String,          // File path
    "page": Integer,
    "file_type": String,       // Extension
    "created_at": DateTime,
    "size": Integer
  }
}
```

Indexes:

- `vector` field with `2dsphere` or `knnBeta` index type
- Compound indexes on `(metadata.source, chunk_index)`

## Common Migrations

### Adding a New Index

```javascript
// Migration: add_file_type_index.js
db.embeddings.createIndex(
  { "metadata.file_type": 1 },
  { name: "file_type_idx", background: true }
)
```

### Renaming a Field

From MongoDB shell:

```javascript
db.embeddings.updateMany(
  {},
  { $rename: { "old_field": "new_field" } }
)
```

### Dropping Deprecated Fields

```javascript
db.embeddings.updateMany(
  {},
  { $unset: { "legacy_field": "" } }
)
```

## Performing Migrations

### Manual Migration

1. Export current data:

```bash
mongodump --uri="$SECONDBRAIN_MONGO_URI" --archive=dump.archive
```

2. Run migration (mongosh):

```javascript
// Apply changes
db.embeddings.createIndex(...)
db.embeddings.updateMany(..., {$rename: {...}})
```

3. Verify migration:

```javascript
db.embeddings.getIndexes()
// Confirm new indexes present

db.embeddings.findOne()
// Confirm expected document structure
```

### Programmatic Migration

For automated deployments:

```python
async def migrate_add_source_hash():
    """Add computed hash for deduplication."""
    from pymongo import MongoClient
    
    client = MongoClient(os.getenv("SECONDBRAIN_MONGO_URI"))
    db = client[os.getenv("SECONDBRAIN_MONGO_DB")]
    collection = db[os.getenv("SECONDBRAIN_MONGO_COLLECTION")]
    
    # Add hash field
    cursor = collection.find({"content_hash": {"$exists": False}})
    for doc in cursor:
        doc["content_hash"] = compute_hash(doc["text"])
        collection.replace_one({"_id": doc["_id"]}, doc)
    
    client.close()

if __name__ == "__main__":
    migrate_add_source_hash()
```

## Rollback Procedures

### Index Removal

```javascript
// Non-essential index only
db.embeddings.dropIndex("temporary_idx")
```

### Field Restoration

Cannot automatically restore renamed/deleted fields from MongoDB. Ensure backups exist before irreversible operations.

## Pre-Migration Checklist

Before applying migrations:

- [ ] Backup database: `mongodump --archive=backup.archive`
- [ ] Review migration scripts in staging environment
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

2. Check for errors in logs

3. Confirm expected performance characteristics

4. Monitor error tracking for new migration-related bugs

## Version Compatibility Matrix

| Version | Schema Version | Compatible |
|---------|---------------|------------|
| 0.3.x | v1 | Read/write |
| 0.4.0 | v2 | Read/write |
| Future | v3 | Write only |

Schemas are additive (fields added) in minor versions. Major versions may introduce breaking changes.