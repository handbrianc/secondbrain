## ADDED Requirements

### Requirement: Embedding Generation
The system SHALL generate semantic embeddings for text chunks using Ollama with embeddinggemma:latest model.

#### Scenario: Generate embedding for text
- **WHEN** user ingests a document with extracted text
- **THEN** the system chunks text into segments
- **AND** generates embedding vector for each chunk using Ollama API
- **AND** returns 384-dimensional vectors (embeddinggemma output)

#### Scenario: Ollama service unavailable
- **WHEN** user attempts ingestion but Ollama is not running
- **THEN** the system reports connection error
- **AND** suggests checking Docker Compose status
- **AND** does not proceed without valid connection

#### Scenario: Model not pulled
- **WHEN** user runs ingestion but embeddinggemma:latest is not available
- **THEN** the system automatically pulls the model
- **AND** reports pull progress
- **AND** continues with embedding generation

#### Scenario: Embedding cache
- **WHEN** user ingests same document twice
- **THEN** the system regenerates embeddings (no cache for now)
- **AND** allows force regeneration via flag

#### Scenario: Custom embedding model
- **WHEN** user sets SECONDBRAIN_MODEL environment variable
- **THEN** the system uses specified model instead of default
- **AND** validates model is available in Ollama

#### Scenario: Batch embedding generation
- **WHEN** system has multiple chunks to embed
- **THEN** the system sends batches to Ollama API
- **AND** processes efficiently to minimize API calls

### Requirement: Text Chunking
The system SHALL split documents into overlapping text chunks for embedding.

#### Scenario: Fixed-size chunking
- **WHEN** system processes extracted text
- **THEN** it splits into chunks of configurable size (default: 512 chars)
- **AND** applies overlap between chunks (default: 50 chars)

#### Scenario: Preserve semantic boundaries
- **WHEN** chunk would split a sentence
- **THEN** the system prefers to break at sentence boundaries
- **AND** adjusts chunk size to respect natural breaks

#### Scenario: Empty chunk handling
- **WHEN** extracted text is empty or whitespace only
- **THEN** the system skips generating embedding for that chunk
- **AND** logs warning

### Requirement: Ollama Configuration
The system SHALL connect to Ollama via configurable URL and validate connectivity.

#### Scenario: Default Ollama URL
- **WHEN** SECONDBRAIN_OLLAMA_URL is not set
- **THEN** system connects to http://localhost:11434

#### Scenario: Custom Ollama URL
- **WHEN** user sets SECONDBRAIN_OLLAMA_URL to custom URL
- **THEN** system connects to specified URL
- **AND** validates connection before operations

#### Scenario: Connection timeout
- **WHEN** Ollama does not respond within timeout
- **THEN** system reports timeout error
- **AND** allows retry
