# MCP Server Ingest Worker Cap (2) — Proposal

## Why

On the production host (6 GiB RAM), ingesting a heavy PDF through the MCP
server OOM-killed the CLI's multiprocessing workers: the server container's
cgroup `memory.events` recorded 8 `oom_kill` events, the CLI failed with
`BrokenProcessPool: worker process crashed mid-batch`, and — because the
client's own request timeout (~10 min) fires before the server's 900 s
subprocess cap — the client saw a silent 10-minute hang ending in a cancelled
call instead of the CLI's diagnostic. The CLI's default of four parallel
docling workers (`SECONDBRAIN_MAX_WORKERS=4` in `.env.docker`) multiplies peak
parse memory; the shipped stack configuration was unsuitable for the host it
runs on. The knob already exists (`config/processing.py` `max_workers`,
env `SECONDBRAIN_MAX_WORKERS`) — the stack just needs the bounded value.

## What Changes

- **`.env.docker`**: `SECONDBRAIN_MAX_WORKERS` 4 → 2 with the rationale in a
  comment. The MCP server pushes `--cores` to the CLI only when the caller
  sets it (verified: `mcp-server/src/tools/ingest.rs` adds the flag only for
  `Some(cores)`), so this cap governs every server-driven ingest by default;
  an explicit per-call `cores` / `--cores` still wins per the documented
  precedence (explicit `--cores` > configured `max_workers` > auto-detect).
- **Documentation**: the docker guide's production-stack section gains the
  worker-cap rationale, and its troubleshooting gains the
  OOM/`BrokenProcessPool` symptom/fix pair (including the cgroup
  `memory.events` evidence path and the client-timeout interaction). Two
  stale references to the removed `cli` service in the same file are corrected
  in passing.

No compose-YAML, Python, or Rust changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the bounded-ingest-worker requirement (the
  production stack caps CLI worker processes at 2 via the env file).

## Dependencies

- Requires: `revise-compose-production-stack` (the stack whose env file is
  revised).

**Depended on by:** none yet.

## Impact

**Code**: `.env.docker`.

**Docs**: `docs/developer-guide/docker.md`.

## Non-goals

- A compose `cpus: 2` quota: a CPU limit does not reduce peak parse memory
  (the OOM mechanism) — it only slows the workers while they balloon.
- Test-stack parity: `docker-compose.test.yml` configures its `mcp-server`
  inline (no `env_file`) and drives ingest only through stubs, so the cap has
  no test-stack analogue.
- Lowering `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE`: the worker cap was the
  observed OOM lever; batch-size tuning stays available as a documented
  follow-up knob if a single worker still exhausts memory on larger files.
- The per-file spike discovered during validation: `UserManual_x175.pdf`
  OOM-kills even at the 2-worker cap because the structure probe routes it
  (a text-layer PDF with ToC-like leading pages) into the full docling
  pipeline — a single ~5.8 G parse spike. With
  `SECONDBRAIN_PDF_STRUCTURE_PROBE_ENABLED=false` the same file ingests in
  48 s. Flipping that default (structural labels vs. heavy-parse
  survivability on a 6 GiB host) is deliberately left to a separate change.
