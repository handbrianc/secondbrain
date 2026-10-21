# MCP CLI Adapter — Proposal

## Why

The MCP server wraps the secondbrain Python CLI rather than reimplementing RAG logic (see
`add-mcp-server-scaffold/design.md` §1). Every tool drives the CLI as a subprocess, so a well-tested execution layer
must exist before any tool lands. This proposal delivers the adapter's core unit of work: **executing the CLI and
returning structured outcomes** — binary resolution, argv-only spawning (no shell), separated stdout/stderr capture,
and exit-code mapping. Two adjacent behaviors are separate units: the environment contract (inheritance + per-call
overrides → `add-mcp-cli-env-passthrough`) and deadline enforcement with process-group teardown
(`add-mcp-cli-timeout`).

## What Changes

- **`mcp-server/src/cli.rs`** — `CliRunner` core:
  - Resolves `SECONDBRAIN_MCP_CLI_BIN` (absolute path or `PATH`); unresolvable → error naming the variable.
  - Spawns with an **argv vector — never a shell** (no interpolation/injection surface).
  - Captures stdout and stderr separately (CLI logging goes to stderr; rich spinners auto-suppress on non-TTY).
  - Inherits the server's working directory and (at this stage) its environment.
  - Maps outcomes: `Ok { stdout, stderr }` (exit 0), `Err::Exit { code, stdout, stderr }` (non-zero).
- **Stub-CLI test fixtures** (`mcp-server/tests/fixtures/`): success, failure, and argv-echo stubs so the core is
  proven hermetically (no Python or Qdrant required).

No MCP wiring yet — tools consume this layer in the tool proposals.

## Capabilities

### New Capabilities

- **mcp-cli-adapter**: subprocess execution of the secondbrain CLI by the MCP server (env contract and timeout
  requirements are added to this capability by their proposals).

### Modified Capabilities

- *None.*

## Dependencies

- Requires: `add-mcp-server-scaffold` (config provides `CLI_BIN`).

**Depended on by:** `add-mcp-cli-env-passthrough`, `add-mcp-cli-timeout`, all tool proposals.

## Impact

**Code**: `mcp-server/src/cli.rs`, fixtures, new tests.

**Dependencies**: `tokio` (already present via the runtime proposal).

**Out of scope**: env overrides, timeout/teardown (separate proposals); MCP endpoints; CLI flag decisions (tool
proposals own those).

## Non-goals

- Changing the Python CLI.
- Windows process management (the server ships in Linux containers).
