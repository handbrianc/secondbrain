# Migration Strategy

This document describes how schema changes are handled in SecondBrain.

## Versioning

### Current Schema Version
- **Version**: 1
- **Introduced**: Initial implementation

### Version Tracking
- Each document in the database includes a `version` field
- The schema version is tracked in `../architecture/index.mdschema.md`
- Migration scripts are stored in `migrations/` directory

## Migration Categories

### 1. Backward Compatible Changes
No migration required. Examples:
- Adding optional fields
- Adding new indexes
- Changing default values

### 2. Non-Breaking Upgrades
No migration needed but migration script provided:
- Adding new metadata fields with defaults
- Adding new search indexes
- Refactoring internal code

### 3. Breaking Changes
Require migration script:
- Removing fields
- Changing field types
- Renaming fields
- Modifying vector dimension requirements

## Migration Script Structure

Migration scripts are located in `migrations/` directory:

```
migrations/
├── v1__initial_schema.sql          # Initial schema
├── v2__add_version_field.sql      # Add version field to all documents
└── v3__optimize_indexes.sql       # Optimize index configuration
```

### Script Naming Convention
```
v<version>__<description>.<extension>
```

- `<version>`: Target schema version
- `<description>`: Brief description
- `<extension>`: `.sql` for database migrations, `.py` for data migrations

## Migration Process

### For Development/Testing
1. Run migrations before starting the application
2. Check `migrations_applied` collection for applied migrations
3. Rollback is not supported - restore from backup if needed

### For Production
1. Stop all application instances
2. Backup the database
3. Run migration scripts
4. Verify migration succeeded
5. Restart application instances

## Automated Migration

The application checks schema version on startup:

```python
# Pseudocode
if schema_version < current_version:
    run_migration(schema_version)
    update_schema_version(current_version)
```

### Migration Check Flow
1. Connect to MongoDB
2. Check `schema_versions` collection for current version
3. Compare with `current_version` constant
4. If newer version needed:
   - Check `schema_migrations_lock` collection
   - If lock acquired, run migration
   - Release lock and update version
5. If migration fails, log error and exit

## Manual Migration

To run migrations manually:

```bash
# Apply all pending migrations
python -m secondbrain migrations apply

# Check migration status
python -m secondbrain migrations status

# Rollback last migration (development only!)
python -m secondbrain migrations rollback
```

## Version History

### v1 (Current)
- Initial schema
- Embedding storage with MongoDB vector search
- Chunk metadata with ingestion timestamps

### Upcoming Versions

#### v2 (Planned)
- Add `version` field to all documents
- Add `source_hash` for content deduplication
- Optimize index configuration

#### v3 (Planned)
- Support for custom embedding dimensions
- Add full-text search metadata
- Improve pagination performance

## Migration Guidelines

### Best Practices
1. Always version documents
2. Provide migration scripts for breaking changes
3. Test migrations on full dataset before production
4. Document all changes in `../architecture/index.mdschema.md`
5. Update this migration guide with new patterns

### Avoid
- Modifying existing data without migration
- Removing fields without backward compatibility
- Changing vector dimensions without warning
- Migration scripts that take hours to run

## Troubleshooting

### Migration Stuck
If migration fails and leaves the database in an inconsistent state:
1. Stop the application
2. Restore from backup
3. Fix migration script
4. Re-run migration

### Version Mismatch
If application version doesn't match database schema version:
1. Check `../architecture/index.mdschema.md` for current version
2. Run migrations
3. Check logs for migration errors

## Support

For migration issues:
1. Check logs for detailed error messages
2. Verify database backup exists
3. Contact development team with migration ID

## Related Documentation

- [Schema Reference](../architecture/SCHEMA.md) - Database schema
- [Development Guide](./development.md) - Development workflow
