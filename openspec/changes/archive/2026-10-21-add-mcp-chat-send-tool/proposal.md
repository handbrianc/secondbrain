# MCP Chat Send Tool — Proposal

## Why

Conversational RAG is secondbrain's third capability group (`secondbrain chat`): retrieval-augmented answers with
persistent sessions in SQLite. The CLI already supports machine-friendly single-turn invocation —
`secondbrain chat "query" --session <id>` runs non-interactively, auto-creating an explicitly named session silently
(the noisy `Created new session:` line only appears when `--session` is omitted), and
`SECONDBRAIN_SHOW_THINKING=0` reduces stdout to one strippable reasoning-indicator line plus the streamed answer.
This proposal exposes the core unit: sending one query into a session. The two read-only introspection tools
(`chat_list_sessions`, `chat_get_history`) are separate units with their own proposals.

Two verified CLI constraints shape the scope (see `add-mcp-server-scaffold/design.md` §5):
`chat --delete-session` hardcodes an interactive y/N prompt (not scriptable → deletion is a non-goal), and sources
print after the answer only with `--show-sources` with no stable delimiter (→ sources are a non-goal in v1).

## What Changes

- **`chat_send` MCP tool**: input `query` (required), `session_id` (optional — server generates a UUID v4 when
  absent and returns it), `top_k` (default 20), `temperature` (default 0.1), `model` (optional).
  - Execution: `chat <query> --session <id> [--top-k N] [--temperature T] [--model M]` through the CLI adapter, with
    the per-call env override `SECONDBRAIN_SHOW_THINKING=0` (the env contract proposal provides overrides).
  - Output: JSON text block `{"session_id": ..., "answer": ...}` where `answer` is stdout with every
    `▸ Thinking:`-prefixed line stripped.

No Python changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the chat send tool requirement.

## Dependencies

- Requires: `add-mcp-streamable-http-transport`, `add-mcp-cli-adapter`, `add-mcp-cli-env-passthrough`
  (overrides); `add-mcp-cli-timeout` strongly recommended before production use (LLM-bound calls can hang).

**Depended on by:** `add-mcp-e2e-smoke`, `add-mcp-readme-feature-docs`.

## Impact

**Code**: `mcp-server/src/tools/chat.rs` (send), new tests.

**Dependencies**: `uuid` crate (v4 session ids).

## Non-goals

- Session deletion (`chat_delete_session`) — the CLI's interactive y/N prompt is not scriptable; follow-up candidate
  is a `--yes` flag on the CLI, then a wrapping tool.
- Source citations in tool output (needs a stable `--show-sources` format; same follow-up path).
- Multi-turn REPL streaming over SSE (each tool call is one turn; clients maintain the session id).
- Session listing/history (separate proposals).
