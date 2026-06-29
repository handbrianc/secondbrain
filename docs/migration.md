# Migration Guide

Instructions for migrating between SecondBrain versions or updating configurations.

## Upgrading SecondBrain

### Standard Upgrade

```bash
# Upgrade via pip
pip install --upgrade secondbrain

# Verify version
secondbrain --version
```

### Version-Specific Notes

#### Upgrading to 0.4.0

Version 0.4.0 introduces:

- Text compression option (`SECONDBRAIN_TEXT_COMPRESSION_ENABLED`)
- Enhanced RAG formatting controls (`RAG_MAX_CONTEXT_CHARS`, `RAG_CHUNK_PREVIEW_CHARS`)
- Storage format migration from Binary to Array (see below)

#### Prior to 0.3.0

Older versions used different storage schemes. If upgrading from pre-0.3:

1. Export critical data via `secondbrain ls --all`
2. Consider export before major upgrades

### Re-ingesting Documents

After upgrade, consider re-ingesting documents to benefit from:

- Improved chunking algorithms
- Updated parsing improvements
- New metadata fields

```bash
# Export current inventory
secondbrain ls --all > pre_upgrade_inventory.csv

# Delete old data
secondbrain delete --all --yes

# Re-ingest with new version
secondbrain ingest ./documents/ --recursive --cores 4
```

## Configuration Migration

When adding new environment variables:

| Variable | Added In | Default |
|----------|----------|---------|
| `SECONDBRAIN_TEXT_COMPRESSION_ENABLED` | 0.4.0 | `false` |
| `SECONDBRAIN_RAG_MAX_CONTEXT_CHARS` | 0.4.0 | `8000` |
| `SECONDBRAIN_RAG_CHUNK_PREVIEW_CHARS` | 0.4.0 | `500` |
| `SECONDBRAIN_STORAGE_COMPRESSION_ENABLED` | 0.4.0 | `true` |

New variables have sensible defaults. Existing deployments continue working without changes.

## MongoDB Migration

### Collection Upgrades

SecondBrain creates indexes automatically on first run. MongoDB migrations may be needed for:

- Index type changes (e.g., `2dsphere` → `cosineSimilarity`)
- New fields added to schema

### Vector Index Recreation

If vector search stops working after upgrade:

```javascript
// Check current index
db.embeddings.getIndexes()

// If outdated, recreate
db.embeddings.dropIndex("vector_index")
// SecondBrain recreates on next ingest/search
```

### Data Export/Import

Backup before migration:

```bash
mongodump \
  --uri="$SECONDBRAIN_MONGO_URI" \
  --db=secondbrain \
  --collection=embeddings \
  --archive=embeddings_backup.archive
```

Restore if needed:

```bash
mongorestore \
  --uri="$SECONDBRAIN_MONGO_URI" \
  --db=secondbrain \
  --collection=embeddings \
  --archive=embeddings_backup.archive
```

## Environment Variable Changes

### Renamed Variables

Occasionally variables are renamed for clarity. Legacy names may continue working with deprecation warnings.

Current naming convention: `SECONDBRAIN_<DOMAIN>_<NAME>`

For example: `SECONDBRAIN_EMBEDDING_MODEL` not `SECONDBRAIN_MODEL`

### Removed Variables

Deprecated variables emit warnings. Check logs after upgrading.

## Docker Compose Migration

If using provided `docker-compose.yml`:

```bash
# Pull new image
docker pull secondbrain:latest

# Restart services
secondbrain stop
secondbrain start --wait

# Verify health
secondbrain health
```

For custom compose files, compare against provided template for new service definitions.

## Zero-Downtime Upgrades

For production environments:

1. **Stage in testing**: Deploy new version to staging
2. **Backup data**: `mongodump` current state
3. **Switch traffic**: Route to new version
4. **Monitor**: Watch for errors or regressions
5. **Rollback if needed**: Restore backup, redeploy old version

## Cross-Version Compatibility

| Client Version | Server Compatible | Notes |
|---------------|-------------------|-------|
| 0.4.0 | 0.4.0, forward compat | Current stable |
| 0.3.x | 0.4.0 | Fully compatible |
| < 0.3 | 0.4.0 | May have issues, upgrade recommended |

## Troubleshooting Upgrades

### Import Errors After Upgrade

```bash
# Clear import caches
rm -rf __pycache__ .pytest_cache

# Reinstall in dev mode
pip install -e . --force-reinstall
```

### MongoDB Schema Conflicts

```bash
# Check MongoDB server version
mongosh --eval "db.version()"

# Ensure MongoDB 4.4+ for vector search
# If using Atlas, verify tier supports vector search
```

### Index Creation Failures

Vector index creation requires MongoDB 5.0+ with specific index types.

```javascript
// Check server version for $vectorSearch support
db.adminCommand({getCmdLineOpts: ()}).parsed.version
```

Upgrade MongoDB if below 5.0, or disable automatic index creation and manage manually.