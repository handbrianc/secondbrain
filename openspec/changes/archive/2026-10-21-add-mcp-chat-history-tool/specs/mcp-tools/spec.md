# MCP Tools

## ADDED Requirements

### Requirement: Chat history tool

The MCP server SHALL expose a `chat_get_history` tool that returns a session's conversation history
(`chat --history --session <id>`) as text content, and SHALL map a missing session to a tool error.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `chat_get_history`
- **AND** its input schema declares `session_id` (string, required)

#### Scenario: History of an existing session

- **WHEN** the tool is called with a `session_id` that exists
- **THEN** the result carries the CLI's history rendering for that session

#### Scenario: History of an unknown session

- **WHEN** the tool is called with a `session_id` that does not exist
- **THEN** the tool result is an error reporting the session was not found (surfaced from the CLI's non-zero exit)

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero for any other reason (e.g. SQLite storage unavailable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis
