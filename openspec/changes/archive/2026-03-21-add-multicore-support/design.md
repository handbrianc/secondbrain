## Context

The current implementation uses `ThreadPoolExecutor` for parallel file processing in `DocumentIngestor.ingest()`, but this approach has limitations:

1. **Thread-based parallelism**: Python's GIL limits true parallelism for CPU-bound tasks
2. **No core count control**: Users cannot configure how many workers to use
3. **Mixed workload handling**: Text extraction (CPU-bound) and embedding generation (I/O-bound) are processed together without optimization
4. **Limited progress tracking**: No detailed progress reporting during multicore operations

The design must balance:
- CPU-bound tasks (text extraction, chunking) benefit from `multiprocessing`
- I/O-bound tasks (embedding API calls, MongoDB writes) benefit from threading/async
- Memory usage when spawning multiple processes
- Cross-platform compatibility (Windows/macOS/Linux)

## Goals / Non-Goals

**Goals:**

1. Add configurable core count via `--cores` CLI option and `max_workers` config
2. Implement true multiprocessing for CPU-bound operations (text extraction, chunking)
3. Maintain thread-based parallelism for I/O-bound operations (embedding generation, storage)
4. Provide progress tracking for multicore operations
5. Optimize memory usage with proper worker management
6. Ensure backward compatibility - default to current behavior if not specified

**Non-Goals:**

1. Real-time progress UI (progress bars, live updates)
2. Distributed processing across multiple machines
3. Automatic core detection optimization (user-configured only)
4. Support for async multiprocessing (complexity not justified)
5. Breaking changes to existing APIs

## Decisions

### 1. Use `concurrent.futures.ProcessPoolExecutor` for CPU-bound tasks

**Decision**: Use `ProcessPoolExecutor` for text extraction and chunking, `ThreadPoolExecutor` for I/O-bound tasks.

**Rationale**:
- `ProcessPoolExecutor` bypasses Python's GIL for true parallelism
- `ThreadPoolExecutor` is sufficient for I/O-bound operations (network calls, disk I/O)
- `concurrent.futures` provides consistent API across both executor types
- Cross-platform compatible (unlike raw `multiprocessing` on Windows)

**Alternatives Considered**:
- **Raw `multiprocessing` module**: More control but complex API, Windows compatibility issues
- **`joblib` library**: Simpler API but adds dependency, less flexible
- **Pure threading**: Doesn't solve GIL limitation for CPU-bound tasks

### 2. Separate CPU-bound and I/O-bound processing phases

**Decision**: Split ingestion into two distinct phases:
1. **Phase 1 (CPU-bound)**: Extract text and chunk documents using `ProcessPoolExecutor`
2. **Phase 2 (I/O-bound)**: Generate embeddings and store using `ThreadPoolExecutor`

**Rationale**:
- Each phase can use the optimal parallelization strategy
- Reduces memory overhead (embeddings generated after text extraction completes)
- Clear separation of concerns improves maintainability

**Alternatives Considered**:
- **Single mixed phase**: Simpler but suboptimal parallelization strategy
- **Async for everything**: Overly complex, doesn't help with CPU-bound tasks

### 3. Use `--cores` CLI option with config fallback

**Decision**: Add `--cores` / `-c` CLI option that overrides `max_workers` config, which defaults to CPU count.

**Rationale**:
- CLI option provides immediate control for one-off operations
- Config provides persistent default for regular users
- CPU count auto-detection provides sensible default

**Implementation**:
```python
@click.option("--cores", "-c", type=int, help="Number of CPU cores to use")
def ingest(..., cores: int | None):
    config = get_config()
    num_cores = cores or getattr(config, 'max_workers', None) or os.cpu_count()
```

**Alternatives Considered**:
- **Config-only**: Less flexible for ad-hoc operations
- **CLI-only**: Requires explicit specification every time
- **Auto-detection based on workload**: Complex, unpredictable behavior

### 4. Use picklable worker functions for ProcessPoolExecutor

**Decision**: Define worker functions at module level (not methods) to ensure they can be pickled for process spawning.

**Rationale**:
- `ProcessPoolExecutor` requires functions to be picklable
- Module-level functions are simpler to pickle than bound methods
- Clear separation between worker logic and orchestration

**Implementation Pattern**:
```python
def _extract_and_chunk_file(file_path: Path, chunk_size: int, chunk_overlap: int) -> dict:
    """Worker function for process pool - must be module-level."""
    # Extract text, chunk, return dict with results
    pass

class DocumentIngestor:
    def ingest(self, ...):
        with ProcessPoolExecutor(max_workers=num_cores) as executor:
            futures = [executor.submit(_extract_and_chunk_file, f, ...) for f in files]
            # Process results...
```

**Alternatives Considered**:
- **Lambda functions**: Cannot be pickled
- **Bound methods**: Complex pickling, platform-specific issues
- **`pathos` library**: More flexible but adds dependency

### 5. Memory-efficient batch processing with size limits

**Decision**: Limit batch sizes for embedding generation based on available memory.

**Rationale**:
- Multiple processes holding large text chunks can exhaust memory
- Embedding vectors are large (768 floats = ~3KB each)
- Need to balance parallelism with memory usage

**Implementation**:
```python
MAX_MEMORY_BATCH_SIZE = 100  # Max chunks to embed in one batch
batch_size = min(len(chunks), MAX_MEMORY_BATCH_SIZE)
```

**Alternatives Considered**:
- **Dynamic memory monitoring**: Complex, overhead
- **Fixed batch size**: May be too large for some systems or too small for others

## Risks / Trade-offs

### 1. Process spawning overhead

**Risk**: Creating multiple processes has startup cost (~100ms per process on typical systems).

**Mitigation**: 
- Use `ProcessPoolExecutor` which maintains worker pool
- Only beneficial for batches of 5+ files
- Document recommendation: use for directories, not single files

### 2. Memory duplication across processes

**Risk**: Each process gets its own copy of Python interpreter and imported modules.

**Mitigation**:
- Keep worker functions minimal (only import what's needed)
- Use `copy_on_write` semantics of fork (on Unix)
- Limit concurrent workers via `--cores` option
- Document memory considerations for large-scale ingestion

### 3. Error handling across process boundaries

**Risk**: Exceptions in worker processes must be pickled and re-raised in main process.

**Mitigation**:
- Wrap worker functions in try-except, return error info in result dict
- Use `future.result()` to propagate exceptions
- Log detailed error information in worker processes

### 4. Windows compatibility with multiprocessing

**Risk**: Windows uses `spawn` method (not `fork`), requiring `if __name__ == "__main__":` guards.

**Mitigation**:
- Use `concurrent.futures` which abstracts platform differences
- Ensure all worker functions are module-level
- Test on Windows before release

### 5. Rate limiting with multiple workers

**Risk**: Multiple processes/threads may overwhelm sentence-transformers API.

**Mitigation**:
- Keep rate limiter as singleton shared across workers
- Rate limiter uses thread-safe primitives
- Document recommendation to adjust rate limits for multicore usage

## Migration Plan

### Phase 1: Add configuration (backward compatible)

1. Add `max_workers` field to `Config` class with default `None` (uses CPU count)
2. No CLI changes yet - users can set via environment variable

### Phase 2: Add CLI option

1. Add `--cores` / `-c` option to `ingest` command
2. Update help text to explain multicore usage

### Phase 3: Refactor ingestion pipeline

1. Create worker functions for text extraction and chunking
2. Refactor `DocumentIngestor.ingest()` to use `ProcessPoolExecutor`
3. Add progress tracking
4. Update tests to verify parallel behavior

### Phase 4: Documentation

1. Update README with multicore usage examples
2. Add performance tips to configuration docs
3. Document memory considerations

### Rollback Strategy

- All changes are additive - no breaking changes
- If issues arise, can disable by not using `--cores` flag
- Config defaults to `None` which maintains current behavior

## Open Questions

1. **What's the optimal default batch size for embedding generation?**
   - Current: 10 (from `--batch-size` option)
   - Question: Should this be separate from core count?

2. **Should we auto-detect optimal core count based on workload?**
   - CPU-bound vs I/O-bound ratio varies by document types
   - Complexity vs benefit trade-off

3. **How to handle progress reporting across process boundaries?**
   - ProcessPoolExecutor doesn't support callbacks easily
   - Option: Use queue-based progress reporting
   - Option: Simple file-based progress tracking

4. **Should we add a `--dry-run` option to test multicore setup?**
   - Useful for debugging without actual ingestion
   - Adds complexity
