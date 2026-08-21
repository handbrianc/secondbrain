# Migration Guide

Instructions for migrating between SecondBrain versions or updating configurations.

> **2026-08 / MongoDB → Qdrant + SQLite migration**: vector storage moved to Qdrant (`QdrantVectorStorage` +
> `StorageFactory`; chunk metadata in the Qdrant payload), conversation sessions moved to SQLite
> (`ConversationStorage`), and MongoDB/pymongo were removed entirely. If you previously pointed at MongoDB, re-ingest
> your documents after setting `SECONDBRAIN_STORAGE_BACKEND=qdrant`.

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
| ---------- | ---------- | --------- |
| `SECONDBRAIN_TEXT_COMPRESSION_ENABLED` | 0.4.0 | `false` |
| `SECONDBRAIN_RAG_MAX_CONTEXT_CHARS` | 0.4.0 | `8000` |
| `SECONDBRAIN_RAG_CHUNK_PREVIEW_CHARS` | 0.4.0 | `500` |
| `SECONDBRAIN_STORAGE_COMPRESSION_ENABLED` | 0.4.0 | `true` |

New variables have sensible defaults. Existing deployments continue working without changes.

## Storage Migration (Qdrant + SQLite)

SecondBrain now uses Qdrant for vector storage and SQLite for conversations/sessions. The `StorageFactory` selects
the backend; `QdrantVectorStorage` is the production backend and `MockVectorStorage` is used for tests.

### Vector Collection Verification

If vector search stops working after upgrade, verify Qdrant is running and reachable:

```bash
secondbrain start --wait
secondbrain health
# Qdrant recreates the collection on next ingest/search
```

### Data Export/Import

Backup before migration:

```bash
# Export current inventory
secondbrain ls --all > embeddings_backup.csv
```

Conversation sessions live in the SQLite database at `~/.secondbrain/secondbrain.db`. Back that file up if you need
to preserve chat history.

## Environment Variable Changes

### Removed Variables

The legacy MongoDB variables (`SECONDBRAIN_MONGO_URI`, `SECONDBRAIN_MONGO_DB`, `SECONDBRAIN_MONGO_COLLECTION`, and
any `MONGO_INITDB_*` variables) no longer exist. Replace them with the Qdrant/SQLite variables listed in the
configuration guide (`SECONDBRAIN_QDRANT_URL`, `SECONDBRAIN_QDRANT_COLLECTION`, `SECONDBRAIN_SQLITE_PATH`, and
`SECONDBRAIN_STORAGE_BACKEND`).

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
2. **Backup data**: export inventory (`secondbrain ls --all`) and back up the SQLite database
3. **Switch traffic**: Route to new version
4. **Monitor**: Watch for errors or regressions
5. **Rollback if needed**: Restore backup, redeploy old version

## Cross-Version Compatibility

| Client Version | Server Compatible | Notes |
| --------------- | ------------------- | ------- |
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

### Qdrant Connection Issues

```bash
# Verify Qdrant is running and check its logs
docker ps
docker logs secondbrain-qdrant

# Restart the stack
secondbrain stop
secondbrain start --wait
```

### Collection Creation Failures

Qdrant requires the collection to be reachable. Ensure the Qdrant service is running (`secondbrain start --wait`) and
that `SECONDBRAIN_QDRANT_URL` points at the correct endpoint. The collection is created automatically on first ingest.
