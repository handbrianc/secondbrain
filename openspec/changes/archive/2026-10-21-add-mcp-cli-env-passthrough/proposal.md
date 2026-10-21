# MCP CLI Environment Contract — Proposal

## Why

The CLI adapter core (`add-mcp-cli-adapter`) executes the CLI but pins no environment contract. In the container,
everything that makes the tools work — Qdrant endpoint, embedding/vector-model API, LLM API, SQLite path — reaches
the Python CLI through inherited environment variables (the Python config layer reads `SECONDBRAIN_*` from the
process environment). This proposal makes that contract explicit and testable: subprocesses inherit the server's
full environment, and callers may apply per-call overrides (the chat tool will rely on this to set
`SECONDBRAIN_SHOW_THINKING=0`). This is a separate unit from execution because it is an independently rejectable
contract decision (an operator could mandate a fixed environment), and because its failure modes (leakage between
calls, silent non-inheritance) are distinct.

## What Changes

- **Environment contract in `CliRunner`**:
  - Guaranteed inheritance of the server's full environment on every call.
  - Per-call override map applied on top of the inherited environment — never mutating process-global state, never
    leaking into subsequent calls.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-cli-adapter** — adds the environment passthrough requirement.

## Dependencies

- Requires: `add-mcp-cli-adapter` (the execution core).

**Depended on by:** all tool proposals (chat especially — `SECONDBRAIN_SHOW_THINKING=0`).

## Impact

**Code**: `mcp-server/src/cli.rs` (override parameter on `run`), new fixture + tests.

**Dependencies**: none beyond existing.

## Non-goals

- Env allow-listing/deny-listing (full inheritance is the v1 contract; the container is the trust boundary).
- Changing the Python CLI's `.env`-from-CWD loading behavior.
