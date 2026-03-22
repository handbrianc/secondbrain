## Context

**Background**: SecondBrain currently provides semantic search via vector embeddings stored in MongoDB. Users can ingest documents and perform one-off semantic queries, but each query is stateless with no conversation history or context preservation.

**Current State**:
- Document ingestion pipeline (docling → chunking → embeddings → MongoDB)
- Semantic search via `secondbrain search <query>` (stateless, no history)
- Vector storage in MongoDB Atlas with cosine similarity
- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)

**Constraints**:
- Must maintain backward compatibility with existing `search` command
- Must work with existing MongoDB infrastructure (no new vector DB required)
- Must support future MCP service conversion without major refactoring
- CLI must remain responsive (async/await where appropriate)

**Stakeholders**:
- CLI users (current and future)
- MCP service consumers (future)
- Development team (maintainability, testability)

## Goals / Non-Goals

**Goals:**
1. Enable multi-turn conversational Q&A with context preservation
2. Separate RAG orchestration logic from presentation layer (CLI/MCP-agnostic)
3. Provide pluggable LLM interface for answer generation
4. Store conversation history in MongoDB for persistence
5. Implement query rewriting using conversation context
6. Design for easy MCP service conversion (HTTP API + MCP protocol)

**Non-Goals:**
1. Replacing existing semantic search (remains as standalone feature)
2. Adding new vector database (reuse existing MongoDB)
3. Implementing advanced retrieval strategies (multi-query, reranking) in v1
4. Supporting real-time streaming responses
5. Adding user authentication/authorization (single-user CLI focus for now)
6. Building web UI (CLI only, MCP service for other interfaces)

## Decisions

### 1. Architecture: Layered Service Pattern

**Decision**: Implement a three-layer architecture:
```
Presentation Layer (CLI/MCP)
         ↓
RAG Service Layer (framework-agnostic)
         ↓
Retrieval Layer (existing Searcher + Storage)
```

**Rationale**: 
- **Why**: Production RAG systems (LangChain, LlamaIndex) separate orchestration from retrieval and presentation. This enables the same RAG logic to serve multiple interfaces (CLI now, MCP later).
- **Alternative considered**: Monolithic CLI command with embedded RAG logic
- **Why rejected**: Would require rewriting for MCP conversion; violates separation of concerns

**Reference**: LangChain's LCEL (LangChain Expression Language) pattern - retriever is independent chain component.

### 2. Local LLM Provider Abstraction

**Decision**: Define `LocalLLMProvider` protocol with `generate(prompt: str) -> str` method. Default to Ollama, but design for any OpenAI-compatible local server.

**Rationale**:
- **Why**: Local models align with 12-factor principles (backing service), work offline, no API costs, data privacy.
- **Supported backends**: Ollama, vLLM, llama.cpp server, LM Studio, Text-Generation-WebUI
- **Alternative considered**: Cloud APIs (OpenAI, Anthropic)
- **Why rejected**: Requires internet, ongoing costs, data leaves system, vendor lock-in

**Interface**:
```python
class LocalLLMProvider(Protocol):
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str: ...
    async def agenerate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str: ...
    
    # Health check for 12-factor backing service pattern
    def health_check(self) -> bool: ...
```

**12-Factor Configuration**:
```python
# All configuration via environment variables
config = {
    "provider": os.getenv("SECONDBRAIN_LLM_PROVIDER", "ollama"),
    "endpoint": os.getenv("SECONDBRAIN_LLM_ENDPOINT", "http://localhost:11434"),
    "model": os.getenv("SECONDBRAIN_LLM_MODEL", "llama3.2"),
    "temperature": float(os.getenv("SECONDBRAIN_LLM_TEMPERATURE", "0.7")),
    "max_tokens": int(os.getenv("SECONDBRAIN_LLM_MAX_TOKENS", "4096")),
    "timeout": int(os.getenv("SECONDBRAIN_LLM_TIMEOUT", "120")),  # Local models can be slow
}
```

**Provider-Specific Endpoints**:
| Provider | Default Endpoint | Notes |
|----------|-----------------|-------|
| Ollama | `http://localhost:11434` | Most popular, easy setup |
| vLLM | `http://localhost:8000/v1` | High throughput, production |
| llama.cpp | `http://localhost:8080` | Lightweight, CPU-friendly |
| LM Studio | `http://localhost:1234` | GUI + API, Windows/Mac |

### 3. Conversation Storage Schema

**Decision**: Store conversations in MongoDB collection `conversations` with schema:
```python
{
    "session_id": "uuid4",
    "user_id": "default",  # Placeholder for future auth
    "messages": [
        {
            "role": "user|assistant|system",
            "content": str,
            "timestamp": ISO8601,
            "retrieved_chunks": list[str] | None  # Optional: chunk IDs for reference
        }
    ],
    "created_at": ISO8601,
    "updated_at": ISO8601,
    "metadata": {
        "source_files": list[str],  # Documents referenced in conversation
        "topic": str | None  # Optional auto-classification
    }
}
```

**Rationale**:
- **Why**: Flexible schema supports arbitrary conversation lengths. `retrieved_chunks` enables traceability and debugging.
- **Alternative considered**: Separate collections for sessions and messages
- **Why rejected**: Adds query complexity; single document per session is simpler for CLI use case

### 4. Query Rewriting Strategy

**Decision**: v1 uses template-based query rewriting. Future v2 can upgrade to ML-based rewriter.

**Template approach**:
```
Conversation Context:
{last_N_turns}

Current Question: {user_query}

Rewrite as standalone question that preserves context:
```

**Rationale**:
- **Why**: Simple, no additional model required, leverages same LLM used for answer generation.
- **Alternative considered**: Dedicated query rewriter model (e.g., sentence-transformers fine-tuned for rewriting)
- **Why rejected**: Adds complexity and dependency; template approach sufficient for v1

### 5. Context Window Management

**Decision**: Limit conversation context to last 5 turns (10 messages) in RAG prompts. Use MongoDB full history for persistence.

**Rationale**:
- **Why**: Prevents context explosion in LLM prompts. 5 turns is sufficient for most conversations while staying within token limits.
- **Alternative considered**: Unlimited history with summarization
- **Why rejected**: Summarization adds complexity; fixed window is predictable and simple

**Configuration**: `SECONDBRAIN_RAG_CONTEXT_WINDOW=5` (default)

### 6. Retrieval Integration

**Decision**: Reuse existing `Searcher` class for retrieval. New `RAGPipeline` wraps search results into LLM context.

**Rationale**:
- **Why**: Leverages existing, tested vector search infrastructure. No duplication of retrieval logic.
- **Alternative considered**: New retrieval implementation in RAG module
- **Why rejected**: Unnecessary; existing `Searcher` already handles embedding generation, vector search, filtering

### 7. Dependency Strategy

**Decision**: v1 uses minimal dependencies (direct HTTP API calls for local LLM). No cloud SDK required. v2 can adopt LangChain if advanced features needed.

**Rationale**:
- **Why**: Local LLM APIs are HTTP-based and OpenAI-compatible. No SDK needed beyond httpx (already a dependency).
- **Alternative considered**: Cloud LLM SDKs (openai, anthropic)
- **Why rejected**: Violates 12-factor (tightly coupled to backing service), requires internet, incurs costs

**Dependencies to add**:
- **None new** - httpx already available for async HTTP calls
- **Optional**: `langchain-community` if advanced features needed later
- **Local LLM server**: Ollama/vLLM/etc. runs as separate process (12-factor backing service)

**No vendor lock-in**:
```python
# Works with ANY OpenAI-compatible local server
# Just change SECONDBRAIN_LLM_ENDPOINT environment variable
# No code changes required
```

## Risks / Trade-offs

**[Risk] Local model hardware requirements** → **Mitigation**: 
- Minimum: 8GB RAM for 7B parameter models (quantized)
- Recommended: 16GB+ RAM or GPU for larger models
- Configurable model selection via `SECONDBRAIN_LLM_MODEL`
- Support for quantized models (GGUF format) to reduce memory

**[Risk] Local model latency vs cloud APIs** → **Mitigation**:
- Configurable timeout: `SECONDBRAIN_LLM_TIMEOUT=120` (default, higher than cloud)
- Streaming responses (future enhancement)
- Model selection guidance in documentation
- Async support for concurrent requests

**[Risk] Conversation quality depends on retrieval quality** → **Mitigation**:
- v1: Use existing semantic search (proven in production)
- v2: Add multi-query retrieval, reranking if needed
- Clear user feedback mechanism for bad answers

**[Risk] Local LLM server availability** → **Mitigation**:
- Health check before queries: `provider.health_check()`
- Graceful degradation: "Local LLM server unavailable at {endpoint}"
- Automatic retry with exponential backoff
- Clear error messages with startup instructions

**[Risk] Context window limits may truncate important history** → **Mitigation**:
- Configurable window size (default conservative at 5 turns)
- Future: Implement conversation summarization to compress history

**[Risk] MongoDB conversation collection growth** → **Mitigation**:
- Implement TTL index for auto-expiration (optional, configurable)
- Archive/delete commands for session management
- Compression enabled by default (MongoDB feature)

**[Trade-off] Template-based query rewriting vs ML-based** → 
- Template: Simple, no extra model, but may miss nuanced context
- ML-based: Better quality, but requires additional model and training data
- Decision: Start with template, upgrade if user feedback indicates need

**[Trade-off] Minimal dependencies vs LangChain features** →
- Minimal: Faster development, lighter footprint, but manual implementation of advanced features
- LangChain: Rich feature set, but heavy dependency tree, less control
- Decision: Start minimal, migrate to LangChain only if advanced features become necessary

## Migration Plan

**Phase 1: Core Infrastructure** (Week 1)
1. Create `src/secondbrain/conversation/` module with `ConversationSession` class
2. Create `src/secondbrain/rag/` module with `RAGPipeline` and `LocalLLMProvider` protocol
3. Add MongoDB `conversations` collection schema and storage logic
4. Write unit tests for session management and RAG pipeline

**Phase 2: CLI Integration** (Week 1-2)
1. Add `secondbrain chat [session-id]` command to CLI
2. Implement interactive readline loop with Rich formatting
3. Add `--session` flag to specify or create conversation session
4. Add `--list-sessions` and `--delete-session` commands
5. Integration tests for CLI workflow

**Phase 3: Local LLM Provider Integration** (Week 2)
1. Implement `OllamaLLMProvider` with environment variable configuration
2. Add configuration options (endpoint, model, temperature, max tokens, timeout)
3. Implement prompt templates for RAG context formatting
4. Implement health check for local LLM server
5. End-to-end tests with local LLM (Ollama)

**Phase 4: MCP Service Preparation** (Week 2-3)
1. Extract RAG service into standalone callable interface
2. Define OpenAPI spec for HTTP API (future MCP conversion)
3. Add async support for concurrent requests
4. Documentation for MCP service conversion

**Rollback Strategy**:
- All changes are additive; existing `search` command unaffected
- If issues arise, simply don't use `chat` command
- MongoDB schema additions are backward compatible
- No database migrations required

## Open Questions

1. **Which local LLM backend to default to?** Ollama is most popular and easiest to set up. Decision: Default to Ollama (`http://localhost:11434`), but support any OpenAI-compatible endpoint via `SECONDBRAIN_LLM_ENDPOINT`.

2. **What model to recommend?** llama3.2 (7B) offers good quality/performance balance. Alternatives: mistral, codellama, phi3. Decision: Default to `llama3.2`, document alternatives in README.

3. **Should we support multiple concurrent sessions?** v1: Single active session per CLI invocation. Future: Multi-session management via session ID parameter.

4. **How to handle long conversations?** v1: Fixed context window. Future: Add summarization or hierarchical memory.

5. **Should retrieved chunks be shown to users?** Decision: Yes, with `--show-sources` flag (similar to existing `search` command).

6. **When to trigger MCP service conversion?** After CLI validation proves the RAG approach works. Separate spec change will define MCP protocol implementation.

7. **How to handle model downloads?** Ollama handles this automatically (`ollama pull llama3.2`). Other backends require manual model setup. Decision: Document setup for each backend, prioritize Ollama for simplicity.
