# MCP CLI Adapter

## ADDED Requirements

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
