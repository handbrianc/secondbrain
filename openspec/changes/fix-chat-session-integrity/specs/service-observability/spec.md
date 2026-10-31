# Service Observability (delta)

## ADDED Requirements

### Requirement: Default rotating file log

CLI commands SHALL attach a size-rotating file log under the user's
application data directory (e.g. `~/.secondbrain/logs/secondbrain.log`) by
default, without requiring environment configuration. Rotation SHALL cap
both the per-file size and the total retained log volume. An explicit
`SECONDBRAIN_LOG_FILE` MAY still override the destination; a disable switch
MAY suppress file logging entirely. Console output behavior SHALL be
unchanged by this default.

#### Scenario: Fresh environment gets a log file

- **WHEN** a command runs in an environment where `SECONDBRAIN_LOG_FILE` is
  unset and no log directory exists
- **THEN** a log file under the application data directory receives the
  command's log records
- **AND** later commands append to the same rotated series

#### Scenario: Rotation caps disk usage

- **WHEN** the active log file grows past the configured size cap
- **THEN** it rotates to numbered backups
- **AND** the number of retained backups stays within the configured limit

### Requirement: Slow-call WARNING logging

External service calls (LLM, embedding, vector store) SHALL log a WARNING
with the operation name, target (endpoint or collection), and elapsed time
when the call's elapsed time exceeds a configured slow-call threshold. The
warning SHALL be emitted regardless of log level configuration, so silent
multi-minute stalls are attributable in the default file log. Calls within
the threshold SHALL NOT emit the warning.

#### Scenario: Stalled call is attributable

- **WHEN** an LLM call in a chat turn takes minutes while the user sees no
  progress (observed: chat silent 04:32:57–04:39:44 with zero Qdrant
  requests)
- **THEN** the default file log carries a WARNING naming the operation and
  its elapsed time
- **AND** the gap is attributable without reproducing it under debug logging

#### Scenario: Fast calls stay silent

- **WHEN** all external calls in a command complete within the threshold
- **THEN** no slow-call warnings are emitted
- **AND** normal INFO/ERROR log volume is unchanged
