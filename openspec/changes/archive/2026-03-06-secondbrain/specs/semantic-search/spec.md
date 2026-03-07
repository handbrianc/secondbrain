## ADDED Requirements

### Requirement: Semantic Search
The system SHALL perform semantic search using cosine similarity on stored embeddings.

#### Scenario: Search with text query
- **WHEN** user runs `secondbrain search "query text"`
- **THEN** system generates embedding for query text
- **AND** performs cosine similarity search in MongoDB
- **AND** returns top-k results (default: 5)

#### Scenario: Custom result count
- **WHEN** user runs `secondbrain search "query" --top-k 10`
- **THEN** system returns top 10 results instead of default

#### Scenario: Search results format
- **WHEN** user performs search
- **THEN** results include:
  - chunk_text (matching text)
  - source_file (file it came from)
  - page_number (if available)
  - score (similarity score 0-1)

#### Scenario: Empty results
- **WHEN** search query has no similar results
- **THEN** system returns empty list
- **AND** reports "No results found"

#### Scenario: Search with filters
- **WHEN** user runs `secondbrain search "query" --source file.pdf`
- **THEN** system filters results to specific source file only

### Requirement: Search Result Display
The system SHALL format and display search results clearly.

#### Scenario: Default display
- **WHEN** user performs search without flags
- **THEN** results show:
  - Rank (1, 2, 3...)
  - Source file
  - Page number (if available)
  - Score (percentage)
  - Text preview (truncated to 200 chars)

#### Scenario: Verbose display
- **WHEN** user runs `secondbrain search "query" --verbose`
- **THEN** results show full text content
- **AND** all metadata

#### Scenario: JSON output
- **WHEN** user runs `secondbrain search "query" --json`
- **THEN** results output as JSON for scripting

### Requirement: Search Performance
The system SHALL optimize search for fast response times.

#### Scenario: Vector index usage
- **WHEN** system performs search
- **THEN** it uses MongoDB vector search index
- **AND** returns results within 1 second for <10k chunks

#### Scenario: Query embedding
- **WHEN** user submits search query
- **THEN** system generates embedding via Ollama
- **AND** uses same model as ingestion
