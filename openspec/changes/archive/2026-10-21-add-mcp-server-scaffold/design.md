# MCP Server Architecture — Design

> Shared architecture record for the MCP proposal series (`add-mcp-server-scaffold` and dependents). Each dependent
> proposal references decisions here rather than restating them.

## 1. Purpose and constraint

Expose secondbrain's three capability groups — **file ingestion**, **semantic search**, and **chat sessions** — as an
MCP server, so MCP clients (e.g. Claude Desktop, OpenChamber, other agents) can use secondbrain over HTTP(S).

**Key architectural decision: the Rust MCP server wraps the existing Python CLI via subprocess; it does not
reimplement RAG logic.**

- Single source of truth for ingestion/chunking/embedding/search/RAG behavior stays in `src/secondbrain/`.
- Reimplementing document parsing (PDF/DOCX/audio/image pipelines) in Rust is infeasible and would fork behavior.
- The user requirement "include the CLI tooling for the MCP server to interact with" matches this: the container
  carries both the Rust server binary and the Python CLI; the server drives the CLI.
- Prior art in-repo: `add-conversational-rag` scoped the RAG layer CLI/MCP-agnostic; the CLI surface is already
  machine-usable in the relevant spots (`search --format json`, single-turn `chat "q" --session <id>`).

## 2. Source tree layout (this project)

```
mcp-server/                     # top-level dir, clearly the MCP server code
├── Cargo.toml                  # crate: secondbrain-mcp
├── src/                        # server code
│   ├── main.rs                 # entrypoint: config, router, bind, graceful shutdown
│   ├── config.rs               # SECONDBRAIN_MCP_* parsing/validation
│   ├── cli.rs                  # subprocess CLI adapter (the three adapter proposals)
│   ├── tools/                  # MCP tools: search.rs, ingest.rs, chat.rs (the tool proposals)
│   ├── tls.rs                  # rustls serving (TLS proposal)
│   └── auth.rs                 # bearer middleware (auth proposal)
└── tests/                      # integration tests (own source tree)
    ├── common/                 # ephemeral-port boot helpers, stub-CLI fixtures
    └── *.rs                    # one integration binary per feature area
```

Rust convention: unit tests live inline in `src/`; cross-boundary behavior (HTTP, subprocess, TLS) lives in
`mcp-server/tests/`. Stub CLI executables used by tests are shell scripts under `mcp-server/tests/fixtures/`
(keeps tests hermetic — no Python or Qdrant required).

## 3. Protocol and stack (verified 2026-10)

- **SDK**: `rmcp` 3.5.x (official Rust MCP SDK; implements MCP **2026-07-28**, the current stable protocol revision,
  which is stateless by default; compatible with 2025-11-25 and earlier).
- **Transport**: Streamable HTTP. Single `POST /mcp` endpoint; responses as single `application/json` bodies
  (`json_response(true)` — SSE only if a handler emits notifications, which none do). No `Mcp-Session-Id`, no
  GET/DELETE streams in stateless mode.
- **HTTP/TLS**: `axum` 0.8 router mounted with rmcp's `StreamableHttpService` (a Tower service). TLS via
  `axum-server` 0.8 `tls-rustls` (rustls 0.23) — rmcp provides no server TLS itself.
- **Tool schemas**: `schemars` 1.x derives input JSON Schema from typed parameter structs.

## 4. Environment variables

Two families, both documented in the container (proposals 9-10) and README (proposal 12):

**Server config** (`SECONDBRAIN_MCP_*`, parsed by `mcp-server/src/config.rs` from proposal 1 onward):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECONDBRAIN_MCP_HTTP_BIND_ADDR` | `0.0.0.0:8080` | Listen address |
| `SECONDBRAIN_MCP_HTTP_TLS_ENABLED` | `false` | Serve HTTPS instead of HTTP |
| `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` | — (required if TLS) | PEM certificate chain |
| `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH` | — (required if TLS) | PEM private key |
| `SECONDBRAIN_MCP_AUTH_TOKEN` | unset (open) | Optional static bearer token |
| `SECONDBRAIN_MCP_CLI_BIN` | `secondbrain` | CLI binary the adapter spawns |
| `SECONDBRAIN_MCP_WORKSPACE_ROOT` | `.` | Ingest path allow-list root |
| `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` | `900` | CLI subprocess timeout |
| `SECONDBRAIN_MCP_LOG_LEVEL` | `info` | tracing filter |

**Python passthrough** (inherited verbatim by CLI subprocesses; the container exposes all of them for external
LLM / embedding-model / Qdrant integration):

- Storage: `SECONDBRAIN_QDRANT_URL`, `SECONDBRAIN_QDRANT_API_KEY`, `SECONDBRAIN_QDRANT_COLLECTION`,
  `SECONDBRAIN_STORAGE_BACKEND`, `SECONDBRAIN_SQLITE_PATH`
- Embedding (vector model): `SECONDBRAIN_EMBEDDING_PROVIDER`, `SECONDBRAIN_EMBEDDING_API_BASE`,
  `SECONDBRAIN_EMBEDDING_API_KEY`, `SECONDBRAIN_EMBEDDING_MODEL`, `SECONDBRAIN_EMBEDDING_DIMENSIONS`,
  `SECONDBRAIN_EMBEDDING_BATCH_SIZE`, `SECONDBRAIN_EMBEDDING_TIMEOUT`
- LLM: `SECONDBRAIN_LLM_PROVIDER`, `SECONDBRAIN_OPENAI_BASE_URL`, `SECONDBRAIN_OPENAI_API_KEY`,
  `SECONDBRAIN_ANTHROPIC_API_KEY`, `SECONDBRAIN_LLM_MODEL`, `SECONDBRAIN_LLM_TEMPERATURE`, `SECONDBRAIN_LLM_TIMEOUT`
- Behavior: `SECONDBRAIN_CHUNK_SIZE`, `SECONDBRAIN_CHUNK_OVERLAP`, `SECONDBRAIN_MAX_FILE_SIZE_BYTES`,
  `SECONDBRAIN_LOG_LEVEL`/`SECONDBRAIN_LOG_FORMAT` (CLI's own logging), plus the rest of the
  `SECONDBRAIN_*` surface (config/ typed settings).

Notes:

- The Python CLI loads `.env` from its CWD; the adapter inherits the server's CWD (in the container, `/data/workspace`
  contains no `.env`), so real environment variables are authoritative.
- The adapter passes arguments as an **argv vector — never through a shell** (no interpolation/injection surface).
- For chat calls the adapter sets `SECONDBRAIN_SHOW_THINKING=0` to keep stdout parseable.

## 5. Known CLI constraints (accepted for v1, verified against the code)

- `ingest` has no JSON output → the ingest tool returns the CLI's human-readable stdout as tool text.
- `search --format json` does **not** apply `min-score` (that is table-mode-only, `display.py`) → the search tool
  applies the threshold itself in Rust (default 0.46, matching the CLI default).
- Chat sessions: with an explicit `--session <id>` the CLI auto-creates silently; without one it prints
  `Created new session: <uuid>`. → The server always generates/passes an explicit session id, so parsing is stable.
- `SECONDBRAIN_SHOW_THINKING=0` leaves exactly one line `▸ Thinking: N chars (collapsed)` on stdout → the chat tool
  strips lines with that prefix; the remainder is the answer.
- `chat --delete-session` hardcodes an interactive y/N prompt → session deletion is **not exposed** in v1
  (documented non-goal; follow-up candidate: add a `--yes` flag to the CLI).
- `--show-sources` prints after the answer on stdout with no stable delimiter → sources are **not** returned in v1
  (non-goal; same follow-up path as above).

## 6. Security model

- TLS terminates **in the server** (rustls; axum-server) — an **optional capability** (MAY-level requirements, off by
  default; deployments choose via `SECONDBRAIN_MCP_HTTP_TLS_ENABLED`); when enabled, HTTPS reaches the calling client
  with no sidecar proxy required.
- Auth v1 is an optional **static bearer token** (`SECONDBRAIN_MCP_AUTH_TOKEN`, constant-time comparison, 401 with
  `WWW-Authenticate: Bearer`). `/healthz` stays unauthenticated for orchestrators. Full MCP authorization spec
  conformance (OAuth 2.1 resource server, RFC 9728 metadata) is an explicit non-goal for v1, listed as a follow-up.

## 7. Deployment shape (Dockerfile and compose proposals)

- One image, two runtime modes: `secondbrain-mcp` (default CMD, the MCP server) and `secondbrain` (the CLI).
- `docker-compose.yml`: `mcp-server` is the primary service with a `qdrant` dependency and healthcheck; no
  `cli` service — the stack runs only the server and Qdrant (operator CLI access is out-of-stack).
- `docker-compose.test.yml`: same image wired to the test Qdrant + mock embedding provider + fixture workspace;
  an end-to-end smoke script drives health → tools/list → ingest → search (chat gated on test LLM availability).
- The PyInstaller one-file CLI build in the current Dockerfile is replaced by a wheel install in the runtime stage;
  `scripts/build.sh` / `secondbrain.spec` (host-side packaging) are untouched, with their stale
  `pymongo`/`dotenv` hidden imports flagged for a separate cleanup.

## 8. Atomicity standard of the series

Review pass (2026-10-14) re-decomposed an original 12-proposal draft into the 22 single-unit proposals listed below.
Standard applied: **one independently shippable, independently verifiable unit of behavior per proposal** — tested by
"could this requirement be rejected independently without invalidating its siblings?" Requirements that are facets of
one deliverable (e.g. server metadata inside the transport construction, TLS startup validation inside the TLS mode,
image hygiene attributes inside the image revision) stay together. CI workflows are treated as verification plumbing
and bundled with the unit they gate.

Second pass (2026-10-15): the server's process-runtime behaviors were separated further — serving (bind + `/healthz`),
graceful shutdown, and structured logging are independent units (distinct purposes and verification mechanisms: HTTP
probing vs signal delivery vs log capture). TLS requirements were restated as an **optional capability** (MAY-level,
default off, conditional SHALL only when enabled) rather than a mandatory server property. 24 proposals total.

## 9. Dependency graph of the series

```
Foundation
1  add-mcp-server-scaffold (crate + config + CI gate)
└─ 2  add-mcp-server-runtime (bind + /healthz)
   ├─ 3  add-mcp-graceful-shutdown
   ├─ 4  add-mcp-structured-logging
   └─ 5  add-mcp-streamable-http-transport (/mcp, stateless, JSON)
      ├─ 15 add-mcp-tls-support (OPTIONAL capability, MAY-level) ┐ independent after 5
      └─ 16 add-mcp-bearer-auth                                  ┘

Adapter lane (needs 1)
6  add-mcp-cli-adapter (execution core)
├─ 7  add-mcp-cli-env-passthrough
└─ 8  add-mcp-cli-timeout

Tools lane (needs 5 + 6 + 7; may proceed in parallel)
├─ 9  add-mcp-search-tool
├─ 10 add-mcp-ingest-tool → 11 add-mcp-ingest-path-confinement
├─ 12 add-mcp-chat-send-tool (8 recommended before production use)
├─ 13 add-mcp-chat-sessions-list-tool (needs 5 + 6)
└─ 14 add-mcp-chat-history-tool (needs 5 + 6)

Deployment lane
17 revise-dockerfile-for-mcp (needs 1, 2; benefits from 5 for the smoke)
18 harden-compose-qdrant-service (first compose change)
19 revise-compose-production-stack (needs 17 + 18)
21 revise-compose-test-stack (needs 17)
22 add-mcp-e2e-smoke (needs 9-12, 19, 21)

Documentation
23 add-mcp-readme-feature-docs (needs 5, 9-16; assumes 17-22)
└─ 24 add-mcp-docs-site-integration
```

Proposals 9-16 can proceed in parallel once their prerequisites land. 23-24 last.
