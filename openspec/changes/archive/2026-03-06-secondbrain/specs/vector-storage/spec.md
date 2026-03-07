## ADDED Requirements

### Requirement: Vector Storage
The system SHALL store embedding vectors in MongoDB with complete metadata.

#### Scenario: Store embedding with metadata
- **WHEN** system generates embedding for a chunk
- **THEN** it stores in MongoDB:
  - chunk_id (UUID)
  - source_file (filename)
  - page_number (if applicable)
  - chunk_text (the text content)
  - embedding (384-dim vector)
  - metadata (file_type, ingested_at, chunk_index)

#### Scenario: MongoDB connection
- **WHEN** system needs to store vectors
- **THEN** it connects to MongoDB using SECONDBRAIN_MONGO_URI
- **AND** uses database name from SECONDBRAIN_MONGO_DB (default: "secondbrain")
- **AND** uses collection from SECONDBRAIN_MONGO_COLLECTION (default: "embeddings")

#### Scenario: Create vector index
- **WHEN** system stores first embedding
- **THEN** it creates vector search index on embedding field
- **AND** uses cosine similarity metric

#### Scenario: Connection failure
- **WHEN** MongoDB is not available
- **THEN** system reports connection error
- **AND** suggests checking Docker Compose status
- **AND** does not proceed without valid connection

#### Scenario: Duplicate handling
- **WHEN** user ingests same file again
- **THEN** system creates new entries (allows duplicates)
- **OR** optionally replaces existing (--replace flag)

#### Scenario: Bulk insert
- **WHEN** system has multiple embeddings to store
- **THEN** it uses bulk insert for efficiency
- **AND** commits in batches

### Requirement: Metadata Storage
The system SHALL store comprehensive metadata alongside embeddings.

#### Scenario: File metadata
- **WHEN** system stores document embedding
- **THEN** it records:
  - source_file (full path or filename)
  - file_type (pdf, docx, etc.)
  - file_size (bytes)
  - file_hash (SHA256 for deduplication)
  - ingested_at (timestamp)

#### Scenario: Chunk metadata
- **WHEN** system stores chunk embedding
- **THEN** it records:
  - chunk_index (position in document)
  - chunk_text (content)
  - page_number (if PDF/DOCX)
  - char_count (text length)

### Requirement: MongoDB Configuration
The system SHALL use environment variables for all MongoDB configuration.

#### Scenario: Default MongoDB URI
- **WHEN** SECONDBRAIN_MONGO_URI is not set
- **THEN** system uses mongodb://localhost:27017

#### Scenario: Custom database name
- **WHEN** user sets SECONDBRAIN_MONGO_DB
- **THEN** system uses specified database

#### Scenario: Collection configuration
- **WHEN** user sets SECONDBRAIN_MONGO_COLLECTION
- **THEN** system uses specified collection

#### Scenario: Connection validation
- **WHEN** system starts any operation
- **THEN** it validates MongoDB connectivity first
- **AND** reports clear error if unavailable
