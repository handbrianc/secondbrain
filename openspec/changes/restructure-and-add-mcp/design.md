## Context

The SecondBrain CLI is a document intelligence tool with ~30 Python source files organized under `src/secondbrain/`. Current structure mixes CLI concerns (Click decorators, terminal display) with business logic (document ingestion, search, RAG pipeline). 

**Current State:**
- Single package: `secondbrain`
- CLI code in `secondbrain/cli/` (commands.py, display.py, errors.py)
- Core logic scattered across domain modules
- No clear separation for new MCP server functionality

**Constraints:**
- Must maintain backward-compatible CLI interface
- Existing users depend on `secondbrain` command
- MCP server should expose same capabilities as CLI
- Python 3.11+ requirement

## Goals / Non-Goals

**Goals:**
1. Create three distinct, importable modules: `secondbrain_cli`, `secondbrain_common`, `secondbrain_mcp`
2. Extract shared domain logic into `secondbrain_common` for reuse
3. Implement MCP server exposing CLI commands as MCP tools
4. Maintain existing CLI behavior (no user-facing changes)
5. Enable independent testing of each module

**Non-Goals:**
- Changing CLI command interface or options
- Adding new features beyond MCP server
- Refactoring internal implementation of business logic
- Database schema changes
- Breaking existing import patterns in external code (documented as breaking change)

## Decisions

### 1. Module Structure: Separate Packages vs Submodules

**Decision:** Create three separate top-level packages under `src/`

```
src/
├── secondbrain_cli/       # CLI-specific code
│   ├── __init__.py
│   ├── cli.py            # Click group definition
│   ├── commands.py       # Command implementations
│   ├── display.py        # Rich output formatting
│   └── errors.py         # Error handling
├── secondbrain_common/    # Shared domain logic
│   ├── __init__.py
│   ├── core/             # Core business logic
│   │   ├── document.py   # Document ingestion
│   │   ├── search.py     # Semantic search
│   │   ├── rag.py        # RAG pipeline
│   │   └── conversation.py # Chat session management
│   ├── domain/           # Domain models
│   │   ├── entities.py
│   │   ├── value_objects.py
│   │   └── interfaces.py
│   ├── storage/          # Persistence layer
│   │   ├── models.py
│   │   └── pipeline.py
│   ├── embedding/        # Vector embeddings
│   │   └── local.py
│   ├── config/           # Configuration
│   │   └── __init__.py
│   ├── exceptions.py     # Shared exceptions
│   └── utils/            # Shared utilities
│       ├── circuit_breaker.py
│       └── connections.py
└── secondbrain_mcp/       # MCP server implementation
    ├── __init__.py
    ├── server.py         # MCP server entry point
    ├── tools/            # MCP tool definitions
    │   ├── __init__.py
    │   ├── ingest.py
    │   ├── search.py
    │   ├── chat.py
    │   └── admin.py
    └── handlers/         # Request handlers
        ├── __init__.py
        └── errors.py
```

**Alternatives Considered:**
- *Submodules under secondbrain*: Would blur boundaries, harder to maintain separation
- *Monorepo with workspaces*: Overkill for this scale, adds npm/yarn complexity

### 2. Shared State Management

**Decision:** Use dependency injection for shared components (config, storage, LLM providers)

```python
# secondbrain_common/core/rag.py
class RAGPipeline:
    def __init__(
        self,
        searcher: Searcher,
        llm_provider: LLMProvider,
        top_k: int,
        context_window: int,
    ):
        self.searcher = searcher
        self.llm_provider = llm_provider
        # ...
```

CLI and MCP both instantiate with their own dependencies, avoiding shared mutable state.

**Alternatives Considered:**
- *Singleton pattern*: Harder to test, creates hidden dependencies
- *Global config module*: Tight coupling,不利于 testing

### 3. MCP Protocol Implementation

**Decision:** Use `mcp` Python SDK (Model Context Protocol) with tool-based architecture

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

app = Server("secondbrain")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ingest",
            description="Ingest documents into vector database",
            inputSchema={...},
        ),
        # ...
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "ingest":
        return await ingest_tool(arguments)
    # ...
```

**Alternatives Considered:**
- *Custom protocol*: Reinventing wheels, no interoperability
- *REST API*: Not MCP-compliant, different client ecosystem

### 4. Error Handling Strategy

**Decision:** Domain-specific exceptions in `secondbrain_common`, transport-layer handling per module

```python
# secondbrain_common/exceptions.py
class DocumentError(Exception): pass
class SearchError(Exception): pass
class StorageError(Exception): pass

# secondbrain_cli/errors.py - formats for terminal
# secondbrain_mcp/handlers/errors.py - formats for MCP JSON-RPC
```

**Alternatives Considered:**
- *Unified error handler*: Would leak transport concerns into domain

### 5. Configuration Loading

**Decision:** Keep config in `secondbrain_common/config/` - shared between CLI and MCP

```python
# secondbrain_common/config/__init__.py
from pydantic_settings import BaseSettings

class SecondBrainConfig(BaseSettings):
    chunk_size: int = 1000
    chunk_overlap: int = 200
    llm_model: str = "llama3.2"
    ollama_host: str = "http://localhost:11434"
    # ...
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **Breaking imports**: External code using `secondbrain.cli` will break | Document clearly in CHANGELOG; provide migration guide |
| **Circular dependencies**: Common modules depending on CLI | Strict layering: common → domain → storage; CLI/MCP depend on common only |
| **MCP SDK instability**: Early-stage library may have breaking changes | Pin version; abstract MCP-specific code behind interfaces |
| **Performance overhead**: Additional abstraction layers | Profile after migration; inline hot paths if needed |
| **Testing complexity**: More modules = more test files | Parallel test structure; shared fixtures in common |

## Migration Plan

### Phase 1: Create New Structure (Week 1)
1. Create `src/secondbrain_cli/` - copy CLI code, fix imports
2. Create `src/secondbrain_common/` - extract domain logic
3. Create stub `src/secondbrain_mcp/` - empty package
4. Update `pyproject.toml` - add new packages, MCP dependency
5. Verify CLI still works unchanged

### Phase 2: Extract Shared Logic (Week 2)
1. Move domain entities to common
2. Move storage models to common
3. Move RAG pipeline to common
4. Move search logic to common
5. Update CLI to import from common

### Phase 3: Build MCP Server (Week 3)
1. Implement MCP server skeleton
2. Create ingest tool
3. Create search tool
4. Create chat tool
5. Create admin tools (list, delete, health)
6. Test MCP tools against common implementations

### Phase 4: Testing & Polish (Week 4)
1. Write unit tests for common module
2. Write integration tests for MCP tools
3. Verify CLI behavior unchanged
4. Update documentation
5. Create migration guide

### Rollback Strategy
If issues arise:
1. Revert to git state before migration
2. Keep new code in separate branch for later attempt
3. No partial deployments - all-or-nothing cutover

## Open Questions

1. **MCP transport**: Should MCP server support stdio only, or also HTTP/SSE?
   - *Current plan*: stdio (matches MCP spec defaults)
   - *Decision needed*: Add HTTP transport?

2. **Dependency injection depth**: Should CLI create all dependencies, or should common provide factory functions?
   - *Current plan*: Common provides factory functions (e.g., `create_rag_pipeline()`)
   - *Rationale*: Reduces boilerplate in CLI/MCP

3. **Versioning**: Should common, CLI, and MCP be versioned together or independently?
   - *Current plan*: Single version (same as current CLI version)
   - *Rationale*: Simpler; they ship together

4. **MCP tool naming**: Should MCP tool names match CLI command names exactly?
   - *Current plan*: Yes (ingest, search, chat, ls, delete, health, status)
   - *Rationale*: Predictable for users familiar with CLI
