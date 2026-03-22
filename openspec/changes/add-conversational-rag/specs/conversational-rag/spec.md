## ADDED Requirements

### Requirement: Create conversation session
The system SHALL create a new conversation session with a unique identifier when the user initiates a chat.

#### Scenario: Create new session
- **WHEN** user runs `secondbrain chat` without specifying a session ID
- **THEN** system creates a new session with UUID
- **AND** session is stored in MongoDB `conversations` collection
- **AND** system displays the session ID to the user

#### Scenario: Resume existing session
- **WHEN** user runs `secondbrain chat --session <session-id>`
- **AND** session ID exists in MongoDB
- **THEN** system loads conversation history
- **AND** displays summary of previous turns

### Requirement: Multi-turn conversation
The system SHALL preserve conversation context across multiple user queries within a session.

#### Scenario: User asks follow-up question
- **WHEN** user asks a second question referencing the first
- **THEN** system includes previous conversation turns in context
- **AND** answer reflects understanding of conversation history

#### Scenario: Context window limit
- **WHEN** conversation exceeds configured context window (default: 5 turns)
- **THEN** system uses only the most recent N turns for context
- **AND** full history remains stored in MongoDB

### Requirement: Query rewriting with context
The system SHALL rewrite user queries to include conversation context for better retrieval.

#### Scenario: Contextual query expansion
- **WHEN** user asks "What about the pricing?" after discussing "ACME contract"
- **THEN** system rewrites query to "ACME contract pricing"
- **AND** uses rewritten query for vector search

#### Scenario: Standalone query (no context needed)
- **WHEN** user asks a completely new question unrelated to conversation
- **THEN** system uses query as-is without rewriting
- **AND** retrieval proceeds normally

### Requirement: Display conversation sources
The system SHALL show retrieved document sources used for generating answers.

#### Scenario: Show sources flag enabled
- **WHEN** user runs with `--show-sources` flag
- **AND** system retrieves chunks for the query
- **THEN** system displays source file names and page numbers
- **AND** shows similarity scores for each chunk

#### Scenario: Show sources flag disabled (default)
- **WHEN** user runs without `--show-sources` flag
- **THEN** system displays only the answer
- **AND** sources are stored internally for debugging

### Requirement: Session management commands
The system SHALL provide commands to list, view, and delete conversation sessions.

#### Scenario: List all sessions
- **WHEN** user runs `secondbrain chat --list-sessions`
- **THEN** system displays table with session IDs, creation dates, and message counts

#### Scenario: View session history
- **WHEN** user runs `secondbrain chat --session <id> --history`
- **THEN** system displays full conversation transcript

#### Scenario: Delete session
- **WHEN** user runs `secondbrain chat --delete-session <id>`
- **AND** confirms deletion
- **THEN** system removes session from MongoDB
- **AND** displays confirmation message

### Requirement: Interactive chat mode
The system SHALL support interactive multi-turn conversation in a single CLI invocation.

#### Scenario: Enter interactive mode
- **WHEN** user runs `secondbrain chat`
- **THEN** system enters readline loop
- **AND** displays prompt with session ID
- **AND** waits for user input

#### Scenario: Exit interactive mode
- **WHEN** user types "exit" or presses Ctrl+D
- **THEN** system saves final conversation state
- **AND** displays session summary
- **AND** returns to shell prompt

#### Scenario: User input validation
- **WHEN** user submits empty query
- **THEN** system displays error message
- **AND** prompts for new input without saving

### Requirement: Configuration options
The system SHALL support configuration via environment variables and CLI flags following 12-factor principles.

#### Scenario: Set local LLM provider
- **WHEN** user sets `SECONDBRAIN_LLM_PROVIDER=ollama`
- **THEN** system uses Ollama as the LLM backend
- **AND** defaults to endpoint `http://localhost:11434`

#### Scenario: Set custom LLM endpoint
- **WHEN** user sets `SECONDBRAIN_LLM_ENDPOINT=http://localhost:8000/v1`
- **THEN** system connects to custom endpoint (e.g., vLLM)
- **AND** overrides default Ollama endpoint

#### Scenario: Set LLM model
- **WHEN** user sets `SECONDBRAIN_LLM_MODEL=llama3.2`
- **THEN** system uses specified model for generation
- **AND** defaults to `llama3.2` if not set

#### Scenario: Set context window size
- **WHEN** user sets `SECONDBRAIN_RAG_CONTEXT_WINDOW=10`
- **THEN** system uses 10 turns for context window
- **AND** overrides default value of 5

#### Scenario: Set session storage location
- **WHEN** user sets `SECONDBRAIN_CONVERSATION_DB` to custom MongoDB URI
- **THEN** system stores sessions in specified database
- **AND** defaults to `secondbrain.conversations` if not set

#### Scenario: Set LLM generation parameters
- **WHEN** user sets `SECONDBRAIN_LLM_TEMPERATURE=0.8`
- **AND** `SECONDBRAIN_LLM_MAX_TOKENS=2048`
- **THEN** system uses these parameters for generation
- **AND** defaults to 0.7 temperature and 4096 max tokens

### Requirement: Error handling
The system SHALL handle errors gracefully and provide actionable feedback.

#### Scenario: Invalid session ID
- **WHEN** user specifies non-existent session ID
- **THEN** system displays error: "Session not found: <id>"
- **AND** suggests creating new session with `--create` flag

#### Scenario: Local LLM server unavailable
- **WHEN** local LLM server at configured endpoint is unreachable
- **THEN** system displays: "Local LLM server unavailable at <endpoint>"
- **AND** provides instructions: "Start your LLM server (e.g., 'ollama serve') and ensure SECONDBRAIN_LLM_ENDPOINT is correct"
- **AND** offers retry option or graceful exit

#### Scenario: Model not found
- **WHEN** configured model is not available on local server
- **THEN** system displays: "Model '<model>' not found on LLM server"
- **AND** suggests: "Pull the model: ollama pull <model>" or "Set SECONDBRAIN_LLM_MODEL to available model"

#### Scenario: MongoDB connection failure
- **WHEN** cannot connect to MongoDB for session storage
- **THEN** system displays: "Session storage unavailable"
- **AND** suggests checking MongoDB connection

## ADDED Requirements (RAG Pipeline)

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
