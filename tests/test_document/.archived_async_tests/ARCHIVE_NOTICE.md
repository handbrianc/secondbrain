# Archived Async Ingestion Tests

These test files have been consolidated into `test_async_ingestion.py` to reduce redundancy and improve maintainability.

## Consolidation Date
May 30, 2026

## Files Archived
- `test_async_api.py` (2 tests) - Async context manager tests
- `test_async_api_extended.py` (3 tests) - Extended async coverage tests  
- `test_async_backward_compat.py` (6 tests) - Sync/async compatibility tests
- `test_async_embedding_native.py` (6 tests) - Native async embedding tests
- `test_async_ingest_method.py` (3 tests) - Async ingest method tests
- `test_async_storage_integration.py` (3 tests) - Async storage integration tests

**Total: 23 tests consolidated into 1 unified suite**

## New Location
All tests have been migrated to: `tests/test_document/test_async_ingestion.py`

## Test Organization
The consolidated file is organized into these test classes:
- `TestAsyncDocumentIngestor` - Basic async API tests (context manager)
- `TestAsyncDocumentIngestorCoverage` - Extended async coverage (semaphore, empty files)
- `TestAsyncBackwardCompat` - Sync/async compatibility
- `TestAsyncEmbeddingNative` - Native async embedding generation
- `TestAsyncIngestMethod` - Async ingest method functionality
- `TestAsyncStorageIntegration` - Async storage operations

## Running Tests
```bash
# Run all consolidated async tests
pytest tests/test_document/test_async_ingestion.py -v

# Run specific test class
pytest tests/test_document/test_async_ingestion.py::TestAsyncBackwardCompat -v
```

## Verification
All 21 tests pass successfully:
```
============================= 21 passed in 40.80s ==============================
```

## Reason for Consolidation
Per test review action plan 1.1:
- Reduced redundancy (6 files → 1 file)
- Improved maintainability
- Better test organization
- Easier to understand async testing patterns
- Eliminates duplicate test setup
