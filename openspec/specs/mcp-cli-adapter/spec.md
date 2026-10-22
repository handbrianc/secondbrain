# mcp-cli-adapter Specification

## Purpose
The mcp-cli-adapter capability covers how the secondbrain CLI exposes MCP-facing operations as subcommands: the environment passthrough and override rules that let the MCP server's subprocess calls (and direct CLI users) target a specific storage backend, collection, and embedding configuration without image rebuilds or code changes. add-mcp-cli-env-passthrough. Update Purpose after archive.

## Requirements

### Requirement: Environment passthrough and overrides

The adapter SHALL pass the server's full environment to the CLI process on every call, and SHALL apply per-call
environment overrides on top of it without mutating global state or leaking into subsequent calls.

#### Scenario: Inherited environment

- **WHEN** the server runs with `SECONDBRAIN_QDRANT_URL=https://qdrant.example:6333` in its environment
- **THEN** a CLI subprocess observes that variable (verified with an env-dumping stub)

#### Scenario: Per-call override

- **WHEN** a call specifies the override `SECONDBRAIN_SHOW_THINKING=0`
- **THEN** the child observes the overridden value

#### Scenario: No override leakage

- **WHEN** an override is applied on one call and a further call is made without it
- **THEN** the further call's child observes the inherited value, not the override

### Requirement: Timeout with process-group teardown

The adapter SHALL enforce `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` per call; on expiry it SHALL terminate the
CLI's entire process group (including any children it spawned) and return a timeout failure.

#### Scenario: Hanging CLI is killed

- **WHEN** the CLI (stub: a script that sleeps far longer than the configured timeout) exceeds the timeout
- **THEN** the call returns a timeout failure promptly after the deadline
- **AND** the stub process (and its children) are no longer running

#### Scenario: Timeout leaves subsequent calls working

- **WHEN** a call times out and a further call is made
- **THEN** the further call executes normally

### Requirement: Subprocess execution of the CLI

The MCP server SHALL execute the secondbrain CLI as a subprocess using an argv vector (no shell interpolation),
capturing stdout and stderr separately, and inheriting the server's working directory.

#### Scenario: Successful invocation

- **WHEN** the adapter runs the configured CLI binary with arguments that exit 0
- **THEN** the outcome is success carrying the full stdout and stderr separately

#### Scenario: Non-zero exit is a structured failure

- **WHEN** the CLI exits with a non-zero code
- **THEN** the outcome is a failure carrying the exit code plus both captured streams (not a panic)

#### Scenario: No shell interpolation

- **WHEN** an argument contains shell metacharacters (e.g. `$(...)`, backticks, `;`)
- **THEN** the bytes are passed verbatim as one argv element to the child process (verified with a stub that echoes its arguments)

### Requirement: CLI binary resolution

The adapter SHALL resolve `SECONDBRAIN_MCP_CLI_BIN` as an absolute path, or from `PATH`; when unresolvable it SHALL
report an error naming the variable before any tool invocation.

#### Scenario: Missing binary is reported

- **WHEN** `SECONDBRAIN_MCP_CLI_BIN` points to a nonexistent path
- **THEN** the outcome is a failure whose message names `SECONDBRAIN_MCP_CLI_BIN` (and no spawn is attempted)
