## ADDED Requirements

### Requirement: RAG pipeline orchestration
The system SHALL orchestrate retrieval and generation in a single pipeline.

#### Scenario: End-to-end query processing
- **WHEN** user submits a question
- **THEN** system rewrites query with context (if applicable)
- **AND** retrieves top-K chunks from vector store
- **AND** formats context for LLM prompt
- **AND** generates answer using LLM
- **AND** returns answer with optional sources

### Requirement: Pluggable LLM provider
The system SHALL support multiple LLM providers through a common interface.

#### Scenario: Use OpenAI provider
- **WHEN** `SECONDBRAIN_LLM_PROVIDER=openai`
- **AND** `SECONDBRAIN_OPENAI_API_KEY` is set
- **THEN** system uses OpenAI API for generation
- **AND** defaults to `gpt-4o-mini` model

#### Scenario: Use alternative provider
- **WHEN** `SECONDBRAIN_LLM_PROVIDER=anthropic`
- **AND** `SECONDBRAIN_ANTHROPIC_API_KEY` is set
- **THEN** system uses Anthropic API for generation
- **AND** defaults to `claude-3-haiku` model

### Requirement: Context formatting for LLM
The system SHALL format retrieved chunks and conversation history into LLM prompts.

#### Scenario: Build RAG prompt
- **WHEN** system prepares prompt for LLM
- **THEN** prompt includes conversation history (up to context window)
- **AND** prompt includes retrieved chunks with source attribution
- **AND** prompt includes user's current query
- **AND** prompt instructs LLM to use context only

#### Scenario: Handle no retrieved chunks
- **WHEN** vector search returns zero results
- **THEN** system informs LLM "No relevant documents found"
- **AND** LLM responds that it cannot answer from knowledge base

### Requirement: Retrieval integration
The system SHALL reuse existing semantic search infrastructure for document retrieval.

#### Scenario: Use existing Searcher
- **WHEN** RAG pipeline needs to retrieve documents
- **THEN** system calls existing `Searcher.search()` method
- **AND** uses user query (rewritten if applicable)
- **AND** respects existing filters (source, file type)

### Requirement: Answer generation
The system SHALL generate answers based on retrieved context and conversation history.

#### Scenario: Generate grounded answer
- **WHEN** LLM receives prompt with context
- **THEN** LLM generates answer based on context only
- **AND** acknowledges if answer not found in context
- **AND** includes citations to source documents

#### Scenario: Handle ambiguous queries
- **WHEN** user query is unclear or ambiguous
- **THEN** LLM asks clarifying question
- **AND** conversation continues with clarification

### Requirement: Performance monitoring
The system SHALL track latency and token usage for RAG operations.

#### Scenario: Log performance metrics
- **WHEN** query completes
- **THEN** system logs: retrieval latency, generation latency, total latency
- **AND** logs token usage (prompt tokens, completion tokens)
- **AND** stores metrics in performance monitor

### Requirement: Async support
The system SHALL support async operations for concurrent requests.

#### Scenario: Async query execution
- **WHEN** called from async context (future MCP server)
- **THEN** system uses async LLM provider methods
- **AND** async MongoDB operations for session storage
- **AND** returns awaitable future
