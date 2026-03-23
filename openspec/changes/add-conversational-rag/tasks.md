## 1. Core Module Structure

- [x] 1.1 Create `src/secondbrain/conversation/` module with `__init__.py`
- [x] 1.2 Create `src/secondbrain/rag/` module with `__init__.py`
- [x] 1.3 Define `LocalLLMProvider` protocol in `src/secondbrain/rag/interfaces.py`
- [x] 1.4 Add conversation-related configuration to `src/secondbrain/config/__init__.py`

## 2. Conversation Session Management

- [x] 2.1 Implement `ConversationSession` class in `src/secondbrain/conversation/session.py`
- [x] 2.2 Implement session storage layer in `src/secondbrain/conversation/storage.py`
- [x] 2.3 Create MongoDB schema for `conversations` collection
- [x] 2.4 Implement session CRUD operations (create, read, list, delete)
- [x] 2.5 Implement context window management (truncate to last N turns)
- [x] 2.6 Add session validation and error handling

## 3. Query Rewriting

- [x] 3.1 Implement template-based query rewriter in `src/secondbrain/conversation/rewriter.py`
- [x] 3.2 Create prompt template for query expansion using conversation history
- [x] 3.3 Add logic to detect when rewriting is needed (vs. standalone query)
- [x] 3.4 Write unit tests for query rewriting logic

## 4. Local LLM Provider Integration

- [x] 4.1 Implement `OllamaLLMProvider` class in `src/secondbrain/rag/providers/ollama.py`
- [x] 4.2 Add environment variable configuration for local LLM (endpoint, model, temperature, max tokens, timeout)
- [x] 4.3 Implement sync `generate()` method with HTTP POST to local server
- [x] 4.4 Implement async `agenerate()` method
- [x] 4.5 Implement `health_check()` method to verify local LLM server availability
- [x] 4.6 Add error handling for connection failures, model not found, timeouts
- [x] 4.7 Create factory function to instantiate provider from config (supports ollama, vllm, llama-cpp)
- [x] 4.8 Write unit tests for LLM provider (mock HTTP calls)

## 5. RAG Pipeline Implementation

- [x] 5.1 Implement `RAGPipeline` class in `src/secondbrain/rag/pipeline.py`
- [x] 5.2 Integrate with existing `Searcher` class for document retrieval
- [x] 5.3 Implement context formatting (conversation history + retrieved chunks)
- [x] 5.4 Create RAG prompt template with instructions for grounded answers
- [x] 5.5 Implement answer generation using local LLM provider
- [x] 5.6 Add source attribution and citation formatting
- [x] 5.7 Implement performance tracking (latency, token usage estimation)
- [x] 5.8 Write unit tests for RAG pipeline

## 6. CLI Integration

- [x] 6.1 Add `chat` command to `src/secondbrain/cli/commands.py`
- [x] 6.2 Implement `--session` flag for specifying session ID
- [x] 6.3 Implement `--list-sessions` flag
- [x] 6.4 Implement `--delete-session` flag
- [x] 6.5 Implement `--history` flag for viewing conversation transcript
- [x] 6.6 Implement `--show-sources` flag for displaying retrieved chunks
- [x] 6.7 Create interactive readline loop with Rich formatting
- [x] 6.8 Add session summary display on exit
- [x] 6.9 Implement input validation and error handling
- [x] 6.10 Add help text and examples for chat command
- [x] 6.11 Add `--check-local-llm` flag to verify local LLM server is running

## 7. Configuration and Environment Variables

- [x] 7.1 Add `SECONDBRAIN_RAG_CONTEXT_WINDOW` config option (default: 10)
- [x] 7.2 Add `SECONDBRAIN_CONVERSATION_DB` config option
- [x] 7.3 Add `SECONDBRAIN_LLM_PROVIDER` config option (default: ollama)
- [x] 7.4 Add `SECONDBRAIN_OLLAMA_HOST` config option (default: http://localhost:11434)
- [x] 7.5 Add `SECONDBRAIN_LLM_MODEL` config option (default: llama3.2)
- [x] 7.6 Add `SECONDBRAIN_LLM_TEMPERATURE` config option (default: 0.1)
- [x] 7.7 Add `SECONDBRAIN_LLM_MAX_TOKENS` config option (default: 2048)
- [x] 7.8 Add `SECONDBRAIN_LLM_TIMEOUT` config option (default: 120)
- [x] 7.9 Update documentation with all new environment variables

## 8. Performance Monitoring and Logging

- [x] 8.1 Add logging for RAG operations (retrieval, generation, total latency)
- [x] 8.2 Integrate with existing `perf_monitor` for performance metrics
- [x] 8.3 Log generation parameters (model, temperature, tokens) for debugging
- [x] 8.4 Add structured logging for query/response pairs (opt-in for debugging)
- [x] 8.5 Add local LLM server health check logging

## 9. Testing

- [x] 9.1 Create test fixtures with sample conversation data
- [x] 9.2 Write unit tests for `ConversationSession` class
- [x] 9.3 Write unit tests for query rewriter
- [x] 9.4 Write unit tests for Ollama provider (mock HTTP calls)
- [x] 9.5 Write unit tests for RAG pipeline
- [x] 9.6 Write integration tests for CLI chat command
- [x] 9.7 Write end-to-end test with real Ollama instance (marked as slow)
- [x] 9.8 Add tests for error handling (server down, model not found, timeout)
- [x] 9.9 Add tests for different local LLM backends (ollama, vllm compatibility)

## 10. Documentation

- [x] 10.1 Create `docs/user-guide/conversational-qa.md` with usage guide
- [x] 10.2 Add CLI help text and examples for `secondbrain chat`
- [x] 10.3 Document all configuration options and environment variables
- [x] 10.4 Create setup guide for local LLM servers (Ollama, vLLM, llama.cpp)
- [x] 10.5 Create developer guide for adding new LLM providers
- [x] 10.6 Add architecture diagram showing layered design
- [x] 10.7 Document MCP service conversion path
- [x] 10.8 Add troubleshooting guide for common local LLM issues

## 11. MCP Service Preparation

- [x] 11.1 Extract RAG service into standalone class (CLI-agnostic interface)
- [x] 11.2 Define OpenAPI spec for HTTP API (future reference)
- [x] 11.3 Add async support for concurrent requests
- [x] 11.4 Document MCP protocol mapping (which CLI commands become MCP tools)
- [x] 11.5 Create example MCP server skeleton in `docs/examples/mcp_server.py`

## 12. Dependencies and Setup

- [x] 12.1 Verify httpx is available for HTTP calls (already in dependencies)
- [x] 12.2 Update `README.md` with new chat command
- [x] 12.3 Create `.env.example` with new configuration options
- [x] 12.4 Update installation instructions with local LLM setup guide
- [x] 12.5 Add Ollama installation instructions (macOS, Linux, Windows)
- [x] 12.6 Add model download instructions (`ollama pull llama3.2`)

## 13. Quality Assurance

- [x] 13.1 Run `ruff check .` and fix any linting issues
- [x] 13.2 Run `ruff format .` to format new code
- [x] 13.3 Run `mypy .` and fix type errors
- [x] 13.4 Run `pytest` to ensure all tests pass
- [x] 13.5 Verify backward compatibility (existing `search` command still works)
- [x] 13.6 Test with real documents and local LLM (Ollama)
- [x] 13.7 Performance test: measure latency for typical queries with local model
- [x] 13.8 Security review: validate user inputs, sanitize prompts
- [x] 13.9 Test on different platforms (macOS, Linux, Windows)

## 14. Release Preparation

- [x] 14.1 Update version number in `pyproject.toml`
- [x] 14.2 Add changelog entry in `CHANGELOG.md`
- [x] 14.3 Create release notes highlighting new RAG capabilities with local LLM
- [x] 14.4 Tag release commit with version
- [x] 14.5 Prepare blog post or announcement (optional)
