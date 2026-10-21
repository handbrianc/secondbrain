# mcp-documentation Specification

## Purpose
The mcp-documentation capability covers the user- and developer-facing documentation for MCP-specific features: tool usage, upload flow, configuration variables, and deployment guides, kept accurate with the shipped behavior. add-mcp-upload-tool. Update Purpose after archive.

## Requirements

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

### Requirement: Feature-set README with the MCP server

The MCP server source tree SHALL contain a `README.md` documenting the exposed feature set: every registered MCP tool
(name, purpose, parameters with defaults, result shape, error behavior), all `SECONDBRAIN_MCP_*` server variables,
the Python `SECONDBRAIN_*` integration surface (external LLM, embedding/vector model API, Qdrant, SQLite), optional
HTTPS (TLS) setup, bearer-token auth, and wire-level usage examples.

#### Scenario: Tool reference completeness

- **WHEN** the README is checked against the tools registered in `mcp-server/src/tools/`
- **THEN** every tool name appears with its parameter list and defaults

#### Scenario: Configuration reference completeness

- **WHEN** the README is checked against the variables parsed by `mcp-server/src/config.rs`
- **THEN** every `SECONDBRAIN_MCP_*` variable appears with its default and meaning

#### Scenario: Wire-level example works as documented

- **WHEN** a reader follows the README's JSON-RPC-over-HTTPS example against a running (test-configuration) server
- **THEN** the request/response shapes match the documented examples

### Requirement: Automated documentation completeness check

A test SHALL verify documentation completeness so it cannot silently drift: every registered tool name and every
`SECONDBRAIN_MCP_*` variable from the config source of truth MUST appear in `mcp-server/README.md`.

#### Scenario: Missing tool documented as failure

- **WHEN** a new MCP tool is registered but not documented
- **THEN** the documentation completeness test fails

### Requirement: Documentation integrated into the docs site

The project documentation site SHALL include an MCP server guide (`docs/developer-guide/mcp.md`) linked from the
navigation, and the Docker guide SHALL reflect the MCP server as the container's primary function.

#### Scenario: Docs build gate

- **WHEN** `mkdocs build --strict` runs
- **THEN** it passes with the MCP pages included and no broken links

#### Scenario: Docker guide accuracy

- **WHEN** a reader consults the Docker guide
- **THEN** it describes the MCP-server-primary container and env-file configuration,
  with no stale "application runs natively / Docker only for Qdrant" statement
