# Migrations Guide

Schema migration strategies for SecondBrain.

## Overview

SecondBrain uses MongoDB, which has a flexible schema. However, migrations may be needed for:

- New required fields
- Data transformations
- Index changes
- Collection restructuring

## Migration Strategies

### 1. Forward Compatibility

Design schemas to be forward-compatible:

```python
class Document(BaseModel):
    id: str
    content: str
    # New fields optional
    metadata: Optional[Dict] = None
```

### 2. Versioned Documents

Add schema version to documents:

```python
{
    "_id": "...",
    "schema_version": "1.0",
    "content": "...",
    "metadata": {...}
}
```

### 3. Migration Scripts

Create migration scripts for data transformations:

```python
async def migrate_v1_to_v2():
    """Migrate documents from schema v1 to v2."""
    async for doc in collection.find({"schema_version": "1.0"}):
        # Transform document
        doc["new_field"] = transform(doc["old_field"])
        doc["schema_version"] = "2.0"
        await collection.replace_one({"_id": doc["_id"]}, doc)
```

## Migration Workflow

### 1. Plan Migration

- Document schema changes
- Estimate data volume
- Plan rollback strategy
- Test on subset of data

### 2. Create Migration Script

```python
async def run_migration():
    # Backup first
    await backup_collection()
    
    # Run migration
    await migrate_v1_to_v2()
    
    # Verify
    await verify_migration()
```

### 3. Backup Data

```bash
mongodump --db secondbrain --out ./backup/
```

### 4. Run Migration

```bash
python -m secondbrain.management.migrate --from 1.0 --to 2.0
```

### 5. Verify

```python
def verify_migration():
    # Check document count
    # Validate new fields
    # Test queries
    pass
```

### 6. Rollback (if needed)

```bash
mongorestore --db secondbrain ./backup/secondbrain/
```

## Common Migration Patterns

### Adding Required Field

```python
async def add_required_field():
    default_value = "default"
    
    async for doc in collection.find({"new_field": {"$exists": False}}):
        doc["new_field"] = default_value
        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"new_field": default_value}}
        )
```

### Renaming Field

```python
async def rename_field():
    async for doc in collection.find({"old_field": {"$exists": True}}):
        doc["new_field"] = doc["old_field"]
        del doc["old_field"]
        await collection.replace_one({"_id": doc["_id"]}, doc)
```

### Splitting Field

```python
async def split_field():
    async for doc in collection.find({"combined": {"$exists": True}}):
        parts = doc["combined"].split("|")
        doc["field1"] = parts[0]
        doc["field2"] = parts[1]
        del doc["combined"]
        await collection.replace_one({"_id": doc["_id"]}, doc)
```

## Index Management

### Create Index

```python
await collection.create_index([("new_field", 1)])
```

### Drop Index

```python
await collection.drop_index("index_name")
```

### Background Index Creation

```python
await collection.create_index(
    [("field", 1)],
    background=True  # Don't block operations
)
```

## Best Practices

1. **Always backup** before migrations
2. **Test on small dataset** first
3. **Run in stages** for large datasets
4. **Monitor performance** during migration
5. **Have rollback plan** ready
6. **Document changes** in migration notes

## Migration Commands

```bash
# List available migrations
secondbrain migrate --list

# Run specific migration
secondbrain migrate --to 2.0

# Dry run (preview changes)
secondbrain migrate --dry-run
```

## Troubleshooting

### Migration Failed

```bash
# Check logs
secondbrain migrate --verbose

# Restore from backup
mongorestore --db secondbrain ./backup/
```

### Incomplete Migration

```bash
# Resume migration
secondbrain migrate --resume
```

## Next Steps

- [Schema Reference](../architecture/SCHEMA.md) - Current schema
- [Changelog](changelog.md) - Version history
