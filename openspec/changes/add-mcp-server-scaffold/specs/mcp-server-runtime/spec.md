# MCP Server Runtime

## ADDED Requirements

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
