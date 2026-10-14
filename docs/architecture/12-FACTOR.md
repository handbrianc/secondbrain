# 12-Factor Compliance

SecondBrain is evaluated against the [Twelve-Factor App](https://12factor.net) methodology as part
of the repository's periodic 12-factor scan. Every factor is either satisfied or not applicable
for a local CLI, with two **documented deviations** — both deliberate, with recorded rationale.

| Factor          | Status               | Evidence                                                |
| --------------- | -------------------- | ------------------------------------------------------- |
| VI — Processes  | Documented deviation | Local SQLite conversation/session state — see below     |
| XI — Logs       | Documented deviation | Opt-in rotating file logging — see below                |

## VI — Processes: local conversation state

12-Factor expects stateless, share-nothing processes that keep all state in backing services.
SecondBrain keeps conversation sessions in a local SQLite database (`src/secondbrain/conversation/`,
`src/secondbrain/storage/`).

**Why this is by design.** SecondBrain is a single-user, local-first desktop CLI. Its privacy
model is "documents and conversations stay on your machine" — the same reason parsing, chunking
and vector storage are local (see [Local-First Privacy](index.md#4-local-first-privacy)). The
SQLite store is per-machine user state, analogous to a browser profile, not request-scoped server
state. Scaled-out, horizontally-replicated deployment is not a target topology for this tool, so
the statelessness requirement that factor VI encodes has no counterpart to enforce.

**Consequences.** Sessions are not shared between machines, and concurrent writers are bounded by
SQLite locking. The store sits behind the `conversation`/`storage` module interfaces, so a future
server deployment can swap it for a networked backing service without touching the RAG pipeline.

## XI — Logs: stdout by default, rotating file opt-in

The default log stream is stdout, per 12-Factor: each process writes its event stream to the
process's stdout for the environment to route. SecondBrain additionally supports rotating on-disk
log files when the operator sets `SECONDBRAIN_LOG_FILE` (`RotatingFileHandler` in
`src/secondbrain/logging/__init__.py:17,181,231`, sized by `SECONDBRAIN_LOG_MAX_BYTES` and
`SECONDBRAIN_LOG_BACKUP_COUNT` — see [Logging](../getting-started/configuration.md#logging)).

**Why this is acceptable.** The file handler is strictly opt-in and never the primary channel:
with `SECONDBRAIN_LOG_FILE` unset, no file handler is created and all output stays on stdout,
preserving the 12-Factor delivery model. File logging exists for long-running ingestion agents
whose terminal is not observed, where operators need bounded on-disk retention. Rotation with
size and backup-count caps is precisely the control that keeps file logging from becoming
unbounded disk growth — the practical failure mode factor XI warns against. Every log record
carries a request ID via `contextvars` (`logging/__init__.py:46`), so events stay joinable on
either channel.
