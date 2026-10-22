# MCP Chat Sessions List Tool — Proposal

## Why

With `add-mcp-chat-send-tool` covering writes, callers need to discover which chat sessions exist before resuming
one. The CLI already provides `secondbrain chat --list-sessions` (a stable human-readable table:
`session_id: N messages (created: ...)`). This proposal wraps that single flag as the `chat_list_sessions` MCP tool —
its own unit of work (one tool, one flag, text passthrough), independent of the send and history tools.

## What Changes

- **`chat_list_sessions` MCP tool**: no parameters; CLI `chat --list-sessions` through the adapter; the CLI's session
  listing is returned as text content (documented human format — see the design doc's CLI-constraints note).

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the chat session listing requirement.

## Dependencies

- Requires: `add-mcp-streamable-http-transport`, `add-mcp-cli-adapter`.

**Depended on by:** `add-mcp-readme-feature-docs`.

## Impact

**Code**: `mcp-server/src/tools/chat.rs` (list), new fixture + tests.

**Dependencies**: none beyond existing.

## Non-goals

- Structured/JSON session listing (requires a Python CLI change; follow-up candidate).
- Session deletion (interactive CLI prompt; see `add-mcp-chat-send-tool` non-goals).
