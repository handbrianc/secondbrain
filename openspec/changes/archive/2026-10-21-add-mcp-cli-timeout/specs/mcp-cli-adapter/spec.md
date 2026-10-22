# MCP CLI Adapter

## ADDED Requirements

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
