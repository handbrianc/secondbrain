## 1. Configuration Setup

- [x] 1.1 Add `max_workers` field to `Config` class in `src/secondbrain/config/__init__.py` with default `None` and description "Maximum number of worker processes for parallel processing"
- [x] 1.2 Add validation for `max_workers` to ensure it's positive when set (add to existing `validate_config_values` method)
- [x] 1.3 Update `get_config()` documentation to mention multicore settings

## 2. CLI Interface Updates

- [x] 2.1 Add `--cores` / `-c` option to `ingest` command in `src/secondbrain/cli/commands.py`
- [x] 2.2 Update `ingest` function signature to accept `cores: int | None` parameter
- [x] 2.3 Add help text explaining multicore usage: "Number of CPU cores to use for parallel processing (default: auto-detect)"
- [x] 2.4 Add validation logic to clamp core count to available CPU count with warning message
- [x] 2.5 Update CLI help text for `--batch-size` to mention compatibility with `--cores`

## 3. Worker Functions for Multiprocessing

- [x] 3.1 Create module-level worker function `_extract_and_chunk_file()` in `src/secondbrain/document/__init__.py`
- [x] 3.2 Worker function SHALL accept file_path, chunk_size, chunk_overlap as parameters
- [x] 3.3 Worker function SHALL return dict with keys: `success`, `file_path`, `chunks`, `error`
- [x] 3.4 Worker function SHALL handle all exceptions and return error info instead of raising
- [x] 3.5 Add proper type hints to worker function signature

## 4. DocumentIngestor Refactoring

- [x] 4.1 Import `ProcessPoolExecutor` and `as_completed` from `concurrent.futures` in `src/secondbrain/document/__init__.py`
- [x] 4.2 Import `os` module for CPU count detection
- [x] 4.3 Update `ingest()` method signature to accept `cores: int | None = None` parameter
- [x] 4.4 Add core count resolution logic: `cores or config.max_workers or os.cpu_count()`
- [x] 4.5 Replace `ThreadPoolExecutor` with `ProcessPoolExecutor` for text extraction phase
- [x] 4.6 Submit `_extract_and_chunk_file` worker to process pool for each file
- [x] 4.7 Process results from `as_completed()` and collect successful/failed counts
- [x] 4.8 Add progress tracking: display "Processing file X/Y" during execution
- [x] 4.9 Keep embedding generation and storage in ThreadPoolExecutor (I/O-bound)
- [x] 4.10 Ensure worker function is picklable (module-level, no closures)

## 5. Memory Management

- [x] 5.1 Add constant `MAX_MEMORY_BATCH_SIZE = 100` for embedding batch limiting
- [x] 5.2 Implement batch splitting logic in embedding generation phase
- [x] 5.3 Add memory usage logging in verbose mode
- [x] 5.4 Ensure proper cleanup of worker process resources (ProcessPoolExecutor handles this automatically)

## 6. Error Handling and Recovery

- [x] 6.1 Implement error aggregation from worker processes
- [x] 6.2 Log detailed error messages for failed files (include stack trace in verbose mode)
- [x] 6.3 Ensure accurate success/failure counts returned from `ingest()` method
- [x] 6.4 Add handling for `BrokenProcessPool` exceptions
- [x] 6.5 Test error scenarios: corrupted files, permission errors, unsupported formats

## 7. Rate Limiting Integration

- [x] 7.1 Verify rate limiter is thread-safe and works across process boundaries (threading.Lock, embedding phase runs in main process)
- [x] 7.2 Test that multiple workers don't exceed rate limit threshold (covered by existing rate limiter tests)
- [x] 7.3 Add rate limit queue logging in verbose mode

## 8. Testing

- [x] 8.1 Create test `test_multicore_ingestion.py` in `tests/test_document/`
- [x] 8.2 Test single file ingestion with `--cores 1`
- [x] 8.3 Test directory ingestion with `--cores 4`
- [x] 8.4 Test core count validation (0, negative, excessive values)
- [x] 8.5 Test fallback to config `max_workers` setting
- [x] 8.6 Test fallback to CPU count auto-detection
- [x] 8.7 Test error handling: file with extraction failure doesn't crash batch
- [x] 8.8 Test progress tracking output
- [x] 8.9 Test backward compatibility: no `--cores` flag uses existing behavior
- [x] 8.10 Test Windows compatibility (if available): verify spawn method works

## 9. Documentation

- [x] 9.1 Update README.md with multicore usage example: `secondbrain ingest /docs --cores 4`
- [x] 9.2 Add performance tips section to `docs/getting-started/configuration.md`
- [x] 9.3 Document memory considerations for large-scale ingestion
- [x] 9.4 Add troubleshooting section for multiprocessing issues
- [x] 9.5 Update docstrings in `DocumentIngestor` class to mention multicore support

## 10. Verification and Cleanup

- [x] 10.1 Run `ruff check .` to ensure no linting errors
- [x] 10.2 Run `ruff format .` to ensure proper formatting
- [x] 10.3 Run `mypy .` to ensure no type errors
- [x] 10.4 Run `pytest -m "not integration"` to verify fast tests pass
- [x] 10.5 Run integration tests with actual documents to verify performance improvement
- [x] 10.6 Measure performance: compare single-core vs 4-core ingestion time
- [x] 10.7 Verify no memory leaks during long ingestion sessions
- [x] 10.8 Clean up any temporary files or resources
