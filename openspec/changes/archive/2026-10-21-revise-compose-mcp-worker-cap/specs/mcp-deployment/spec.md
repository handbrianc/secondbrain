# MCP Deployment

## ADDED Requirements

### Requirement: Bounded ingest worker concurrency in the production stack

The production compose stack SHALL run CLI-driven ingestion with a bounded
worker pool — `SECONDBRAIN_MAX_WORKERS=2` in `.env.docker` — sized for the
memory the host can spare, so the parallel parse workers of a heavy document
cannot exhaust host memory and get OOM-killed (which the CLI surfaces as
`BrokenProcessPool`). The server SHALL keep passing `--cores` to the CLI only
when the caller sets it, so the env-file cap governs default ingest calls
while an explicit per-call `cores` still wins (precedence: explicit
`--cores` > configured `max_workers` > auto-detect).

#### Scenario: A default ingest stays inside the worker cap

- **WHEN** a client calls an ingest-family tool without an explicit `cores`
- **THEN** the CLI's process pool runs at most 2 worker processes

#### Scenario: Explicit per-call cores still wins

- **WHEN** a client passes an explicit `cores` to the tool
- **THEN** the CLI receives that explicit `--cores` value instead of the
  env-file cap

#### Scenario: A host-OOM kill is diagnosable, not silent

- **WHEN** a worker process is OOM-killed despite the cap
- **THEN** the CLI reports `BrokenProcessPool` naming the in-flight file, the
  tool call fails with that diagnostic (no partial points stored, the staged
  file retained), and the container cgroup's `memory.events` shows the
  `oom_kill` count
