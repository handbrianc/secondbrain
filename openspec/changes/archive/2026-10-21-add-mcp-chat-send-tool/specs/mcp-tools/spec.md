# MCP Tools

## ADDED Requirements

### Requirement: Chat send tool

The MCP server SHALL expose a `chat_send` tool that submits one query into a chat session by driving the secondbrain
CLI (`chat <query> --session <id>` with mapped optional flags and `SECONDBRAIN_SHOW_THINKING=0` in the subprocess
environment), and SHALL return the session id with the answer text.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `chat_send`
- **AND** its input schema declares `query` (string, required), `session_id` (string, optional), `top_k` (integer,
  optional), `temperature` (number, optional), `model` (string, optional)

#### Scenario: New session gets a generated id

- **WHEN** the tool is called without `session_id`
- **THEN** the server generates a UUID v4, passes it to the CLI as `--session <id>`, and returns it in the result
  (the CLI auto-creates the session silently, so no `Created new session:` line appears)

#### Scenario: Answer is extracted cleanly

- **WHEN** the CLI stdout consists of a `▸ Thinking: ...` indicator line followed by the streamed answer
- **THEN** the returned `answer` is the stdout with every `▸ Thinking:`-prefixed line stripped, preserving the rest
- **AND** the subprocess environment contained `SECONDBRAIN_SHOW_THINKING=0` for this call

#### Scenario: Existing session continues

- **WHEN** the tool is called with a `session_id` that already exists
- **THEN** the query is appended to that session's context (CLI receives `--session <existing-id>`) and the returned
  `session_id` matches

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero (e.g. LLM unreachable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis
