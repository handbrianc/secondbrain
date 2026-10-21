# MCP Chat Sessions List Tool — Tasks

## 1. Tool implementation

- [x] 1.1 Add empty-params `chat_list_sessions` to `mcp-server/src/tools/chat.rs`, registered via `#[tool]`; argv `["chat", "--list-sessions"]`; CLI stdout returned as text content; exit ≠ 0 → error result

## 2. Tests proving the unit of work

- [x] 2.1 Fixture `stub_chat_sessions.sh` (prints the CLI session-table format; exits 0; failure variant exits 1)
- [x] 2.2 Unit test: argv construction (no extra flags)
- [x] 2.3 Integration `tests/tools_chat_list.rs` (full HTTP round trip): tools/call → session table text; tools/list shows the tool with empty input schema; CLI failure → error result
