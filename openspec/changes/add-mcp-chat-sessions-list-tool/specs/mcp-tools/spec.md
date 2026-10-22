# MCP Tools

## ADDED Requirements

### Requirement: Chat session listing tool

The MCP server SHALL expose a `chat_list_sessions` tool that returns the CLI's session listing
(`chat --list-sessions`) as text content.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `chat_list_sessions` with an empty input schema (no parameters)

#### Scenario: Listing sessions

- **WHEN** the tool is called
- **THEN** the result carries the CLI's session listing output (one `session_id: N messages (created: ...)` line per session)

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis
