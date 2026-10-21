# MCP Server Runtime

## ADDED Requirements

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
