## ADDED Requirements

### Requirement: List Documents
The system SHALL list ingested documents and chunks from the database.

#### Scenario: List all documents
- **WHEN** user runs `secondbrain list`
- **THEN** system returns list of unique source files
- **AND** shows: source_file, chunk_count, file_type, ingested_at

#### Scenario: List chunks for specific file
- **WHEN** user runs `secondbrain list --source file.pdf`
- **THEN** system returns all chunks from that file
- **AND** shows: chunk_id, chunk_index, page_number, text_preview

#### Scenario: List by chunk ID
- **WHEN** user runs `secondbrain list --chunk-id <uuid>`
- **THEN** system returns specific chunk details
- **AND** shows: full text, metadata

#### Scenario: List with pagination
- **WHEN** user runs `secondbrain list --limit 10 --offset 20`
- **THEN** system returns chunks 20-30
- **AND** shows total count for pagination UI

#### Scenario: List empty database
- **WHEN** user runs `secondbrain list` but no documents ingested
- **THEN** system reports "No documents found"
- **AND** suggests running ingest command

### Requirement: Delete Documents
The system SHALL delete documents and chunks from the database.

#### Scenario: Delete by source file
- **WHEN** user runs `secondbrain delete --source file.pdf`
- **THEN** system removes all chunks from that file
- **AND** confirms deletion with count

#### Scenario: Delete specific chunk
- **WHEN** user runs `secondbrain delete --chunk-id <uuid>`
- **THEN** system removes that specific chunk only
- **AND** confirms deletion

#### Scenario: Delete all documents
- **WHEN** user runs `secondbrain delete --all`
- **THEN** system prompts for confirmation
- **AND** removes all documents and embeddings
- **AND** confirms "Database cleared"

#### Scenario: Delete with filter
- **WHEN** user runs `secondbrain delete --file-type pdf`
- **THEN** system removes all PDF document chunks

#### Scenario: Delete confirmation
- **WHEN** user attempts destructive delete
- **THEN** system requires --force flag for non-interactive use
- **AND** warns about data loss

### Requirement: Database Statistics
The system SHALL provide database statistics and health information.

#### Scenario: Show statistics
- **WHEN** user runs `secondbrain status`
- **THEN** system shows:
  - Total documents
  - Total chunks
  - Storage size (approximate)
  - Database connection status

#### Scenario: Index status
- **WHEN** user runs `secondbrain status`
- **THEN** system reports vector index status
- **AND** shows if index is healthy
