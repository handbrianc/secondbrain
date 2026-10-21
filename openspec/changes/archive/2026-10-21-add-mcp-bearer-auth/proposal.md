# MCP Bearer Auth — Proposal

## Why

An MCP server that can ingest documents and query a knowledge base must be lockable down when exposed over a network.
The MCP authorization specification (2026-07-28) defines full OAuth 2.1 resource-server flows — the right end state
for public deployments, but disproportionate for v1 where the server runs in a private stack. This proposal ships the
pragmatic core: an optional static bearer token, enforced at the HTTP layer with constant-time comparison and
standard 401 signaling, off by default so local/single-user deployments stay zero-config. The design deviation from
the full OAuth spec is explicit (see Non-goals) and recorded as the follow-up path.

## What Changes

- **Optional bearer auth middleware** on `/mcp` (and any future MCP surface), driven by `SECONDBRAIN_MCP_AUTH_TOKEN`
  (already parsed by the scaffold config):
  - Unset: no auth required (current behavior, unchanged).
  - Set: requests must carry `Authorization: Bearer <token>` matching the configured value (constant-time compare);
    otherwise 401 with `WWW-Authenticate: Bearer`.
  - `GET /healthz` stays unauthenticated so container orchestrators' healthchecks keep working.
- **Tests**: all four outcomes (open mode, 401 missing/wrong/scheme, 200 correct), health exemption, prefix-match
  rejection (constant-time property smoke).

No Python changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-server-runtime** — adds auth requirements.

## Dependencies

- Requires: `add-mcp-server-scaffold` (config field), `add-mcp-streamable-http-transport` (the protected surface).
  Independent of TLS and the tool proposals.

**Depended on by:** `add-mcp-readme-feature-docs`, `revise-compose-production-stack` (token env wiring).

## Impact

**Code**: `mcp-server/src/auth.rs` (tower middleware), `main.rs` layer wiring, new tests.

**Dependencies**: `subtle` (constant-time comparison), `tower`/`tower-http` middleware plumbing (already in tree via
rmcp's tower feature).

## Non-goals

- OAuth 2.1 resource-server conformance: RFC 9728 protected-resource metadata endpoint, 401
  `WWW-Authenticate` with `resource_metadata`, dynamic client registration, token introspection — explicit follow-up
  candidate if public exposure is needed.
- Multiple tokens / token rotation / per-token scopes.
- Rate limiting (separate concern).
