## 1. Project Setup & Structure

- [ ] 1.1 Create `src/secondbrain_cli/` package directory with __init__.py
- [ ] 1.2 Create `src/secondbrain_common/` package directory with __init__.py
- [ ] 1.3 Create `src/secondbrain_mcp/` package directory with __init__.py
- [ ] 1.4 Update `pyproject.toml` to add new packages in `[tool.setuptools.packages.find]`
- [ ] 1.5 Add `mcp>=1.0.0` dependency to `pyproject.toml`
- [ ] 1.6 Verify new package structure with `pip install -e .`

## 2. Extract Common Module - Domain Layer

- [ ] 2.1 Copy `src/secondbrain/domain/` to `src/secondbrain_common/domain/`
- [ ] 2.2 Copy `src/secondbrain/exceptions.py` to `src/secondbrain_common/exceptions.py`
- [ ] 2.3 Copy `src/secondbrain/types.py` to `src/secondbrain_common/types.py`
- [ ] 2.4 Copy `src/secondbrain/constants.py` to `src/secondbrain_common/constants.py`
- [ ] 2.5 Update imports in common domain files to use absolute imports
- [ ] 2.6 Verify common domain module imports cleanly

## 3. Extract Common Module - Storage Layer

- [ ] 3.1 Copy `src/secondbrain/storage/` to `src/secondbrain_common/storage/`
- [ ] 3.2 Update imports in storage/models.py and storage/pipeline.py
- [ ] 3.3 Copy `src/secondbrain/document/` to `src/secondbrain_common/document/`
- [ ] 3.4 Update document module imports for common package
- [ ] 3.5 Verify storage and document modules import cleanly

## 4. Extract Common Module - Core Logic

- [ ] 4.1 Copy `src/secondbrain/search/` to `src/secondbrain_common/search/`
- [ ] 4.2 Copy `src/secondbrain/rag/` to `src/secondbrain_common/rag/`
- [ ] 4.3 Copy `src/secondbrain/embedding/` to `src/secondbrain_common/embedding/`
- [ ] 4.4 Copy `src/secondbrain/conversation/` to `src/secondbrain_common/conversation/`
- [ ] 4.5 Update all internal imports within common modules
- [ ] 4.6 Verify core logic modules import cleanly

## 5. Extract Common Module - Config & Utils

- [ ] 5.1 Copy `src/secondbrain/config/` to `src/secondbrain_common/config/`
- [ ] 5.2 Copy `src/secondbrain/utils/` to `src/secondbrain_common/utils/`
- [ ] 5.3 Copy `src/secondbrain/logging/` to `src/secondbrain_common/logging/`
- [ ] 5.4 Update utility imports to use common package
- [ ] 5.5 Verify config and utils modules import cleanly

## 6. Create CLI Module

- [ ] 6.1 Copy `src/secondbrain/cli/` to `src/secondbrain_cli/`
- [ ] 6.2 Update `secondbrain_cli/cli.py` to import from `secondbrain_common`
- [ ] 6.3 Update `secondbrain_cli/commands.py` imports for common modules
- [ ] 6.4 Update `secondbrain_cli/display.py` imports for common modules
- [ ] 6.5 Update `secondbrain_cli/errors.py` imports for common exceptions
- [ ] 6.6 Update entry point in `pyproject.toml` to `secondbrain_cli.cli:main`
- [ ] 6.7 Test CLI still works: `python -m secondbrain_cli --help`

## 7. Create MCP Server Skeleton

- [ ] 7.1 Create `src/secondbrain_mcp/server.py` with basic MCP server setup
- [ ] 7.2 Implement `list_tools()` handler returning tool names
- [ ] 7.3 Implement `call_tool()` skeleton with routing structure
- [ ] 7.4 Create `src/secondbrain_mcp/tools/__init__.py`
- [ ] 7.5 Create `src/secondbrain_mcp/handlers/__init__.py`
- [ ] 7.6 Create `src/secondbrain_mcp/handlers/errors.py` for MCP error formatting
- [ ] 7.7 Test MCP server starts: `python -m secondbrain_mcp.server`

## 8. Implement MCP Ingest Tool

- [ ] 8.1 Create `src/secondbrain_mcp/tools/ingest.py`
- [ ] 8.2 Define ingest tool schema (path, recursive, chunk_size, chunk_overlap, cores)
- [ ] 8.3 Implement ingest tool calling `secondbrain_common.document.DocumentIngestor`
- [ ] 8.4 Format success response with chunk count
- [ ] 8.5 Format error response with user-friendly message
- [ ] 8.6 Test ingest tool via MCP client or manual invocation

## 9. Implement MCP Search Tool

- [ ] 9.1 Create `src/secondbrain_mcp/tools/search.py`
- [ ] 9.2 Define search tool schema (query, top_k)
- [ ] 9.3 Implement search tool calling `secondbrain_common.search.Searcher`
- [ ] 9.4 Format results with chunk text, source file, page, score
- [ ] 9.5 Test search tool with sample queries

## 10. Implement MCP Chat Tool

- [ ] 10.1 Create `src/secondbrain_mcp/tools/chat.py`
- [ ] 10.2 Define chat tool schema (query, session_id, top_k, temperature, show_sources)
- [ ] 10.3 Implement chat tool using `secondbrain_common.rag.RAGPipeline`
- [ ] 10.4 Handle session creation/loading via `secondbrain_common.conversation`
- [ ] 10.5 Format response with answer and optional sources
- [ ] 10.6 Test chat tool with single-turn and session-based queries

## 11. Implement MCP Admin Tools (ls, delete)

- [ ] 11.1 Create `src/secondbrain_mcp/tools/admin.py`
- [ ] 11.2 Implement `ls` tool: list documents and chunks
- [ ] 11.3 Implement `delete` tool: delete by ID or pattern
- [ ] 11.4 Add validation for delete operations (confirm deletion count)
- [ ] 11.5 Test ls tool with different types (document, chunk)
- [ ] 11.6 Test delete tool with various criteria

## 12. Implement MCP Health & Status Tools

- [ ] 12.1 Create `src/secondbrain_mcp/tools/health.py`
- [ ] 12.2 Implement `health` tool checking MongoDB and Ollama
- [ ] 12.3 Implement `status` tool returning database statistics
- [ ] 12.4 Implement `metrics` tool returning performance data
- [ ] 12.5 Format health responses with service status details
- [ ] 12.6 Test health tool with services running and down

## 13. Input Validation & Error Handling

- [ ] 13.1 Add schema validation for all tool inputs using Pydantic
- [ ] 13.2 Implement parameter type checking in each tool
- [ ] 13.3 Add path validation for ingest tool (file exists, supported format)
- [ ] 13.4 Add bounds checking for numeric parameters (top_k > 0, temperature 0-1)
- [ ] 13.5 Create consistent error response format across all tools
- [ ] 13.6 Test validation errors return proper MCP error format

## 14. Integration & Consistency Testing

- [ ] 14.1 Run CLI `ingest` and MCP `ingest` on same file, compare results
- [ ] 14.2 Run CLI `search` and MCP `search` with same query, compare results
- [ ] 14.3 Run CLI `chat` and MCP `chat` with same query, compare answers
- [ ] 14.4 Verify database state is identical regardless of entry point
- [ ] 14.5 Test concurrent MCP tool calls (parallel search requests)
- [ ] 14.6 Fix any inconsistencies between CLI and MCP behavior

## 15. Documentation & Cleanup

- [ ] 15.1 Add docstrings to all MCP tool functions
- [ ] 15.2 Update README.md with MCP server usage instructions
- [ ] 15.3 Create MCP quickstart guide (how to connect MCP client)
- [ ] 15.4 Add code comments for non-obvious implementation decisions
- [ ] 15.5 Remove any dead code from original structure
- [ ] 15.6 Run `ruff check .` and fix any linting issues
- [ ] 15.7 Run `mypy .` and fix any type errors
- [ ] 15.8 Create migration guide for users with existing imports

## 16. Final Verification

- [ ] 16.1 Run full test suite: `pytest`
- [ ] 16.2 Verify CLI commands all work: `secondbrain --help` and each command
- [ ] 16.3 Verify MCP server starts and lists tools correctly
- [ ] 16.4 Test end-to-end MCP workflow (ingest → search → chat)
- [ ] 16.5 Check performance is not degraded by refactoring
- [ ] 16.6 Clean up temporary files and build artifacts
- [ ] 16.7 Create git commit with comprehensive message
