# Management Module

Document management operations (list, delete, status) for the vector database.

## Overview

The management module provides classes for listing, deleting, and checking status of documents stored in the vector database. All classes use context manager support for proper resource cleanup.

## Key Components

### BaseManager Class

Base class for management operations with MongoDB availability validation.

#### Methods

- `__init__(verbose)` - Initialize with optional verbose logging
- `_ensure_storage_available()` - Ensure MongoDB is available, raise if not
- `close()` - Close storage connection

#### Context Manager Support

All managers support context manager protocol:

```python
with Lister() as lister:
    chunks = lister.list_chunks()
```

### Lister Class

Handles listing of ingested documents and chunks.

#### Methods

- `__init__(verbose)` - Initialize lister
- `list_chunks(source_filter, chunk_id, limit, offset)` - List chunks with optional filters

### Deleter Class

Handles document deletion by source file.

#### Methods

- `__init__(verbose)` - Initialize deleter
- `delete_by_source(source_file)` - Delete all chunks from a source file

### StatusChecker Class

Checks database statistics and health.

#### Methods

- `__init__(verbose)` - Initialize status checker
- `get_stats()` - Get database statistics

## Example Usage

```python
from secondbrain.management import Lister, Deleter, StatusChecker

# List chunks
with Lister() as lister:
    chunks = lister.list_chunks(source_filter="document.pdf", limit=10)
    for chunk in chunks:
        print(f"{chunk.chunk_id}: {chunk.text[:100]}")

# Delete documents
with Deleter() as deleter:
    deleter.delete_by_source("old_document.pdf")

# Check status
with StatusChecker() as checker:
    stats = checker.get_stats()
    print(f"Total chunks: {stats['total_chunks']}")
```

## Related Documentation

- [API Reference](./index.md) - API documentation overview
- [Document Management](../user-guide/document-management.md) - Usage guide
- [CLI Reference](./cli.md) - CLI commands
