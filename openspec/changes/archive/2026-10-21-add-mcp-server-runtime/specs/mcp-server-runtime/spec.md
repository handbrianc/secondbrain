# MCP Server Runtime

## ADDED Requirements

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
