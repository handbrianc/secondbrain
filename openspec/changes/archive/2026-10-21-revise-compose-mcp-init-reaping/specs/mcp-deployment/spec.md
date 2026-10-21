# MCP Deployment

## ADDED Requirements

### Requirement: Orphaned subprocess reaping under the server containers

The compose `mcp-server` services SHALL run under docker-init (`init: true`),
so the entrypoint-exec'd server does not hold the container's PID 1 seat:
orphaned processes left behind by each CLI-driven tool call (the Python CLI's
forkserver and resource tracker) reparent to the namespace init and are reaped
there, instead of accumulating as defunct children of the server — which, as
PID 1, adopts them and (as a tokio application) never waits children it did not
spawn itself. The entrypoint's root→runtime-user handover SHALL be unaffected:
docker-init runs the entrypoint as the container's original user, and the
entrypoint keeps re-exec'ing the command as the non-root runtime user. The test stack SHALL mirror the
production setting.

#### Scenario: An ingest-family call leaves no defunct processes

- **WHEN** a client drives a tool call whose CLI run spawns the multiprocessing
  helpers (e.g., `ingest_documents` or `upload_document`)
- **THEN** the helpers outlive the CLI by an instant, are reparented to
  docker-init, and are reaped — no defunct processes remain under the server or
  the init afterward

#### Scenario: Pre-existing zombies clear on recreate

- **WHEN** the `mcp-server` container is recreated with `init: true`
- **THEN** the defunct children accumulated under the previous server process
  are gone (the old namespace is torn down with it)

#### Scenario: The privilege handover is unchanged

- **WHEN** the stack starts the `mcp-server`
- **THEN** docker-init runs the entrypoint as the container's original user,
  the entrypoint performs its root-only staging-directory handover, and the
  server process runs as the non-root runtime user

#### Scenario: Test stack parity

- **WHEN** the test stack runs its `mcp-server`
- **THEN** it also runs under docker-init with the same reaping
