## ADDED Requirements

### Requirement: Document Ingestion
The system SHALL allow users to ingest documents from local filesystem paths and generate embeddings stored in MongoDB.

#### Scenario: Ingest single document
- **WHEN** user runs `secondbrain ingest document.pdf`
- **THEN** the system parses the document using Docling
- **AND** extracts text content in chunks
- **AND** generates embeddings using Ollama
- **AND** stores vectors in MongoDB with metadata

#### Scenario: Ingest multiple documents recursively
- **WHEN** user runs `secondbrain ingest /path/to/docs/ --recursive`
- **THEN** the system discovers all supported files in the directory tree
- **AND** processes each document sequentially
- **AND** reports progress for each file
- **AND** handles errors gracefully per file without stopping batch

#### Scenario: Ingest with custom chunk size
- **WHEN** user runs `secondbrain ingest document.pdf --chunk-size 1024`
- **THEN** the system chunks text into 1024-character segments
- **AND** uses 50-character overlap by default (configurable)

#### Scenario: Skip already ingested files
- **WHEN** user runs `secondbrain ingest /path/ --skip-existing`
- **THEN** the system checks if file hash exists in database
- **AND** skips files that have already been ingested
- **AND** reports skipped file count

#### Scenario: Supported document types
- **WHEN** user provides a document file
- **THEN** the system accepts: PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, LaTeX, CSV, Images (PNG, JPEG, TIFF, BMP, WEBP), Audio (WAV, MP3), WebVTT, XML, Docling JSON
- **AND** rejects unsupported formats with clear error message

#### Scenario: Document parsing failure
- **WHEN** user attempts to ingest a corrupted or unreadable file
- **THEN** the system logs the error
- **AND** reports failure to user
- **AND** continues with next file if batch

### Requirement: Batch Processing
The system SHALL process multiple documents in batch mode with progress reporting.

#### Scenario: Progress reporting during batch
- **WHEN** user runs `secondbrain ingest /path/` with 10 files
- **THEN** the system shows progress bar or file count
- **AND** reports completion percentage
- **AND** shows time estimate for remaining files

#### Scenario: Concurrent processing
- **WHEN** user runs `secondbrain ingest /path/ --workers 4`
- **THEN** the system processes up to 4 documents in parallel
- **AND** respects memory constraints

### Requirement: File Type Detection
The system SHALL automatically detect document file types by extension and MIME type.

#### Scenario: Automatic format detection
- **WHEN** user provides file with .pdf extension
- **THEN** system treats it as PDF document
- **AND** uses appropriate Docling converter

#### Scenario: Unknown file type
- **WHEN** user provides file with unknown extension
- **THEN** system rejects with helpful error message
- **AND** lists supported file extensions
