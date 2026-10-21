# MCP Server Scaffold — Proposal

## Why

secondbrain's RAG capabilities (file ingestion, semantic search, conversational chat) are only reachable through the
Python CLI. The archived `add-conversational-rag` change explicitly scoped the RAG layer to be CLI/MCP-agnostic and
flagged "future MCP service conversion" as the intended path. This proposal creates the foundation: a Rust MCP server
crate in its own source tree with its tests in their own source tree, and — as the single unit of work — its
environment-driven **configuration layer** (`SECONDBRAIN_MCP_*`), validated end to end. Process runtime behaviors
(health, shutdown, logging) are a separate unit: `add-mcp-server-runtime`.

## What Changes

- **New Rust crate** `mcp-server/` — the top-level directory is clearly named for MCP server code:
  - `mcp-server/src/` — server code (entrypoint shell, config module)
  - `mcp-server/tests/` — integration tests in their own source tree
- **Configuration module** (`mcp-server/src/config.rs`) parsing and validating the full `SECONDBRAIN_MCP_*` table in
  one place, with documented defaults. All values are parsed here; later proposals wire them in (TLS paths validated
  by the TLS proposal, auth by the auth proposal, and so on).
- **Entrypoint shell**: `main` parses and validates configuration, then exits 0 (binding/serving arrives with the
  runtime proposal). Invalid configuration exits non-zero naming the offending variable — the fail-fast contract the
  runtime builds on.
- **CI**: `.github/workflows/rust-checks.yml` gating the crate (rustfmt, clippy `-D warnings`, `cargo test`).

No Python code changes. No server behavior yet.

## Capabilities

### New Capabilities

- **mcp-server-runtime**: the MCP server process — its configuration layer lands here; layout, transport, TLS, auth,
  and runtime requirements are added to this capability by later proposals.

### Modified Capabilities

- *None.* Purely additive; the Python CLI and existing capabilities are untouched.

## Dependencies

- None — first proposal in the MCP series.

**Depended on by:** `add-mcp-server-runtime`, `add-mcp-cli-adapter`, `revise-dockerfile-for-mcp` (and everything
downstream).

## Impact

**Code** (all new): `mcp-server/Cargo.toml`, `mcp-server/src/main.rs`, `mcp-server/src/config.rs`,
`mcp-server/tests/`, `.github/workflows/rust-checks.yml`, `.gitignore` entry for `mcp-server/target/`.

**Dependencies**: `serde`, `thiserror` (configuration layer). Later proposals add `rmcp`/`axum`/`tokio`/`tracing`
when their behavior lands. Rust edition 2024, MSRV 1.88.

**Tooling**: Rust toolchain required on dev machines and CI.

**Out of scope** (separate proposals): health endpoint/graceful shutdown/logging (`add-mcp-server-runtime`), MCP
transport, CLI adapter, tools, TLS, auth, Docker, docs.

## Non-goals

- Binding a socket or serving any endpoint.
- Exposing MCP tools.
- Any change to the Python CLI or its packaging.
