## Why

Users currently have semantic search capability but lack conversational Q&A on ingested content. Adding RAG (Retrieval Augmented Generation) enables natural multi-turn conversations where context is preserved across queries, transforming the CLI from a search tool into an intelligent document assistant. This positions the system for future MCP service conversion, allowing the same RAG capabilities to be exposed as a service API.

## What Changes

- **New conversational Q&A capability**: Multi-turn dialogue with context preservation across queries
- **New RAG pipeline layer**: Separates retrieval from generation, supporting pluggable LLM providers
- **New CLI command**: `secondbrain chat` for interactive conversational mode
- **New session management**: Persistent conversation history stored in MongoDB
- **New query rewriting**: Context-aware query expansion using conversation history
- **Architecture refactor**: Core RAG logic decoupled from presentation layer (CLI/MCP-agnostic)
- **Future MCP readiness**: Service layer designed for easy conversion to MCP protocol

## Capabilities

### New Capabilities

- **conversational-rag**: Multi-turn Q&A with context preservation, query rewriting, and RAG pipeline
  - Session management for conversation history
  - Context-aware query expansion
  - Pluggable LLM interface for answer generation
  - Support for both CLI and future MCP service interfaces

- **rag-pipeline**: Core RAG orchestration layer
  - Retrieval from existing vector store (MongoDB)
  - Context formatting and prompt engineering
  - LLM integration with provider abstraction
  - Separation of retrieval logic from generation logic

### Modified Capabilities

- *No existing capabilities modified* - All new functionality is additive; existing semantic search (`search` command) remains unchanged

## Impact

**Code**:
- New module: `src/secondbrain/conversation/` (session management, query rewriting)
- New module: `src/secondbrain/rag/` (RAG pipeline, local LLM interface abstraction)
- New CLI command: `chat` in `src/secondbrain/cli/commands.py`
- Modified: `src/secondbrain/storage/storage.py` (new conversation collection schema)

**Dependencies**:
- Add HTTP client for local LLM API calls (httpx already available)
- Add conversation memory library (LangChain Memory or custom implementation)
- **No cloud LLM SDK dependencies** - all local via standard HTTP APIs
- Optional: Cross-encoder reranker for improved retrieval quality

**Configuration (12-Factor)**:
All LLM configuration via environment variables with sensible defaults:
- `SECONDBRAIN_LLM_PROVIDER`: Backend type (ollama, vllm, llama-cpp, etc.)
- `SECONDBRAIN_LLM_ENDPOINT`: Local model server URL
- `SECONDBRAIN_LLM_MODEL`: Model name/identifier
- `SECONDBRAIN_LLM_TEMPERATURE`: Generation temperature (0.0-2.0)
- `SECONDBRAIN_LLM_MAX_TOKENS`: Maximum response tokens
- `SECONDBRAIN_LLM_TIMEOUT`: Request timeout in seconds

**APIs**:
- New `ConversationSession` class for state management
- New `RAGPipeline` class for retrieval + generation orchestration
- New `LocalLLMProvider` protocol/interface for pluggable local backends

**Systems**:
- MongoDB: New `conversations` collection for session storage
- Local LLM server: External backing service (Ollama, vLLM, etc.)
- No changes to existing ingestion or vector search infrastructure
