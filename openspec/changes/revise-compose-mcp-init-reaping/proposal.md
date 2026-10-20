# MCP Server PID 1 Reaping (docker-init) — Proposal

## Why

The image entrypoint re-execs into the server, so `secondbrain-mcp` holds the
container's PID 1 seat (verified live: `docker inspect`'s `.State.Pid` is the
server process). POSIX reparents orphaned processes to the PID-namespace init,
and every CLI-driving tool call leaves helper processes that outlive the CLI by
an instant: the Python 3.14 CLI's `forkserver` and resource tracker (the
`multiprocessing` default start method on Linux) outlive their parent and
reparent to the server. The server (tokio) reaps only children it spawned
itself — its `Child` handles — and never waits adopted orphans, so each
ingest-family call leaves two defunct `python3.14` processes that persist until
the container restarts. Observed live on the production stack: 10 zombies from
5 calls over ~22.5 hours, growing by 2 per call without bound for a long-lived
server. Wrapping the service with docker-init (`init: true`) gives the PID 1
seat to tini, whose purpose is exactly this reaping — with no image or
application-code changes.

## What Changes

- **`docker-compose.yml` (`mcp-server`)**: `init: true` with the rationale in a
  comment. The entrypoint chain is unaffected — docker-init runs the
  entrypoint (and its root-only staging handover) as before, and the entrypoint
  still re-execs the command as the non-root runtime user.
- **`docker-compose.test.yml` (`mcp-server`)**: the same, for stack parity.
- **Documentation**: the docker guide's stack sections and troubleshooting gain
  the reaping rationale and the symptom/fix pair.

No Python or Rust changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the orphaned-subprocess-reaping requirement
  (docker-init holds PID 1 on both `mcp-server` services; one-shot `cli`
  exempt).

## Dependencies

- Requires: `revise-compose-production-stack` and `revise-compose-test-stack`
  (the services being revised), `revise-compose-writable-uploads` (the
  entrypoint handover whose root→runtime-user chain must be unaffected).

**Depended on by:** none yet.

## Impact

**Code**: `docker-compose.yml`, `docker-compose.test.yml`,
`docs/developer-guide/docker.md`.

## Non-goals

- An in-process reaper thread in the server: a bare `waitpid(-1)` loop races
  tokio's `Child::wait()` for exit statuses and needs per-pid bookkeeping to be
  safe — complexity that docker-init already covers.
- Suppressing the CLI's forkserver/resource tracker from Python: private
  `multiprocessing` APIs, fragile, and it would not cover the timeout-kill
  path (the killed group orphans the same helpers).
