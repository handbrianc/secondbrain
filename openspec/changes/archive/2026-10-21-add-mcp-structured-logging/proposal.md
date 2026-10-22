# MCP Structured Logging — Proposal

## Why

The serving runtime (`add-mcp-server-runtime`) has no logging: operators cannot see request handling, startup, or
errors at a controlled verbosity. The scaffold's config already parses `SECONDBRAIN_MCP_LOG_LEVEL`; this proposal
delivers the observability unit that consumes it — structured logging wired to the configured level. It is its own
unit of work because it is an independently rejectable behavior (a deployment could run silent) with a distinct
verification mechanism (log capture, not HTTP probing).

## What Changes

- **Structured logging**: `tracing`/`tracing-subscriber` initialized in `main` with a level filter from
  `SECONDBRAIN_MCP_LOG_LEVEL`; server lifecycle and request events are emitted through it.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-server-runtime** — adds the configurable logging requirement.

## Dependencies

- Requires: `add-mcp-server-runtime` (the process whose events are logged), `add-mcp-server-scaffold`
  (config provides `LOG_LEVEL`).

**Depended on by:** `add-mcp-readme-feature-docs` (documents the variable's runtime effect).

## Impact

**Code**: `mcp-server/src/main.rs` (subscriber init), new integration tests.

**Dependencies**: `tracing`, `tracing-subscriber`.

## Non-goals

- Log output format/plumbing options (JSON logs, external shipping) — single structured format, v1.
- Per-module level filters (single global filter).
