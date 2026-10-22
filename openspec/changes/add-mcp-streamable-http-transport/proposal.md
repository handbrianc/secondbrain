# MCP Streamable HTTP Transport — Proposal

## Why

The scaffold (see `add-mcp-server-scaffold/design.md`) stands up the `secondbrain-mcp` process with only a health
endpoint. Without an MCP endpoint no client can use it. This proposal mounts the official `rmcp` Streamable HTTP
server transport at `/mcp` so any MCP client can connect, discover the (initially empty) tool registry, and
negotiate the protocol — the substrate that all tool proposals (search, ingest, chat) register against.

## What Changes

- **`POST /mcp` MCP endpoint** using rmcp 3.5's `StreamableHttpService` mounted into the existing axum router:
  - Stateless protocol mode (MCP 2026-07-28 default): no `Mcp-Session-Id`, no initialize handshake required, GET/DELETE
    on `/mcp` rejected.
  - Single-body JSON responses (`json_response(true)`): replies are `application/json`; SSE is used only if a handler
    emits notifications (none do in this server).
- **Server metadata**: name `secondbrain-mcp`, version from the crate, and an instructions string summarizing the
  three capability groups (ingestion, search, chat sessions).
- **Empty tool registry**: `tools/list` returns an empty array until the tool proposals land.
- **Integration tests** in `mcp-server/tests/`: raw JSON-RPC over HTTP (content negotiation, error mapping) plus an
  rmcp-client interop test, following rmcp's own ephemeral-port test pattern.

No Python changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-server-runtime** — adds transport requirements (endpoint, protocol mode, metadata, interop).

## Dependencies

- Requires: `add-mcp-server-scaffold` (crate, config), `add-mcp-server-runtime` (router with `/healthz`,
  ephemeral-port test helpers).

**Depended on by:** `add-mcp-cli-adapter`, `add-mcp-tls-support`, `add-mcp-bearer-auth`,
`add-mcp-readme-feature-docs`.

## Impact

**Code**: `mcp-server/src/main.rs` (mount service), new `mcp-server/src/server.rs` (ServerHandler with empty tool
router), new tests under `mcp-server/tests/`.

**Dependencies**: no new crates (rmcp's `transport-streamable-http-server` feature was already declared).

**Out of scope**: tools themselves, TLS, auth.

## Non-goals

- Legacy session mode for pre-2026-07-28 clients (rmcp supports it; not enabled — clients must be stateless-capable).
- OAuth 2.1 resource-server authorization (bearer-token auth arrives in `add-mcp-bearer-auth`).
