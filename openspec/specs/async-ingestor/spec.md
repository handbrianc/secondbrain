# Async Ingestor

## ADDED Requirements

### Requirement: AsyncDocumentIngestor class

The system SHALL provide an AsyncDocumentIngestor class that mirrors DocumentIngestor functionality with native async operations.

#### Scenario: Class exists and is importable

- **WHEN** user imports from secondbrain.document
- **THEN** AsyncDocumentIngestor SHALL be available

#### Scenario: Constructor accepts same parameters as sync version

- **WHEN** AsyncDocumentIngestor is instantiated
- **THEN** it SHALL accept chunk_size, chunk_overlap, and verbose parameters
- **AND** validation rules SHALL be identical to DocumentIngestor

### Requirement: Native async embedding generation

The AsyncDocumentIngestor SHALL use native async embedding generation instead of asyncio.to_thread().

#### Scenario: Batch embedding uses async API

- **WHEN** generate_batch_async() is called
- **THEN** it SHALL use async embedding generator
- **AND** SHALL NOT block event loop

#### Scenario: Single embedding uses async API

- **WHEN** generate_async() is called
- **THEN** it SHALL use async embedding generator
- **AND** SHALL NOT block event loop

### Requirement: Async storage integration

The AsyncDocumentIngestor SHALL integrate with the vector storage protocol's async batch surface
(`store_batch_async`, backed by `QdrantVectorStorage`) for async database operations.

> **Note (2026-10-12):** Amended: the requirement header originally named class "AsyncVectorStorage",
> which does not exist in the shipped code. The real surface is the storage protocol's
> `store_batch_async` (`src/secondbrain/storage/protocol.py:19-56`), implemented by
> `QdrantVectorStorage` (`src/secondbrain/storage/qdrant.py`). Header wording corrected in place above;
> the 2026-10-11 note below is retained unchanged.

> **Note (2026-10-11):** Amended (user decision D3): storage is batch-only. No single-document `store_async()`
> method exists in the shipped code — `src/secondbrain/storage/qdrant.py` and the storage protocol provide
> `store_batch_async()` only, and the async ingestor uses it exclusively. The former "Store operations are
> async" scenario naming `store_async()` has been removed; this requirement now covers batch storage only.

#### Scenario: Batch store operations are async

- **WHEN** storing multiple documents
- **THEN** store_batch_async() SHALL be used
- **AND** it SHALL delegate to the Qdrant-backed store_batch() via asyncio.to_thread (src/secondbrain/storage/qdrant.py), remaining non-blocking from the caller's perspective

### Requirement: Async context manager support

The AsyncDocumentIngestor SHALL support async context manager protocol.

#### Scenario: Async with statement works

- **WHEN** user uses `async with AsyncDocumentIngestor()`
- **THEN** **aenter**() SHALL initialize resources
- **AND** **aexit**() SHALL cleanup resources

#### Scenario: Resources are properly released

- **WHEN** async context exits
- **THEN** async client connections SHALL be closed
- **AND** no resource leaks SHALL occur

### Requirement: Async ingestion method

The AsyncDocumentIngestor SHALL provide ingest_async() method for async document processing.

#### Scenario: Ingest returns same result structure

- **WHEN** ingest_async() completes
- **THEN** it SHALL return dict with 'success' and 'failed' counts
- **AND** structure SHALL match sync version

#### Scenario: Files are processed asynchronously

- **WHEN** multiple files are ingested
- **THEN** processing SHALL be concurrent using asyncio.gather()
- **AND** SHALL NOT use ProcessPoolExecutor

### Requirement: Backward compatibility

The AsyncDocumentIngestor SHALL coexist with DocumentIngestor without conflicts.

#### Scenario: Both classes can be imported

- **WHEN** user imports from secondbrain.document
- **THEN** both DocumentIngestor and AsyncDocumentIngestor SHALL be available
- **AND** imports SHALL NOT conflict

#### Scenario: Existing sync code continues to work

- **WHEN** existing code uses DocumentIngestor
- **THEN** it SHALL continue to work unchanged
- **AND** no deprecation warnings SHALL be issued

### Requirement: Async embedding generator support

The system SHALL provide async embedding generators that work with AsyncDocumentIngestor.

- **WHEN** AsyncDocumentIngestor needs embeddings
- **THEN** it SHALL call generate_async() or generate_batch_async()
- **AND** these methods SHALL use aiohttp or httpx async client

#### Scenario: Async generator supports batching

- **WHEN** generate_batch_async() is called
- **THEN** it SHALL send batch request asynchronously
- **AND** SHALL return list of embeddings
