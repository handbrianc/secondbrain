# MCP CLI Subprocess Timeout — Proposal

## Why

The CLI adapter core (`add-mcp-cli-adapter`) has no deadline: a wedged CLI (unreachable Qdrant, hung LLM stream)
would hang an MCP tool call forever. This proposal adds the adapter's deadline unit: enforce
`SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` (config from the scaffold) and, on expiry, terminate the CLI's **entire
process group** — the CLI spawns process pools for ingestion, so a naive child kill strands grandchildren. This is a
separate unit from execution because it is an independently rejectable policy (one could run without deadlines) with
distinct failure modes and dedicated test machinery (sleeper and child-spawner stubs).

## What Changes

- **Deadline enforcement in `CliRunner`**: every call is bounded by the configured timeout; expiry → `Err::Timeout`.
- **Process-group teardown**: spawn into a POSIX process group; on timeout, `killpg(SIGKILL)` the group and await the
  child so no orphans survive.
- **Post-timeout liveness**: a timed-out call leaves the runner fully usable.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-cli-adapter** — adds the timeout requirement.

## Dependencies

- Requires: `add-mcp-cli-adapter` (execution core; config timeout from the scaffold).

**Depended on by:** the tool proposals (strongly recommended before `add-mcp-chat-send-tool`, whose LLM-bound calls
can hang).

## Impact

**Code**: `mcp-server/src/cli.rs` (spawn in process group, timeout wrapper, killpg), new fixtures + tests.

**Dependencies**: none beyond existing (`tokio::time`, libc `killpg` via existing process-group support).

## Non-goals

- Per-call timeout overrides (config-level deadline only, v1).
- Windows process management.
