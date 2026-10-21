# mcp-server-runtime Specification

## Purpose
The mcp-server-runtime capability covers the Rust MCP server's runtime behavior: the streamable-HTTP JSON-RPC transport, request gating (Host allowlist, auth, TLS), tool dispatch to the secondbrain CLI as a subprocess, worker lifecycle (caps, upload reaping), health reporting, and logging. add-mcp-http-allowed-hosts. Update Purpose after archive.

## Requirements

### Requirement: MCP endpoint Host-header allow-list

The MCP endpoint at `/mcp` SHALL validate the request `Host` header against an allow-list, backed by the
`SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` configuration variable, as protection against DNS rebinding. The health
endpoint `/healthz` SHALL NOT be subject to this check.

#### Scenario: Foreign Host rejected by default

- **WHEN** `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` is unset and a client POSTs to `/mcp` with a `Host` header outside
  rmcp's built-in allow-list (`localhost`, `127.0.0.1`, `::1`)
- **THEN** the response status is 403 with body `Forbidden: Host header is not allowed`
- **AND** the same request with a `Host` header of `localhost`, `127.0.0.1`, or `::1` (any port) succeeds

#### Scenario: Configured host is accepted

- **WHEN** `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS=ops.internal.example.com` and a client POSTs to `/mcp` with
  `Host: ops.internal.example.com:8080`
- **THEN** the response status is 200 and the body contains the tool registry

#### Scenario: Configured list replaces the default

- **WHEN** `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` is set to a value not including the loopback names
- **THEN** a request with `Host: localhost` is rejected with 403
- **AND** a request with the configured host succeeds

#### Scenario: Port matching semantics

- **WHEN** an allow-list entry specifies a port (e.g. `ops.internal.example.com:8080`)
- **THEN** only that exact host and port are accepted
- **WHEN** an allow-list entry specifies no port
- **THEN** that host is accepted on any port

#### Scenario: Health endpoint is not affected

- **WHEN** a client GETs `/healthz` with any `Host` header
- **THEN** the response is 200 regardless of the allow-list

#### Scenario: Invalid configuration is rejected at startup

- **WHEN** `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` is set but contains no valid entry (e.g. only whitespace or commas)
- **THEN** the server refuses to start, exits non-zero, and the error message names `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS`

#### Scenario: Empty and unset values are equivalent

- **WHEN** `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` is unset or empty
- **THEN** the rmcp default allow-list (`localhost`, `127.0.0.1`, `::1`) remains active

### Requirement: MCP endpoint at /mcp

The server SHALL expose the MCP Streamable HTTP endpoint at `POST /mcp`, handling JSON-RPC 2.0 requests (`tools/list`,
`tools/call`) and replying with single-body `application/json` responses.

#### Scenario: tools/list over POST

- **WHEN** a client POSTs a valid JSON-RPC `tools/list` request to `/mcp` with header
  `Accept: application/json, text/event-stream`
- **THEN** the response status is 200 with content type `application/json`
- **AND** the body contains a `tools` array (empty in this change)

#### Scenario: Unknown tool call is a JSON-RPC error

- **WHEN** a client POSTs `tools/call` for a tool that is not registered
- **THEN** the response is an `application/json` JSON-RPC 2.0 error result (method/tool not found), not a server crash

#### Scenario: Content negotiation on the MCP endpoint

- **WHEN** a POST to `/mcp` lacks an `Accept` header including `application/json` or `text/event-stream`
- **THEN** the server rejects the request with HTTP 406 (Not Acceptable)

#### Scenario: GET and DELETE are not used in stateless mode

- **WHEN** a client sends `GET /mcp` or `DELETE /mcp`
- **THEN** the server responds 405 (Method Not Allowed)

### Requirement: Stateless protocol mode

The server SHALL operate in stateless MCP protocol mode (2026-07-28): it SHALL NOT require an initialize handshake,
SHALL NOT issue `Mcp-Session-Id` response headers for stateless-capable clients, and SHALL serve each request
independently.

#### Scenario: Request without a session

- **WHEN** a client POSTs `tools/list` with no prior initialize request and no `Mcp-Session-Id` header
- **THEN** the request succeeds with 200

#### Scenario: No session id issued

- **WHEN** the server replies to a stateless `tools/list` request
- **THEN** the response carries no `Mcp-Session-Id` header

### Requirement: Server metadata

The server SHALL identify itself as `secondbrain-mcp` with its crate version, and SHALL provide an instructions
string summarizing its capability groups (file ingestion, semantic search, chat sessions).

#### Scenario: Server information in tools/list response

- **WHEN** a client receives a successful `tools/list` response
- **THEN** `serverInfo.name` is `secondbrain-mcp` and `serverInfo.version` matches the crate version
- **AND** `instructions` mentions ingestion, search, and chat

### Requirement: rmcp client interoperability

The server SHALL be usable by a standard MCP client built with the same protocol revision (rmcp client), performing
the full request cycle without session state.

#### Scenario: Real client round trip

- **WHEN** an rmcp client connects to `/mcp` via `StreamableHttpClientTransport` and requests `tools/list`
- **THEN** the call succeeds and returns the tool list

### Requirement: Configurable logging

The server SHALL initialize structured logging whose level filter is controlled by `SECONDBRAIN_MCP_LOG_LEVEL`,
and SHALL emit its lifecycle and request events through it.

#### Scenario: Log level respected

- **WHEN** the server runs with `SECONDBRAIN_MCP_LOG_LEVEL=warn`
- **THEN** debug and info events are suppressed while warn and error events are emitted

#### Scenario: Debug verbosity shows detail

- **WHEN** the server runs with `SECONDBRAIN_MCP_LOG_LEVEL=debug`
- **THEN** debug-level events (e.g. request handling) are emitted

### Requirement: TLS termination as an optional capability

The server MAY serve its endpoints over TLS using rustls (via `axum-server`). TLS is an optional capability, off by
default: a server deployed without TLS SHALL function fully over plaintext HTTP. TLS is controlled by
`SECONDBRAIN_MCP_HTTP_TLS_ENABLED` (default `false`), with the certificate chain and private key loaded from
`SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` and `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH` (PEM files) when enabled.

#### Scenario: TLS disabled or absent — fully functional server

- **WHEN** `SECONDBRAIN_MCP_HTTP_TLS_ENABLED` is unset or `false` (TLS simply not enabled by the deployment)
- **THEN** the server binds plaintext HTTP and `/healthz` responds over plain HTTP as before
- **AND** all other server capabilities are unaffected

#### Scenario: TLS enabled serves HTTPS

- **WHEN** TLS is enabled with valid PEM cert/key files
- **THEN** the server completes a TLS handshake on the configured address
- **AND** `GET /healthz` returns 200 over HTTPS with the same body as over HTTP
- **AND** a MCP `tools/list` POST succeeds over HTTPS

#### Scenario: No plaintext fallback while TLS is enabled

- **WHEN** TLS is enabled
- **THEN** the configured listener speaks TLS only (a plain HTTP request to that port does not complete)

### Requirement: TLS configuration validation when enabled

When TLS is enabled, the server SHALL refuse to start if the certificate/key paths are missing, unreadable, or do not
parse as PEM, with an error naming the offending `SECONDBRAIN_MCP_HTTP_TLS_*` variable. When TLS is disabled, the
certificate/key variables SHALL be ignored and no validation applied.

#### Scenario: Missing paths refuse startup (only when TLS enabled)

- **WHEN** TLS is enabled and either path variable is unset
- **THEN** the server exits before binding, naming the missing variable

#### Scenario: Unparseable certificate refuses startup

- **WHEN** TLS is enabled and the cert file is not valid PEM
- **THEN** the server exits before binding, naming `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH`

#### Scenario: Certificate variables ignored when TLS is disabled

- **WHEN** TLS is disabled and the cert/key path variables are set to arbitrary or nonexistent paths
- **THEN** the server starts normally in plaintext (no validation, no error)

### Requirement: Request body size for upload tool calls

The `/mcp` endpoint SHALL accept JSON-RPC request bodies large enough for upload tool calls at the configured
upload limit: the framework default request body limit SHALL be replaced by a limit derived from
`SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` that accounts for base64 expansion (~4/3) and JSON framing, so an
`upload_document` call at the configured limit reaches the tool handler instead of being rejected by the transport.

#### Scenario: Upload at the configured limit is accepted

- **WHEN** a client calls `upload_document` with content at `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (decoded)
- **THEN** the request is not rejected by a default body limit and the tool handler executes

#### Scenario: Raising the limit raises the body budget

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` is increased
- **THEN** the accepted request body size on `/mcp` grows accordingly

### Requirement: Server binds and serves

The server SHALL bind the address from `SECONDBRAIN_MCP_HTTP_BIND_ADDR` and serve requests (plaintext HTTP; TLS is
the optional capability of the TLS proposal) until terminated.

#### Scenario: Default bind address

- **WHEN** the server starts with no `SECONDBRAIN_MCP_HTTP_BIND_ADDR` set
- **THEN** it listens on `0.0.0.0:8080`

#### Scenario: Custom bind address

- **WHEN** the server starts with `SECONDBRAIN_MCP_HTTP_BIND_ADDR=127.0.0.1:<ephemeral>`
- **THEN** it listens on that address and accepts requests

### Requirement: Health endpoint

The server SHALL expose `GET /healthz` returning HTTP 200 with a JSON body `{"status":"ok"}`, independent of MCP
protocol handling.

#### Scenario: Healthy server reports ok

- **WHEN** a client sends `GET /healthz` to the running server
- **THEN** the response status is 200 with content type `application/json`
- **AND** the body parses to JSON with `"status"` equal to `"ok"`

### Requirement: MCP server crate in a dedicated source tree

The repository SHALL contain a Rust crate for the MCP server at `mcp-server/`, a top-level directory whose name
clearly indicates it is specifically for MCP server code, with server code in `mcp-server/src/` and integration
tests in their own source tree `mcp-server/tests/`.

#### Scenario: Repository layout

- **WHEN** the repository is inspected after this change
- **THEN** `mcp-server/Cargo.toml` exists and declares the crate `secondbrain-mcp` (edition 2024, rust-version >= 1.88)
- **AND** `mcp-server/src/` contains the server code
- **AND** `mcp-server/tests/` contains integration tests that are separate from inline unit tests
- **AND** no MCP server code exists under `src/secondbrain/` (the Python package)

#### Scenario: Build and test gate

- **WHEN** `cargo build` and `cargo test` run in `mcp-server/`
- **THEN** both succeed

### Requirement: Configuration from environment

The server's configuration layer SHALL resolve all of its settings from `SECONDBRAIN_MCP_*` environment variables
with documented defaults, and the entrypoint SHALL refuse to start with an error naming the offending variable when
a value is invalid.

| Variable | Default |
| --- | --- |
| `SECONDBRAIN_MCP_HTTP_BIND_ADDR` | `0.0.0.0:8080` |
| `SECONDBRAIN_MCP_HTTP_TLS_ENABLED` | `false` |
| `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` | none (required when TLS enabled — validated by the TLS proposal) |
| `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH` | none (required when TLS enabled) |
| `SECONDBRAIN_MCP_AUTH_TOKEN` | unset (auth disabled) |
| `SECONDBRAIN_MCP_CLI_BIN` | `secondbrain` |
| `SECONDBRAIN_MCP_WORKSPACE_ROOT` | `.` |
| `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` | `900` |
| `SECONDBRAIN_MCP_LOG_LEVEL` | `info` |

#### Scenario: Defaults resolved with no configuration

- **WHEN** the configuration is resolved with no `SECONDBRAIN_MCP_*` variables set
- **THEN** it yields bind address `0.0.0.0:8080`, TLS disabled, auth disabled, CLI binary `secondbrain`, workspace
  root `.`, subprocess timeout 900 seconds, and log level `info`

#### Scenario: Override via environment

- **WHEN** `SECONDBRAIN_MCP_HTTP_BIND_ADDR=127.0.0.1:9200` and `SECONDBRAIN_MCP_LOG_LEVEL=debug` are set
- **THEN** the resolved configuration carries those values

#### Scenario: Invalid value refuses to start

- **WHEN** `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS=zero` is set and the entrypoint runs
- **THEN** it exits with a non-zero status before any runtime behavior begins
- **AND** the error output names `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS`

### Requirement: Graceful shutdown

The server SHALL shut down gracefully on SIGINT and SIGTERM, finishing in-flight requests before exit.

#### Scenario: Container-style termination

- **WHEN** the server receives SIGTERM while idle
- **THEN** it stops accepting connections and exits with status 0

#### Scenario: In-flight request completes

- **WHEN** the server receives SIGTERM while a request is being handled
- **THEN** the in-flight response is delivered before the process exits

#### Scenario: SIGINT termination

- **WHEN** the server receives SIGINT (interactive stop)
- **THEN** it exits with status 0 like on SIGTERM

### Requirement: Optional static bearer authentication

The server SHALL enforce bearer authentication on `/mcp` if and only if `SECONDBRAIN_MCP_AUTH_TOKEN` is set to a
non-empty value. When enforced, requests MUST carry `Authorization: Bearer <token>` matching the configured token,
compared in constant time; other outcomes receive HTTP 401 with a `WWW-Authenticate: Bearer` header.

#### Scenario: Auth disabled by default

- **WHEN** `SECONDBRAIN_MCP_AUTH_TOKEN` is unset or empty
- **THEN** MCP requests are accepted without an `Authorization` header

#### Scenario: Missing header is rejected

- **WHEN** the token is configured and a request to `/mcp` carries no `Authorization` header
- **THEN** the response is 401 with a `WWW-Authenticate: Bearer` header

#### Scenario: Wrong token is rejected

- **WHEN** the token is configured and the presented bearer token differs from it
- **THEN** the response is 401

#### Scenario: Prefix of the token is rejected

- **WHEN** the token is configured and the presented bearer token is a strict prefix of it (or it of the presented one)
- **THEN** the response is 401 (constant-time comparison, no length shortcut leakage in the observable outcome)

#### Scenario: Wrong scheme is rejected

- **WHEN** the token is configured and `Authorization: Basic ...` is presented
- **THEN** the response is 401

#### Scenario: Correct token is accepted

- **WHEN** the token is configured and the request presents the exact configured bearer token
- **THEN** the MCP request proceeds normally (e.g. `tools/list` returns 200)

### Requirement: Health endpoint exempt from auth

The `/healthz` endpoint SHALL remain accessible without authentication regardless of the auth configuration, so
container healthchecks and load-balancer probes function.

#### Scenario: Health check without token

- **WHEN** the token is configured and `GET /healthz` is called without an `Authorization` header
- **THEN** the response is 200
