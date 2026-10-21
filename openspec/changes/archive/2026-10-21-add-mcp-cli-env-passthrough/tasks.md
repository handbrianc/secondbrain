# MCP CLI Environment Contract — Tasks

## 1. Implementation

- [x] 1.1 Extend `CliRunner::run` with an `overrides: &[(String, String)]` parameter applied via `Command::envs` over the inherited environment (per-call, no global mutation)

## 2. Fixture

- [x] 2.1 `mcp-server/tests/fixtures/stub_env.sh` — prints the value of a requested variable name (plus a sentinel distinguishing unset)

## 3. Tests proving the unit of work

- [x] 3.1 Integration `tests/cli_adapter_env.rs` (fixtures, `SECONDBRAIN_MCP_CLI_BIN` at the env stub):
  - inherited server env visible to the child (a var set on the server process)
  - per-call override visible to the child
  - override cleared on the next call (child sees inherited value again)
- [x] 3.2 Unit test: override map with an already-set variable wins over the inherited value
