# MCP Documentation

## ADDED Requirements

### Requirement: Upload tool and configuration documentation

The MCP README SHALL document the upload surface: an `upload_document` row in the tool reference table, a dedicated
tool section (parameters with defaults, result shape, error behavior, and a base64 payload-overhead note — the wire
payload is ~4/3 of the file size), rows for `SECONDBRAIN_MCP_UPLOAD_DIR` and `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` in
the server configuration table (stating the 10 MB default and that the variable raises it), and a JSON-RPC wire
example of an upload call. The documentation-completeness test SHALL cover the new tool and both variables.

#### Scenario: Tool reference covers the upload tool

- **WHEN** the README is checked against the tools registered in `mcp-server/src/tools/`
- **THEN** `upload_document` appears with its parameter list, defaults, result shape, and error behavior

#### Scenario: Configuration rows state the default and the override

- **WHEN** the README is checked against the variables parsed by `mcp-server/src/config.rs`
- **THEN** `SECONDBRAIN_MCP_UPLOAD_DIR` and `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` appear with their defaults
- **AND** the `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` row states the 10 MB default and how to configure a larger limit

#### Scenario: Upload wire example matches reality

- **WHEN** a reader follows the README's upload JSON-RPC example against a running (test-configuration) server
- **THEN** the request/response shapes match, and the example notes the ~4/3 base64 payload overhead

#### Scenario: Completeness test covers the new surface

- **WHEN** the upload tool or an upload variable is registered but missing from the README
- **THEN** the documentation completeness test fails
