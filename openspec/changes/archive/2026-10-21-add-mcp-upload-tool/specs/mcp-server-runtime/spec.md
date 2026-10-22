# MCP Server Runtime

## ADDED Requirements

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
