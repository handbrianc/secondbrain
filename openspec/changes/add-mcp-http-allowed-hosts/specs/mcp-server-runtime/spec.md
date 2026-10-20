# MCP Server Runtime

## ADDED Requirements

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
