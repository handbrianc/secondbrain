# Storage Pipeline Module

MongoDB search pipeline builder for vector search with optimized filtering.

## Overview

The pipeline builder constructs MongoDB aggregation pipelines for vector search with optional source and file type filtering. Uses anchored regex for improved index performance.

## build_search_pipeline Function

Builds a MongoDB aggregation pipeline for vector search.

### Parameters

- `embedding` (list[float]): Query embedding vector
- `top_k` (int): Number of results to return
- `source_filter` (str | None): Filter by source file (optional)
- `file_type_filter` (str | None): Filter by file type (optional)
- `use_prefix_match` (bool): If True, use anchored regex for better index usage (default: True)

### Returns

Aggregation pipeline (list[dict]) for vector search.

### Example Usage

```python
from secondbrain.storage.pipeline import build_search_pipeline

# Basic search
pipeline = build_search_pipeline(
    embedding=[0.1, 0.2, ...],
    top_k=10
)

# Search with source filter
pipeline = build_search_pipeline(
    embedding=[0.1, 0.2, ...],
    top_k=10,
    source_filter="document.pdf"
)

# Search with file type filter
pipeline = build_search_pipeline(
    embedding=[0.1, 0.2, ...],
    top_k=10,
    file_type_filter="pdf"
)
```

### Pipeline Structure

The generated pipeline includes:
1. **$vectorSearch**: Vector similarity search on the embedding field
2. **$match** (optional): Filter by source file and/or file type
3. **$project**: Project relevant fields (chunk_id, source_file, page_number, chunk_text, score)

## Related Documentation

- [API Reference](./index.md) - API documentation overview
- [Storage Guide](./storage.md) - Storage layer documentation
- [Architecture](../architecture/SCHEMA.md) - Database schema
