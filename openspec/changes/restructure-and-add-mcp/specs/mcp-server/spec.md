## ADDED Requirements

### Requirement: MCP server exposes list_tools endpoint
The MCP server SHALL implement the `list_tools` method returning all available tools with their schemas.

#### Scenario: Client requests tool list
- **WHEN** MCP client calls `list_tools`
- **THEN** server returns array of tools including: ingest, search, chat, ls, delete, health, status, metrics
- **AND** each tool includes name, description, and inputSchema

### Requirement: Ingest tool accepts file path and options
The `ingest` tool SHALL accept document path and optional parameters for ingestion configuration.

#### Scenario: Ingest single file
- **WHEN** client calls `ingest` with `{"path": "/path/to/file.pdf"}`
- **THEN** document is processed and embedded
- **AND** response includes count of chunks created

#### Scenario: Ingest with recursive option
- **WHEN** client calls `ingest` with `{"path": "/path/to/dir", "recursive": true}`
- **THEN** all supported files in directory tree are processed
- **AND** response includes total files processed

#### Scenario: Ingest with custom chunk size
- **WHEN** client calls `ingest` with `{"path": "/file.pdf", "chunk_size": 500}`
- **THEN** document is chunked with 500 character chunks
- **AND** chunk overlap uses default unless specified

### Requirement: Search tool performs semantic search
The `search` tool SHALL accept a query and return relevant document chunks.

#### Scenario: Basic semantic search
- **WHEN** client calls `search` with `{"query": "machine learning"}`
- **THEN** server performs vector similarity search
- **AND** returns top-k results with chunk text, source file, and relevance score

#### Scenario: Search with custom top_k
- **WHEN** client calls `search` with `{"query": "API design", "top_k": 10}`
- **THEN** server returns 10 most relevant chunks
- **AND** results ordered by similarity score

### Requirement: Chat tool provides RAG-enhanced conversation
The `chat` tool SHALL accept a query and return LLM-generated answer with sources.

#### Scenario: Single-turn chat
- **WHEN** client calls `chat` with `{"query": "What is secondbrain?"}`
- **THEN** server retrieves relevant chunks via search
- **AND** passes context to LLM
- **AND** returns answer with optional source citations

#### Scenario: Chat with session context
- **WHEN** client calls `chat` with `{"query": "Tell me more", "session_id": "default"}`
- **THEN** conversation history is loaded
- **AND** response considers prior turns
- **AND** response is saved to session history

#### Scenario: Chat with temperature control
- **WHEN** client calls `chat` with `{"query": "Explain", "temperature": 0.7}`
- **THEN** LLM generates response with specified creativity
- **AND** higher temperature produces more varied outputs

### Requirement: List tool displays ingested documents
The `ls` tool SHALL return metadata about ingested documents and chunks.

#### Scenario: List all documents
- **WHEN** client calls `ls` with `{"type": "document"}`
- **THEN** server returns array of documents with: id, filename, ingest_date, chunk_count

#### Scenario: List chunks
- **WHEN** client calls `ls` with `{"type": "chunk", "limit": 50}`
- **THEN** server returns up to 50 chunks with: id, source_file, page_number, text_preview

### Requirement: Delete tool removes documents or chunks
The `delete` tool SHALL accept deletion criteria and remove matching data.

#### Scenario: Delete by document ID
- **WHEN** client calls `delete` with `{"type": "document", "id": "doc_123"}`
- **THEN** document and all its chunks are removed from database
- **AND** response confirms deletion count

#### Scenario: Delete by filename pattern
- **WHEN** client calls `delete` with `{"type": "document", "filename_pattern": "*.tmp"}`
- **THEN** all matching documents are deleted
- **AND** response includes list of deleted filenames

### Requirement: Health tool checks service status
The `health` tool SHALL verify connectivity to all required services.

#### Scenario: All services healthy
- **WHEN** client calls `health`
- **THEN** server checks MongoDB, Ollama, embedding model
- **AND** returns `{"status": "healthy", "services": {...}}`

#### Scenario: Service unavailable
- **WHEN** MongoDB is down
- **THEN** health check returns `{"status": "unhealthy", "services": {"mongodb": "down", ...}}`
- **AND** includes error details for failed services

### Requirement: Status tool returns database statistics
The `status` tool SHALL provide counts and statistics about the vector database.

#### Scenario: Get database status
- **WHEN** client calls `status`
- **THEN** server returns: total_documents, total_chunks, storage_size, index_info

### Requirement: Metrics tool returns performance data
The `metrics` tool SHALL provide performance metrics for recent operations.

#### Scenario: Get ingestion metrics
- **WHEN** client calls `metrics` with `{"type": "ingestion"}`
- **THEN** server returns: avg_processing_time, files_per_minute, error_rate

#### Scenario: Get search metrics
- **WHEN** client calls `metrics` with `{"type": "search"}`
- **THEN** server returns: avg_query_time, cache_hit_rate, top_queries

### Requirement: MCP tools return structured responses
All MCP tool responses SHALL follow the MCP TextContent format.

#### Scenario: Successful tool execution
- **WHEN** tool executes successfully
- **THEN** response is `{"content": [{"type": "text", "text": "..." }]}`

#### Scenario: Tool execution error
- **WHEN** tool encounters error
- **THEN** response includes error in text content
- **AND** error message is user-friendly and actionable

### Requirement: MCP server handles concurrent requests
The MCP server SHALL process multiple tool calls concurrently where safe.

#### Scenario: Parallel search requests
- **WHEN** multiple `search` tool calls arrive simultaneously
- **THEN** all requests are processed in parallel
- **AND** responses are returned independently

### Requirement: MCP tools validate input parameters
All MCP tools SHALL validate input against their schemas before execution.

#### Scenario: Invalid parameter type
- **WHEN** client calls `search` with `{"query": 123}` (number instead of string)
- **THEN** server returns validation error
- **AND** error message indicates expected type

#### Scenario: Missing required parameter
- **WHEN** client calls `ingest` without `path` parameter
- **THEN** server returns validation error
- **AND** error message lists required parameters

### Requirement: MCP server uses same core logic as CLI
MCP tools SHALL invoke the same functions as CLI commands.

#### Scenario: Consistent ingestion behavior
- **WHEN** CLI `ingest` and MCP `ingest` process same file
- **THEN** both produce identical chunks and embeddings
- **AND** database state is identical regardless of entry point

#### Scenario: Consistent search results
- **WHEN** CLI `search` and MCP `search` run same query
- **THEN** both return identical results in same order
- **AND** relevance scores match exactly
