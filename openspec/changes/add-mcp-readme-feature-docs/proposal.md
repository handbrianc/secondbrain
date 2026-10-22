# MCP Server README Feature Documentation — Proposal

## Why

The MCP series lands a new surface (tools, transport, TLS, auth, container, env contract) that operators and MCP
client users must understand without reading Rust or the Python CLI. The user requirement is explicit: the MCP server
documentation must include the exposed feature set. This proposal delivers that as the first documentation unit: a
`mcp-server/README.md` living with the code, with completeness enforced by an automated test rather than convention.
The docs-site integration (MkDocs page, navigation, Docker-guide correction) is a separate unit:
`add-mcp-docs-site-integration`.

## What Changes

- **`mcp-server/README.md`**: the exposed feature set —
  - Tool reference: `search`, `ingest_documents`, `chat_send`, `chat_list_sessions`, `chat_get_history` (parameters,
    defaults, result shapes, error behavior)
  - Server environment reference: the `SECONDBRAIN_MCP_*` table
  - Integration environment reference: the Python `SECONDBRAIN_*` passthrough surface (external LLM, embedding/vector
    model API, Qdrant, SQLite)
  - Optional HTTPS (TLS) setup (PEM cert/key, examples), bearer-token auth, security model and deviations
  - Build/run (cargo), container/compose usage, wire-level examples (JSON-RPC over HTTPS)
- **Completeness test** `tests/test_docs/test_mcp_docs.py`: asserts every registered tool name and every
  `SECONDBRAIN_MCP_*` variable from the config module's source of truth appears in the README.
- **Wire-example verification**: the README's JSON-RPC-over-HTTPS example is checked against the e2e smoke's observed
  shapes.

No Rust or Python behavior changes.

## Capabilities

### New Capabilities

- **mcp-documentation**: documentation completeness requirements for the MCP server.

### Modified Capabilities

- *None.*

## Dependencies

- Requires: `add-mcp-streamable-http-transport`, `add-mcp-search-tool`, `add-mcp-ingest-tool`,
  `add-mcp-ingest-path-confinement`, `add-mcp-chat-send-tool`, `add-mcp-chat-sessions-list-tool`,
  `add-mcp-chat-history-tool`, `add-mcp-tls-support`, `add-mcp-bearer-auth` (documents the feature set); compose
  sections assume the deployment proposals.

**Depended on by:** `add-mcp-docs-site-integration`.

## Impact

**Code**: `mcp-server/README.md`, `tests/test_docs/test_mcp_docs.py` (new).

**Out of scope**: docs site (separate proposal); architecture deep-dive.

## Non-goals

- MkDocs integration and site navigation (`add-mcp-docs-site-integration`).
- Documenting pre-existing CLI behavior beyond what the MCP tools consume.
