# Migration Guide

This guide helps you migrate between SecondBrain versions and handle data migration scenarios.

## Version Migration

### v0.4.0 Migration Notes

#### Breaking Changes
- None - This is a backward-compatible release

#### New Features
- Async API support
- MCP server integration
- OpenTelemetry tracing
- Circuit breaker pattern

#### Upgrade Steps
```bash
# Upgrade to latest version
pip install --upgrade secondbrain

# Verify installation
secondbrain --version

# Run health check
secondbrain health-check
```

### Database Schema Changes

SecondBrain v0.4.0 maintains database compatibility with previous versions. No manual migration is required.

## Data Migration

### Exporting Data

```bash
# Export all documents to JSON
secondbrain export --format json --output backup.json

# Export specific collection
secondbrain export --collection my-docs --format json --output backup.json
```

### Importing Data

```bash
# Import from JSON
secondbrain import --input backup.json
```

### Manual Migration

For custom migration scenarios:

```python
from secondbrain.document import Document
from secondbrain.storage import MongoDBStorage

# Connect to old database
old_storage = MongoDBStorage(uri="mongodb://old-host:27017")

# Connect to new database  
new_storage = MongoDBStorage(uri="mongodb://new-host:27017")

# Migrate documents
for doc in old_storage.list_documents():
    content = old_storage.get_document(doc.id)
    new_storage.store_document(doc, content)
```

## Configuration Migration

### Environment Variables

Old format (deprecated):
```bash
MONGO_URI=mongodb://localhost:27017
DB_NAME=secondbrain
```

New format (v0.4.0+):
```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=secondbrain
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

The system automatically migrates old environment variables to the new format.

## Troubleshooting

### Migration Fails

**Issue**: Import fails with connection error

**Solution**:
1. Verify MongoDB is running
2. Check connection string format
3. Ensure network connectivity
4. Check MongoDB logs

### Data Loss After Upgrade

**Issue**: Documents missing after upgrade

**Solution**:
1. Check MongoDB connection
2. Verify correct database name
3. Restore from backup if needed
4. Check application logs for errors

## Support

If you encounter migration issues:
- Check [Troubleshooting Guide](../getting-started/troubleshooting.md)
- Open an issue on GitHub
- Review application logs

---

Last updated: March 2026
