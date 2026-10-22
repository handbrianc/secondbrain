# MCP Server Runtime Behaviors — Proposal

## Why

The scaffold (`add-mcp-server-scaffold`) delivers the crate and its validated configuration layer, but the entrypoint
does not yet serve anything. This proposal delivers the **serving** unit of work: the server binds the configured
address and exposes a health endpoint. Lifecycle (graceful shutdown) and observability (structured logging) are
independent decisions with their own verification mechanisms — separate proposals
(`add-mcp-graceful-shutdown`, `add-mcp-structured-logging`). Serving is the unit the MCP transport
(`add-mcp-streamable-http-transport`) and the Docker HEALTHCHECK (`revise-dockerfile-for-mcp`) depend on.

## What Changes

- **Serving runtime**: `main` binds `SECONDBRAIN_MCP_HTTP_BIND_ADDR` (plaintext HTTP; TLS is the optional capability
  of `add-mcp-tls-support`) and serves requests until killed.
- **Health endpoint** `GET /healthz` returning `{"status":"ok"}` (plain axum route — MCP handling is the transport
  proposal's unit).

No Python changes. No MCP endpoint, no signal handling, no logging wiring in this unit.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-server-runtime** — adds the serving requirements (bind/serve, health).

## Dependencies

- Requires: `add-mcp-server-scaffold` (crate, config).

**Depended on by:** `add-mcp-graceful-shutdown`, `add-mcp-structured-logging`,
`add-mcp-streamable-http-transport`, `revise-dockerfile-for-mcp`.

## Impact

**Code**: `mcp-server/src/main.rs` (real runtime), `mcp-server/tests/common/mod.rs` (ephemeral-port boot helper),
new integration tests.

**Dependencies**: `axum` 0.8, `tokio` 1.x.

**Out of scope**: graceful shutdown, logging (separate proposals), MCP endpoint, TLS, auth, tools.

## Non-goals

- Graceful shutdown / structured logging (separate proposals).
- Any MCP protocol surface.
- TLS (plaintext only; optional capability in `add-mcp-tls-support`).
