# MCP Upload Tool — Proposal

## Why

Ingestion currently requires documents to already exist inside the workspace the MCP server serves: the
`ingest_documents` tool only accepts a path. A client holding a local document must copy it into the mounted
workspace by out-of-band means (volume mount, scp, manual copy) before it can reach Qdrant. A `upload_document`
MCP tool closes that gap in one call: submit the file's bytes (base64) with a filename, the server stores it inside
the workspace and ingests it through the existing `ingest_documents` flow (resolve → confine → CLI `ingest`). No
Python changes and no new pipeline are needed — the upload composes the ingest tool that already works.

Staying inside the MCP tool surface (instead of a parallel HTTP upload route) keeps one protocol for clients: the
new tool rides the existing `/mcp` endpoint, so bearer auth, host allow-list, and TLS coverage are inherited without
new middleware. The cost is the JSON-RPC envelope: base64 inflates payloads by ~33% and requests are buffered
(~3–4× the file size in memory) — acceptable for a local-first ingestion server with a conservative 10 MB default cap (configurable upward via
`SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`), and streamed/chunked upload would require session state that stateless mode
does not have.

## What Changes

- **`upload_document` MCP tool** (registered beside `ingest_documents`, `search`, `chat_*`):
  - Input: `filename` (required string), `content_base64` (required string), plus the ingest tool's optional
    parameters (`skip_existing` default true, `chunk_size`, `chunk_overlap`, `batch_size`, `cores`).
  - Validation before anything is stored: base64 decode errors and decoded content over
    `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (default 10485760 = 10 MB — a conservative floor below the CLI's 100 MiB
    per-file processing cap; raise the variable to admit larger files, the CLI's own cap still applies at ingest)
    → tool error, nothing stored.
  - Storage: the decoded bytes are saved under `SECONDBRAIN_MCP_UPLOAD_DIR` (default `<workspace root>/uploads`)
    using the filename reduced to its bare name; the directory must resolve inside `SECONDBRAIN_MCP_WORKSPACE_ROOT`
    (fail-fast startup error otherwise); collision with an existing file → tool error (no silent overwrite).
  - Ingestion: after storing, the server runs the same confined ingest invocation the `ingest_documents` tool uses
    (extracted shared helper, behavior-preserving refactor) — no new ingestion pipeline. The CLI's existing gates
    (extension allow-list, per-file size cap) keep applying at ingest time.
  - Outcomes: success → tool result text carrying the stored path, the CLI ingest summary, and the deletion of the
    staged file (the upload directory is transient staging); stored but ingestion failed → tool error carrying the
    stored path and CLI diagnostics (file retained for re-ingest); a deletion that itself fails after a successful
    ingest is reported inside the success result without failing the call; decode, filename, and collision failures
    → tool error, nothing stored.
- **Configuration**: new `SECONDBRAIN_MCP_UPLOAD_DIR` and `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (10 MB default),
  documented in the MCP README's server configuration table (enforced by the docs-completeness test).
- **Request body limit**: the `/mcp` endpoint's request body limit is raised from the framework default (2 MB) to a
  value derived from `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (base64 + JSON overhead), so an upload at the configured
  limit is accepted.
- **Documentation**: `mcp-server/README.md` gains an `upload_document` row in the tool reference table and a
  dedicated tool section (parameters with defaults, result shape, error behavior, base64 payload overhead), a
  JSON-RPC wire example of an upload call, and the two new rows in the server configuration table — completeness
  enforced by `tests/test_docs/test_mcp_docs.py`. The MkDocs guide (`docs/developer-guide/mcp.md`, owned by
  `add-mcp-docs-site-integration`) picks up the upload tool in its tool examples and troubleshooting table once
  that page lands.

No new HTTP routes. The Python CLI is unchanged.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the upload tool requirements (discovery/schema, content validation, storage, and the
  post-upload ingestion contract via the shared ingest helper).
- **mcp-server-runtime** — adds the request-body-size requirement so `/mcp` accepts upload-sized JSON-RPC bodies.
- **mcp-documentation** — adds the upload tool's documentation requirement (tool reference section, configuration
  rows, wire example).

## Dependencies

- Requires: `add-mcp-streamable-http-transport` (server and tool router exist), `add-mcp-cli-adapter` +
  `add-mcp-cli-env-passthrough` (subprocess execution), `add-mcp-ingest-tool` (the ingest invocation being reused),
  `add-mcp-ingest-path-confinement` (the stored path must pass confinement), `add-mcp-readme-feature-docs` (the
  README structure and docs-completeness test this change extends).

**Depended on by:** none yet.

## Impact

**Code**: `mcp-server/src/server.rs` (register the upload tool), new `mcp-server/src/tools/upload.rs` (params,
base64 decoding, size/filename/collision validation, outcome mapping), `mcp-server/src/tools/ingest.rs` (extract the
shared ingest invocation), `mcp-server/src/main.rs` (body-limit wiring on the router), `mcp-server/src/config.rs`
(two new variables), `mcp-server/README.md` (config rows, `upload_document` tool section, wire example),
`docs/developer-guide/mcp.md` (upload coverage once the page lands — owned by `add-mcp-docs-site-integration`),
new integration tests (`mcp-server/tests/tools_upload.rs`
and confinement cases).

**Dependencies**: `base64` crate; no new axum features (multipart is not needed).

## Non-goals

- Machine-readable ingest summaries — the CLI limitation stands; tool results wrap the CLI's prose summary.
- Store-only uploads — the tool always ingests; a failed ingest leaves the file stored and callers can re-ingest it
  via `ingest_documents`.
- Overwrite or unique-naming collision policies — tool error on collision only in this change.
- Multi-file/batch uploads — one file per tool call.
- Streamed or chunked upload (append protocol) — needs cross-request state that stateless MCP mode does not provide;
  revisiting requires a session-mode change first.
- MIME sniffing or content-type-based routing — ingestion support is determined by the file extension, as in the CLI.
- Fetching documents from remote URLs — remains the ingest tool's documented non-goal.
