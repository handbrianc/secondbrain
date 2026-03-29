# Migrations Guide

Database migration guide for SecondBrain.

## Overview

SecondBrain provides migration tools for schema updates and data transformations.

## Migration Strategy

### Version Control

Migrations are version-controlled and applied sequentially.

```
migrations/
├── 001_initial_schema.py
├── 002_add_embeddings_index.py
├── 003_add_collections.py
└── 004_add_metadata_fields.py
```

### Migration Registry

```python
from secondbrain.migrations import MigrationRegistry

registry = MigrationRegistry()
registry.register("001_initial_schema", initial_migration)
registry.register("002_add_embeddings_index", add_index_migration)
```

## Running Migrations

### CLI Command

```bash
# Apply all pending migrations
secondbrain migrate

# Apply specific migration
secondbrain migrate --target 003_add_collections

# Show migration status
secondbrain migrate --status

# Rollback last migration
secondbrain migrate --rollback
```

### Programmatic

```python
from secondbrain.migrations import run_migrations

# Run all migrations
run_migrations()

# Run with options
run_migrations(
    target_version="003_add_collections",
    dry_run=True,
    verbose=True
)
```

## Writing Migrations

### Basic Migration

```python
from secondbrain.migrations import Migration

class AddEmbeddingsIndex(Migration):
    name = "002_add_embeddings_index"
    
    async def up(self, db):
        """Apply migration."""
        await db.documents.create_index(
            [("embeddings", "vector")],
            options={"numDimensions": 384}
        )
    
    async def down(self, db):
        """Rollback migration."""
        await db.documents.drop_index("embeddings_vector_idx")
```

### Data Migration

```python
class MigrateMetadata(Migration):
    name = "004_add_metadata_fields"
    
    async def up(self, db):
        """Add new metadata fields."""
        async for doc in db.documents.find({}):
            if "author" not in doc.get("metadata", {}):
                await db.documents.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"metadata.author": "Unknown"}}
                )
```

## Migration Best Practices

### Idempotency

```python
# Good - Safe to run multiple times
async def up(self, db):
    index_name = "embeddings_vector_idx"
    indexes = await db.documents.list_indexes().to_list()
    if not any(idx["name"] == index_name for idx in indexes):
        await db.documents.create_index(...)

# Avoid - Will fail if run twice
async def up(self, db):
    await db.documents.create_index(...)  # Fails if exists
```

### Backwards Compatibility

```python
# Support old and new schema during transition
async def search(self, query):
    # Handle both old and new metadata format
    if "metadata.author" in doc:
        author = doc["metadata.author"]
    else:
        author = doc["metadata"].get("author", "Unknown")
```

### Testing

```python
import pytest
from secondbrain.migrations import MigrationRunner

@pytest.mark.asyncio
async def test_migration_002():
    """Test migration 002."""
    db = get_test_db()
    migration = AddEmbeddingsIndex()
    
    # Apply
    await migration.up(db)
    
    # Verify
    indexes = await db.documents.list_indexes().to_list()
    assert any(idx["name"] == "embeddings_vector_idx" for idx in indexes)
    
    # Rollback
    await migration.down(db)
```

## Rollback Strategy

### Automatic Rollback

```python
from secondbrain.migrations import Migration

class SafeMigration(Migration):
    async def up(self, db):
        try:
            await self._apply_changes(db)
        except Exception as e:
            await self._rollback(db)
            raise MigrationError(f"Migration failed: {e}")
```

### Manual Rollback

```bash
# Rollback to specific version
secondbrain migrate --rollback-to 002_add_embeddings_index

# Rollback one step
secondbrain migrate --rollback
```

## Migration Status

### Check Status

```python
from secondbrain.migrations import MigrationStatus

status = MigrationStatus.get_current()
print(f"Current version: {status.current_version}")
print(f"Pending migrations: {status.pending}")
print(f"Applied migrations: {status.applied}")
```

### Migration History

```python
from secondbrain.migrations import get_migration_history

history = get_migration_history()
for migration in history:
    print(f"{migration.name}: {migration.applied_at}")
```

## Troubleshooting

### Failed Migration

```bash
# Check error logs
secondbrain migrate --verbose

# Inspect database state
mongosh secondbrain --eval "db.migrations.find()"

# Manual fix then continue
secondbrain migrate --continue
```

### Schema Mismatch

```bash
# Reset migrations (dangerous!)
secondbrain migrate --reset

# Or fix schema manually
mongosh secondbrain --eval "db.documents.dropIndex('...')"
```

## See Also

- [Migration Guide](../migration.md)
- [Schema](../architecture/SCHEMA.md)
- [Configuration](configuration.md)
