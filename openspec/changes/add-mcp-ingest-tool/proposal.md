# MCP Ingest Tool — Proposal

## Why

File ingestion is the secondbrain write path (documents → chunks → embeddings → Qdrant). The CLI's `ingest` command
is fully featured (single file or directory, recursive, chunk sizing, dedup-by-hash skip-existing, process-pool
parallelism) but emits human-prose output. This proposal exposes ingestion as the `ingest_documents` MCP tool: one
unit of work — parameter mapping, execution through the CLI adapter, and result/error surfacing. Path confinement
(the workspace-root allow-list that stops callers ingesting arbitrary container paths) is an independently
rejectable security decision and gets its own proposal: `add-mcp-ingest-path-confinement`.

## What Changes

- **`ingest_documents` MCP tool**:
  - Input: `path` (required; relative paths resolve against `SECONDBRAIN_MCP_WORKSPACE_ROOT`), `recursive`
    (default false), `skip_existing` (default true), `chunk_size`, `chunk_overlap`, `batch_size`, `cores` (optional
    integers).
  - Execution: CLI `ingest <resolved-path> [-r] [--no-skip-existing (when skip_existing=false)] [--chunk-size N]
    [--chunk-overlap N] [-b N] [-c N]`.
  - Output: tool result text carrying the CLI's human-readable ingest summary (documented limitation — the CLI has
    no JSON ingest output); failures → error result with captured diagnostics.

No Python changes. No path validation beyond relative resolution (confinement proposal follows).

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the ingest tool requirements (confinement added by its follow-up).

## Dependencies

- Requires: `add-mcp-streamable-http-transport`, `add-mcp-cli-adapter`, `add-mcp-cli-env-passthrough`.

**Depended on by:** `add-mcp-ingest-path-confinement`, `add-mcp-e2e-smoke`, `add-mcp-readme-feature-docs`.

## Impact

**Code**: `mcp-server/src/tools/ingest.rs`, new tests.

**Dependencies**: none beyond existing.

## Non-goals

- Path confinement/validation (separate proposal: `add-mcp-ingest-path-confinement`).
- Remote/URL ingestion (files must exist in the mounted workspace; client-side upload helpers are a future proposal).
- Machine-readable ingest summaries (requires a Python CLI change; documented follow-up candidate).
- Ingest progress streaming (SSE) — the tool result arrives when ingestion completes.
