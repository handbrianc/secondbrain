# MCP Graceful Shutdown — Proposal

## Why

The serving runtime (`add-mcp-server-runtime`) binds and serves but dies ungracefully on termination signals —
in-flight requests are dropped and `docker stop` gets no drain window. This proposal delivers the lifecycle unit:
clean termination on SIGINT/SIGTERM. It is its own unit of work because it is an independently rejectable behavior
(a deployment could accept abrupt termination) with a distinct verification mechanism (signal delivery and exit
status, not HTTP probing).

## What Changes

- **Graceful shutdown**: the serving loop stops accepting connections on SIGINT/SIGTERM, finishes in-flight requests,
  and exits with status 0 (via `axum`'s graceful-shutdown support and `tokio::signal`).

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-server-runtime** — adds the graceful shutdown requirement.

## Dependencies

- Requires: `add-mcp-server-runtime` (the serving loop being made graceful).

**Depended on by:** `revise-dockerfile-for-mcp` (container stop semantics), `revise-compose-production-stack`
(restart policy behavior).

## Impact

**Code**: `mcp-server/src/main.rs` (shutdown token), one integration test.

**Dependencies**: none beyond existing (`tokio::signal`).

## Non-goals

- Connection-drain timeouts/force-kill thresholds (unbounded drain, v1).
- Configurable shutdown signals.
