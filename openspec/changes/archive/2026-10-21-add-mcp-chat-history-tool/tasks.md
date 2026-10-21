# MCP Chat History Tool — Tasks

## 1. Tool implementation

- [x] 1.1 Add `ChatHistoryParams` (session_id) to `mcp-server/src/tools/chat.rs`, registered via `#[tool]`; argv `["chat", "--history", "--session", <id>]`; CLI stdout returned as text content; exit ≠ 0 → error result

## 2. Tests proving the unit of work

- [x] 2.1 Fixture `stub_chat_history.sh` (prints a canned history block; exits 1 when the requested session is `unknown-session` or absent)
- [x] 2.2 Unit test: argv construction
- [x] 2.3 Integration `tests/tools_chat_history.rs` (full HTTP round trip): known session → history text; unknown session → error; tools/list shows the tool with the required `session_id`
