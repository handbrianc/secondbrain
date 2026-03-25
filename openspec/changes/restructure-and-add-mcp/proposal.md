## Why

The current codebase lacks clear separation between CLI concerns, shared utilities, and the new MCP server functionality. As we add MCP support, the code will become increasingly tangled without a modular structure. This reorganization creates three distinct, maintainable modules that can evolve independently while sharing common abstractions.

## What Changes

**Restructuring:**
- Move CLI-specific code to `src/secondbrain_cli/` - Click commands, argument parsing, terminal display
- Extract shared domain logic to `src/secondbrain_common/` - core business logic, interfaces, utilities
- Create `src/secondbrain_mcp/` - MCP server implementation, tool definitions, protocol handlers

**New Capabilities:**
- MCP server exposing CLI commands as MCP tools
- Structured tool definitions for document ingestion, search, and chat operations
- MCP-specific error handling and response formatting

**Modified Capabilities:**
- None at the requirement level - existing CLI functionality remains unchanged

**Breaking Changes:**
- **BREAKING** Internal module imports will change (e.g., `secondbrain.cli.commands` → `secondbrain_cli.commands`)
- **BREAKING** Package structure changes may affect direct imports by other code

## Capabilities

### New Capabilities
- `mcp-server`: Model Context Protocol server implementation that exposes SecondBrain CLI commands as MCP tools
  - Document ingestion via MCP tools
  - Semantic search via MCP tools  
  - Chat/rag operations via MCP tools
  - Health/status queries via MCP tools

### Modified Capabilities
- None - this is primarily a structural refactoring with new capabilities added

## Impact

**Code:**
- All source files under `src/secondbrain/` will be reorganized
- CLI module (`src/secondbrain/cli/`) → `src/secondbrain_cli/`
- Domain/core logic → `src/secondbrain_common/`
- New MCP server code → `src/secondbrain_mcp/`

**Dependencies:**
- New dependency: `mcp>=1.0.0` (Model Context Protocol SDK)
- Existing dependencies remain unchanged

**APIs:**
- Internal APIs will be reorganized but maintain same functionality
- External API: MCP server will expose tools matching CLI commands
- CLI entry point remains `secondbrain` command

**Testing:**
- Test structure needs parallel reorganization
- Integration tests must verify MCP tools match CLI behavior
