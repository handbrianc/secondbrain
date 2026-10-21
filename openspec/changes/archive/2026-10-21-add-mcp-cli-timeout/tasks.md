# MCP CLI Subprocess Timeout — Tasks

## 1. Implementation

- [x] 1.1 Spawn into a POSIX process group (`Command::process_group(0)`) in the adapter core
- [x] 1.2 Wrap the child wait in `tokio::time::timeout` with `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS`; on expiry `killpg(SIGKILL)` the group, await the child, return `Err::Timeout`

## 2. Fixtures

- [x] 2.1 `mcp-server/tests/fixtures/stub_sleeper.sh` — sleeps 60s (for deadline tests)
- [x] 2.2 `mcp-server/tests/fixtures/stub_spawner.sh` — spawns a background child then sleeps (proves group-wide kill)

## 3. Tests proving the unit of work

- [x] 3.1 Integration `tests/cli_adapter_timeout.rs` (short timeout via env):
  - sleeper exceeds the deadline → `Err::Timeout` returned promptly (elapsed < deadline + grace)
  - spawner's background child is dead after the timeout (checked via the child's output marker file/pid probe)
  - a call after a timeout still succeeds (stub_success)
- [x] 3.2 Unit test: `Err::Timeout` maps to the error variant (no panic) and carries no partial-output confusion (documented: partial streams are discarded on timeout)
