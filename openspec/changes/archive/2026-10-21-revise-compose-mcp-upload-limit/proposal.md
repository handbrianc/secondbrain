# MCP Upload Cap 100 MB — Proposal

## Why

The shipped 10 MB decoded cap rejects large PDFs at the transport before the
CLI ever sees them (HTTP 413 on the `/mcp` body), while the CLI's own
per-file processing cap is 100 MiB — the transport was the binding constraint
an order of magnitude below what the ingestion pipeline supports. The
deployment's document corpus includes multi-megabyte PDFs, and the async
ingestion workflow (`add-mcp-async-ingestion`) exists precisely so large
files can ingest without a client-side timeout; a 10 MB upload cap would
still turn those files away first.

## What Changes

- **`.env.docker`**: `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES=104857600` (100 MB),
  active with a comment carrying the derivation and the CLI-cap caveat. The
  derived `/mcp` request-body budget grows with it automatically
  (`ceil(cap × 4/3) + 1 MiB` ≈ 141 MB) — both enforcement points (the rmcp
  transport's `with_max_request_body_bytes` and the axum `DefaultBodyLimit`
  layer) already derive from this one variable, so no code changes.
- **Documentation**: the docker guide's production-stack section notes the
  stack's 100 MB cap. The server README and the MCP guide keep documenting
  the unchanged code default (10 MB) — the server binary stays conservative
  for hosts that do not override it.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the 100 MB upload-cap requirement for the
  production stack (set via the env file; derived body budget scales with
  it; the CLI's 100 MiB per-file cap remains the ingest-time ceiling).

## Dependencies

- Requires: `revise-compose-production-stack` (the stack whose env file is
  revised), `add-mcp-upload-tool` (the tool whose cap is configured).

**Depended on by:** `add-mcp-async-ingestion` (large uploads are the primary
motivation for polling instead of blocking).

## Impact

**Code**: none (`.env.docker` only).

**Docs**: `docs/developer-guide/docker.md`.

## Non-goals

- Raising the compiled-in default cap: the server binary keeps the 10 MB
  default so bare `docker run` / non-stack deployments stay conservative;
  the stack-level override is the documented mechanism.
- The CLI's 100 MiB per-file processing cap: unchanged — 104857600 bytes
  (100 MB) sits just under it, so submissions accepted by the tool are
  processable by the CLI.
