# MCP Chat History Tool — Proposal

## Why

To resume or audit a chat session, callers need its conversation history. The CLI provides
`secondbrain chat --history --session <id>` (human-readable rendering; exits non-zero for unknown sessions). This
proposal wraps that single flag as the `chat_get_history` MCP tool — its own unit of work, independent of the send
and listing tools.

## What Changes

- **`chat_get_history` MCP tool**: input `session_id` (required); CLI `chat --history --session <id>`; the CLI's
  history rendering returned as text content; unknown session (CLI non-zero exit) → tool error.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the chat history requirement.

## Dependencies

- Requires: `add-mcp-streamable-http-transport`, `add-mcp-cli-adapter`.

**Depended on by:** `add-mcp-readme-feature-docs`.

## Impact

**Code**: `mcp-server/src/tools/chat.rs` (history), new fixture + tests.

**Dependencies**: none beyond existing.

## Non-goals

- Structured/JSON history (message-level JSON requires a Python CLI change; follow-up candidate).
- Pagination/streaming of long histories (full rendering per call, v1).
