# MCP Documentation

## ADDED Requirements

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
