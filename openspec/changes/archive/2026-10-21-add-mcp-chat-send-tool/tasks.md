# MCP Chat Send Tool — Tasks

## 1. Tool implementation

- [x] 1.1 Create `mcp-server/src/tools/chat.rs` with `ChatSendParams` (query, session_id, top_k = 20, temperature = 0.1, model — `serde::Deserialize` + `schemars::JsonSchema`) registered via `#[tool]`
- [x] 1.2 Argv: `["chat", "--session", <id>, (--top-k N)?, (--temperature T)?, (--model M)?, "--", query]`; when `session_id` absent generate UUID v4 (`uuid` crate); unit-test argv construction
- [x] 1.3 Answer extraction: strip every line whose first grapheme cluster starts with `▸ Thinking:` from stdout; the remainder (trimmed of a single trailing newline) is the answer; result JSON `{"session_id", "answer"}` as text content
- [x] 1.4 Set `SECONDBRAIN_SHOW_THINKING=0` as a per-call env override (adapter override map from `add-mcp-cli-env-passthrough`)
- [x] 1.5 Map outcomes: success → JSON text block; exit ≠ 0 → error result with truncated captured streams

## 2. Tests proving the unit of work

- [x] 2.1 Fixtures: `stub_chat_send.sh` (prints a `▸ Thinking: 123 chars (collapsed)` line then a known answer; records the `SECONDBRAIN_SHOW_THINKING` value it observed to a temp file; exits 0), `stub_chat_send_fail.sh` (exit 1 + stderr)
- [x] 2.2 Unit tests: thinking-line stripping (leading, trailing, and multiple lines; answer preserved verbatim otherwise); UUID v4 generation and uniqueness; argv construction per flag combination
- [x] 2.3 Integration `tests/tools_chat_send.rs` (full HTTP round trip, CLI_BIN at fixtures):
  - without session id → success JSON carrying a fresh UUID and the clean answer
  - with a client-provided session id → id echoed back
  - env assertion: the stub's recorded value is `0`
  - CLI failure → error with diagnostics
