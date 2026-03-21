## Why

The current CLI has basic parallel processing via ThreadPoolExecutor for ingestion, but lacks true multicore utilization for CPU-bound tasks like text extraction, chunking, and embedding generation. As document volumes grow, leveraging multiple CPU cores will significantly reduce processing time and improve throughput.

## What Changes

- Add `--cores` / `-c` CLI option to control number of CPU cores used for parallel processing
- Implement multiprocessing for CPU-bound operations (text extraction, chunking)
- Enhance batch embedding generation to utilize multiple cores effectively
- Add configuration for core count in `config.py` with auto-detection fallback
- Improve progress reporting for multicore operations
- Optimize memory usage when processing with multiple cores

**No breaking changes** - all new features are opt-in via CLI flags and config.

## Capabilities

### New Capabilities

- `multicore-ingestion`: Enable parallel document ingestion across multiple CPU cores with configurable worker count, progress tracking, and memory-efficient batch processing

### Modified Capabilities

- None (purely additive changes to existing parallel processing)

## Impact

**Code Changes:**
- `cli/commands.py`: Add `--cores` option to `ingest` command
- `document/__init__.py`: Refactor `DocumentIngestor.ingest()` to support multiprocessing
- `embedding/generator.py`: Enhance `generate_batch()` for multicore utilization
- `config/__init__.py`: Add `max_workers` configuration option

**Dependencies:**
- No new dependencies (uses Python's built-in `multiprocessing` and `concurrent.futures`)

**Performance:**
- Expected 2-4x speedup on 4-core systems for large document batches
- Reduced wall-clock time for CPU-bound operations
- Better resource utilization on multi-core machines

**Compatibility:**
- Backward compatible - defaults to current behavior if `--cores` not specified
- Windows/macOS/Linux compatible (uses `concurrent.futures` for cross-platform support)
