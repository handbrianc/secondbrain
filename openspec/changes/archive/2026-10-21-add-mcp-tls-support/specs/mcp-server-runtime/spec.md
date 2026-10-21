# MCP Server Runtime

## ADDED Requirements

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
