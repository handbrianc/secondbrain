# MCP Server Runtime

## ADDED Requirements

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
