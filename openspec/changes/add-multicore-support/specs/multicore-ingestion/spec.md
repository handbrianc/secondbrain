## ADDED Requirements

### Requirement: CLI supports core count configuration
The system SHALL provide a `--cores` / `-c` CLI option for the `ingest` command that specifies the number of CPU cores to use for parallel processing.

#### Scenario: User specifies core count via CLI
- **WHEN** user runs `secondbrain ingest /path/to/docs --cores 4`
- **THEN** the system uses 4 CPU cores for parallel document processing

#### Scenario: User specifies short form core count
- **WHEN** user runs `secondbrain ingest /path/to/docs -c 8`
- **THEN** the system uses 8 CPU cores for parallel document processing

### Requirement: Core count falls back to configuration
When the `--cores` option is not provided, the system SHALL fall back to the `max_workers` configuration value.

#### Scenario: Config specifies default core count
- **WHEN** `SECONDBRAIN_MAX_WORKERS=6` is set in environment
- **AND** user runs `secondbrain ingest /path/to/docs` (without --cores)
- **THEN** the system uses 6 CPU cores for processing

#### Scenario: No config specified uses CPU count
- **WHEN** neither `--cores` nor `max_workers` config is set
- **AND** user runs `secondbrain ingest /path/to/docs`
- **THEN** the system automatically detects and uses the available CPU core count

### Requirement: Text extraction runs in parallel across cores
The system SHALL use `ProcessPoolExecutor` to extract text from multiple documents in parallel using the configured number of cores.

#### Scenario: Multiple documents processed concurrently
- **WHEN** user ingests a directory with 20 PDF files
- **AND** `--cores 4` is specified
- **THEN** up to 4 documents are processed simultaneously for text extraction
- **AND** total extraction time is significantly less than sequential processing

#### Scenario: Single document uses single core
- **WHEN** user ingests a single file
- **THEN** only one worker process is used regardless of core count configuration

### Requirement: Document chunking runs in parallel across cores
The system SHALL use `ProcessPoolExecutor` to chunk extracted text from multiple documents in parallel using the configured number of cores.

#### Scenario: Large documents chunked concurrently
- **WHEN** user ingests multiple large documents (100+ pages each)
- **AND** `--cores 4` is specified
- **THEN** chunking operations run in parallel across 4 cores
- **AND** chunk boundaries respect the configured chunk_size and chunk_overlap

### Requirement: Progress tracking displays during multicore operations
The system SHALL provide progress feedback during parallel document ingestion operations.

#### Scenario: Progress shown for batch ingestion
- **WHEN** user ingests a directory with multiple documents using `--cores 4`
- **THEN** the system displays progress information (e.g., "Processing file 5/20")
- **AND** completion status is shown when all files are processed

#### Scenario: Success/failure counts displayed
- **WHEN** ingestion completes with `--cores 4`
- **THEN** the system displays "Successfully ingested X files"
- **AND** if any failures occurred, displays "Failed: Y files"

### Requirement: Memory-efficient batch processing
The system SHALL limit batch sizes during parallel processing to prevent memory exhaustion.

#### Scenario: Large batches are split into smaller chunks
- **WHEN** processing 1000 document chunks with embeddings
- **AND** the batch would exceed memory limits
- **THEN** the system splits processing into smaller batches
- **AND** maintains correct ordering of results

#### Scenario: Memory usage scales with core count
- **WHEN** `--cores 8` is specified
- **THEN** each worker process maintains its own memory footprint
- **AND** total memory usage remains within reasonable bounds

### Requirement: Error handling across process boundaries
The system SHALL properly handle and report errors that occur in worker processes.

#### Scenario: File extraction failure doesn't crash entire batch
- **WHEN** one file in a batch of 20 fails to extract text
- **AND** `--cores 4` is specified
- **THEN** the system continues processing remaining files
- **AND** reports the specific file that failed
- **AND** returns accurate success/failure counts

#### Scenario: Serialization errors are caught and reported
- **WHEN** a worker process encounters an unpicklable object
- **THEN** the system catches the serialization error
- **AND** logs detailed error information
- **AND** continues processing other files

### Requirement: Rate limiting works with parallel processing
The system SHALL maintain rate limiting across all worker processes to prevent overwhelming the Ollama API.

#### Scenario: Multiple workers respect rate limits
- **WHEN** 4 worker processes simultaneously generate embeddings
- **AND** rate limit is set to 10 requests/second
- **THEN** total embedding requests across all workers stay within 10/second
- **AND** workers queue requests when limit is reached

### Requirement: Backward compatibility maintained
The system SHALL maintain backward compatibility with existing ingestion behavior when multicore options are not used.

#### Scenario: Default behavior unchanged
- **WHEN** user runs `secondbrain ingest /path/to/docs` without any flags
- **THEN** the system behaves identically to previous versions
- **AND** no performance regression is introduced

#### Scenario: Existing batch-size option still works
- **WHEN** user runs `secondbrain ingest /path/to/docs --batch-size 20`
- **THEN** the batch_size parameter functions as before
- **AND** can be combined with `--cores` for fine-tuned control

### Requirement: Cross-platform multiprocessing support
The system SHALL support multiprocessing on Windows, macOS, and Linux.

#### Scenario: Windows compatibility
- **WHEN** user runs `secondbrain ingest /path/to/docs --cores 4` on Windows
- **THEN** the system uses spawn-based multiprocessing
- **AND** all worker functions are properly picklable
- **AND** ingestion completes successfully

#### Scenario: macOS/Linux compatibility
- **WHEN** user runs `secondbrain ingest /path/to/docs --cores 4` on macOS or Linux
- **THEN** the system uses fork-based multiprocessing (more efficient)
- **AND** ingestion completes successfully

### Requirement: Configuration validation for core count
The system SHALL validate core count configuration values and provide helpful error messages.

#### Scenario: Invalid core count rejected
- **WHEN** user runs `secondbrain ingest /path/to/docs --cores 0`
- **THEN** the system displays an error: "cores must be positive"
- **AND** ingestion does not start

#### Scenario: Excessive core count warned
- **WHEN** user runs `secondbrain ingest /path/to/docs --cores 64` on a 16-core machine
- **THEN** the system displays a warning: "Requested 64 cores, but only 16 available"
- **AND** proceeds with 16 cores (or clamps to available count)
