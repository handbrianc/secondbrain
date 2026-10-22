# MCP CLI Adapter — Tasks

## 1. Adapter core implementation

- [x] 1.1 Implement `mcp-server/src/cli.rs`: `CliOutcome` enum (`Success { stdout, stderr }`, `Exit { code, stdout, stderr }`), `CliError` with `thiserror`, `CliRunner::run(args: &[OsStr])`
- [x] 1.2 Spawn with `tokio::process::Command`, argv vector only, `Stdio::piped()` for stdout/stderr; inherit the server's working directory and environment
- [x] 1.3 Resolve `SECONDBRAIN_MCP_CLI_BIN` (absolute path or `PATH` lookup) once at startup; error names the variable

## 2. Stub fixtures

- [x] 2.1 `mcp-server/tests/fixtures/stub_success.sh` — prints known stdout, writes to stderr, exits 0
- [x] 2.2 `mcp-server/tests/fixtures/stub_failure.sh` — prints diagnostics to stdout/stderr, exits 3
- [x] 2.3 `mcp-server/tests/fixtures/stub_argv.sh` — prints argv one-per-line (proves no-shell, verbatim passing)

## 3. Tests proving the unit of work

- [x] 3.1 Unit tests (inline in `cli.rs`): outcome mapping for exit 0 / exit 3
- [x] 3.2 Integration `tests/cli_adapter_core.rs` (against fixtures, `SECONDBRAIN_MCP_CLI_BIN` pointed at each stub):
  - success captures both streams; exit 3 carries code + streams
  - arg metacharacters pass through verbatim as one argv element (stub_argv)
  - unresolvable `SECONDBRAIN_MCP_CLI_BIN` → failure naming the variable, no spawn attempted
