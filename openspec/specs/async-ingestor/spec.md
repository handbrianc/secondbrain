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
The AsyncDocumentIngestor SHALL integrate with AsyncVectorStorage for async database operations.

#### Scenario: Store operations are async
- **WHEN** storing documents
- **THEN** store_async() SHALL be used
- **AND** SHALL NOT use asyncio.to_thread() wrapper

#### Scenario: Batch store operations are async
- **WHEN** storing multiple documents
- **THEN** store_batch_async() SHALL be used
- **AND** SHALL use Motor's bulk write operations

### Requirement: Async context manager support
The AsyncDocumentIngestor SHALL support async context manager protocol.

#### Scenario: Async with statement works
- **WHEN** user uses `async with AsyncDocumentIngestor()`
- **THEN** __aenter__() SHALL initialize resources
- **AND** __aexit__() SHALL cleanup resources

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

#### Scenario: LocalEmbeddingGenerator has async methods
- **WHEN** AsyncDocumentIngestor needs embeddings
- **THEN** it SHALL call generate_async() or generate_batch_async()
- **AND** these methods SHALL use aiohttp or httpx async client

#### Scenario: Async generator supports batching
- **WHEN** generate_batch_async() is called
- **THEN** it SHALL send batch request asynchronously
- **AND** SHALL return list of embeddings
