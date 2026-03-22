## 1. Core Module Structure

- [ ] 1.1 Create `src/secondbrain/conversation/` module with `__init__.py`
- [ ] 1.2 Create `src/secondbrain/rag/` module with `__init__.py`
- [ ] 1.3 Define `LLMProvider` protocol in `src/secondbrain/rag/interfaces.py`
- [ ] 1.4 Add conversation-related configuration to `src/secondbrain/config/__init__.py`

## 2. Conversation Session Management

- [ ] 2.1 Implement `ConversationSession` class in `src/secondbrain/conversation/session.py`
- [ ] 2.2 Implement session storage layer in `src/secondbrain/conversation/storage.py`
- [ ] 2.3 Create MongoDB schema for `conversations` collection
- [ ] 2.4 Implement session CRUD operations (create, read, list, delete)
- [ ] 2.5 Implement context window management (truncate to last N turns)
- [ ] 2.6 Add session validation and error handling

## 3. Query Rewriting

- [ ] 3.1 Implement template-based query rewriter in `src/secondbrain/conversation/rewriter.py`
- [ ] 3.2 Create prompt template for query expansion using conversation history
- [ ] 3.3 Add logic to detect when rewriting is needed (vs. standalone query)
- [ ] 3.4 Write unit tests for query rewriting logic

## 4. LLM Provider Integration

- [ ] 4.1 Implement `OpenAILLMProvider` class in `src/secondbrain/rag/providers/openai.py`
- [ ] 4.2 Add environment variable configuration for OpenAI API key and model
- [ ] 4.3 Implement sync `generate()` method
- [ ] 4.4 Implement async `agenerate()` method
- [ ] 4.5 Add error handling for API failures and rate limiting
- [ ] 4.6 Create factory function to instantiate provider from config

## 5. RAG Pipeline Implementation

- [ ] 5.1 Implement `RAGPipeline` class in `src/secondbrain/rag/pipeline.py`
- [ ] 5.2 Integrate with existing `Searcher` class for document retrieval
- [ ] 5.3 Implement context formatting (conversation history + retrieved chunks)
- [ ] 5.4 Create RAG prompt template with instructions for grounded answers
- [ ] 5.5 Implement answer generation using LLM provider
- [ ] 5.6 Add source attribution and citation formatting
- [ ] 5.7 Implement performance tracking (latency, token usage)
- [ ] 5.8 Write unit tests for RAG pipeline

## 6. CLI Integration

- [ ] 6.1 Add `chat` command to `src/secondbrain/cli/commands.py`
- [ ] 6.2 Implement `--session` flag for specifying session ID
- [ ] 6.3 Implement `--list-sessions` flag
- [ ] 6.4 Implement `--delete-session` flag
- [ ] 6.5 Implement `--history` flag for viewing conversation transcript
- [ ] 6.6 Implement `--show-sources` flag for displaying retrieved chunks
- [ ] 6.7 Create interactive readline loop with Rich formatting
- [ ] 6.8 Add session summary display on exit
- [ ] 6.9 Implement input validation and error handling
- [ ] 6.10 Add help text and examples for chat command

## 7. Configuration and Environment Variables

- [ ] 7.1 Add `SECONDBRAIN_RAG_CONTEXT_WINDOW` config option
- [ ] 7.2 Add `SECONDBRAIN_CONVERSATION_DB` config option
- [ ] 7.3 Add `SECONDBRAIN_LLM_PROVIDER` config option
- [ ] 7.4 Add `SECONDBRAIN_OPENAI_API_KEY` config option
- [ ] 7.5 Add `SECONDBRAIN_OPENAI_MODEL` config option (default: gpt-4o-mini)
- [ ] 7.6 Add `SECONDBRAIN_RAG_TEMPERATURE` config option (default: 0.7)
- [ ] 7.7 Update documentation with new environment variables

## 8. Performance Monitoring and Logging

- [ ] 8.1 Add logging for RAG operations (retrieval, generation, total latency)
- [ ] 8.2 Integrate with existing `perf_monitor` for performance metrics
- [ ] 8.3 Log token usage for cost tracking
- [ ] 8.4 Add structured logging for query/response pairs (opt-in for debugging)

## 9. Testing

- [ ] 9.1 Create test fixtures with sample conversation data
- [ ] 9.2 Write unit tests for `ConversationSession` class
- [ ] 9.3 Write unit tests for query rewriter
- [ ] 9.4 Write unit tests for LLM provider (mock API calls)
- [ ] 9.5 Write unit tests for RAG pipeline
- [ ] 9.6 Write integration tests for CLI chat command
- [ ] 9.7 Write end-to-end test with real LLM API (marked as slow)
- [ ] 9.8 Add tests for error handling scenarios

## 10. Documentation

- [ ] 10.1 Create `docs/user-guide/conversational-rag.md` with usage guide
- [ ] 10.2 Add CLI help text and examples for `secondbrain chat`
- [ ] 10.3 Document configuration options and environment variables
- [ ] 10.4 Create developer guide for adding new LLM providers
- [ ] 10.5 Add architecture diagram showing layered design
- [ ] 10.6 Document MCP service conversion path

## 11. MCP Service Preparation

- [ ] 11.1 Extract RAG service into standalone class (CLI-agnostic interface)
- [ ] 11.2 Define OpenAPI spec for HTTP API (future reference)
- [ ] 11.3 Add async support for concurrent requests
- [ ] 11.4 Document MCP protocol mapping (which CLI commands become MCP tools)
- [ ] 11.5 Create example MCP server skeleton in `docs/examples/mcp_server.py`

## 12. Dependencies and Setup

- [ ] 12.1 Add OpenAI SDK to `pyproject.toml` dependencies
- [ ] 12.2 Add optional dependencies for alternative providers (anthropic, etc.)
- [ ] 12.3 Update `README.md` with new chat command
- [ ] 12.4 Create `.env.example` with new configuration options
- [ ] 12.5 Update installation instructions with new dependencies

## 13. Quality Assurance

- [ ] 13.1 Run `ruff check .` and fix any linting issues
- [ ] 13.2 Run `ruff format .` to format new code
- [ ] 13.3 Run `mypy .` and fix type errors
- [ ] 13.4 Run `pytest` to ensure all tests pass
- [ ] 13.5 Verify backward compatibility (existing `search` command still works)
- [ ] 13.6 Test with real documents and LLM API
- [ ] 13.7 Performance test: measure latency for typical queries
- [ ] 13.8 Security review: validate user inputs, sanitize prompts

## 14. Release Preparation

- [ ] 14.1 Update version number in `pyproject.toml`
- [ ] 14.2 Add changelog entry in `CHANGELOG.md`
- [ ] 14.3 Create release notes highlighting new RAG capabilities
- [ ] 14.4 Tag release commit with version
- [ ] 14.5 Prepare blog post or announcement (optional)
