# MCP Server Runtime

## ADDED Requirements

### Requirement: Configurable logging

The server SHALL initialize structured logging whose level filter is controlled by `SECONDBRAIN_MCP_LOG_LEVEL`,
and SHALL emit its lifecycle and request events through it.

#### Scenario: Log level respected

- **WHEN** the server runs with `SECONDBRAIN_MCP_LOG_LEVEL=warn`
- **THEN** debug and info events are suppressed while warn and error events are emitted

#### Scenario: Debug verbosity shows detail

- **WHEN** the server runs with `SECONDBRAIN_MCP_LOG_LEVEL=debug`
- **THEN** debug-level events (e.g. request handling) are emitted
