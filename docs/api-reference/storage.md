# Storage Module

MongoDB vector storage with batch operations.

## VectorStorage

::: secondbrain.storage.VectorStorage
    options:
        show_root_heading: true
        show_source: false
        members:
            - store
            - store_batch
            - search
            - delete_by_source
            - get_stats
            - list_chunks

## Helper Functions

::: secondbrain.storage.build_search_pipeline
    options:
        show_root_heading: false
        show_source: false

## Types

::: secondbrain.storage.DatabaseStats
    options:
        show_root_heading: false
        show_source: false

## Related Documentation

- [API Reference](./index.md) - API documentation overview
- [Storage Guide](../developer-guide/development.md#testing) - Storage layer
