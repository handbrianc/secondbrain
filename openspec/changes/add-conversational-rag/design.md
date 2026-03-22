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

### 2. LLM Provider Abstraction

**Decision**: Define `LLMProvider` protocol with `generate(prompt: str) -> str` method. Start with OpenAI API as default implementation, but design for pluggable backends.

**Rationale**:
- **Why**: Allows swapping LLM providers without changing RAG logic. Supports future local models (Ollama, vLLM) or other APIs (Anthropic, Cohere).
- **Alternative considered**: Tightly couple to LangChain's LLM abstraction
- **Why rejected**: Adds heavy dependency for simple use case; custom protocol is lighter and more explicit

**Interface**:
```python
class LLMProvider(Protocol):
    def generate(self, prompt: str, temperature: float = 0.7) -> str: ...
    async def agenerate(self, prompt: str, temperature: float = 0.7) -> str: ...
```

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

**Decision**: v1 uses minimal dependencies (direct HTTP API calls for LLM). v2 can adopt LangChain if advanced features needed.

**Rationale**:
- **Why**: Keeps initial implementation lightweight. LangChain adds 50+ transitive dependencies; not needed for basic RAG.
- **Alternative considered**: Start with LangChain for future-proofing
- **Why rejected**: Over-engineering for v1; can migrate to LangChain if advanced features (agents, chains) become necessary

**Dependencies to add**:
- `openai>=1.0.0` (or alternative LLM provider SDK)
- `uuid` (stdlib, no addition)

## Risks / Trade-offs

**[Risk] LLM costs and latency** → **Mitigation**: 
- Configurable context window size to control token usage
- Caching layer for repeated prompts (extension point)
- Support for cheaper/faster models via provider abstraction

**[Risk] Conversation quality depends on retrieval quality** → **Mitigation**:
- v1: Use existing semantic search (proven in production)
- v2: Add multi-query retrieval, reranking if needed
- Clear user feedback mechanism for bad answers

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
2. Create `src/secondbrain/rag/` module with `RAGPipeline` and `LLMProvider` protocol
3. Add MongoDB `conversations` collection schema and storage logic
4. Write unit tests for session management and RAG pipeline

**Phase 2: CLI Integration** (Week 1-2)
1. Add `secondbrain chat [session-id]` command to CLI
2. Implement interactive readline loop with Rich formatting
3. Add `--session` flag to specify or create conversation session
4. Add `--list-sessions` and `--delete-session` commands
5. Integration tests for CLI workflow

**Phase 3: LLM Provider Integration** (Week 2)
1. Implement `OpenAILLMProvider` with environment variable configuration
2. Add configuration options (model, temperature, max tokens)
3. Implement prompt templates for RAG context formatting
4. End-to-end tests with real LLM API

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

1. **Which LLM provider to default to?** OpenAI is most common, but users may prefer local models (Ollama) or other APIs (Anthropic, Groq). Decision: Default to OpenAI, but document how to switch providers.

2. **Should we support multiple concurrent sessions?** v1: Single active session per CLI invocation. Future: Multi-session management via session ID parameter.

3. **How to handle long conversations?** v1: Fixed context window. Future: Add summarization or hierarchical memory.

4. **Should retrieved chunks be shown to users?** Decision: Yes, with `--show-sources` flag (similar to existing `search` command).

5. **When to trigger MCP service conversion?** After CLI validation proves the RAG approach works. Separate spec change will define MCP protocol implementation.
