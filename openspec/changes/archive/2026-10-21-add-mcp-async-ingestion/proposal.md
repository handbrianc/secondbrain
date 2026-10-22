# MCP Asynchronous Ingestion with Job Polling — Proposal

## Why

Ingestion runs synchronously inside the tool call: the HTTP request stays
open for the whole CLI run (bounded by the server's 900 s subprocess cap,
`add-mcp-cli-timeout`), and any client whose own request timeout is shorter
loses the connection mid-run — the call is cancelled, the in-flight response
is never delivered, and the client reads the dropped request as a crashed
server. That is exactly what happened on this deployment: a heavy PDF ingest
was cancelled by the client ~23 s before the server would have delivered the
real diagnostic. Long ingests are the norm for large PDFs (parse plus
embedding takes minutes), so waiting inside the request is the wrong
contract for them; the result of a long run should be collectable afterwards.

## What Changes

- **`ingest_documents` and `upload_document` gain `async_mode`** (default
  false — the synchronous contract is unchanged and every existing test
  holds). With `async_mode: true`, all fast validation still happens inside
  the call — path resolution and confinement, argv build, and for uploads
  the base64 decode, size budget, filename checks, existing-target check,
  and staging write — so invalid calls fail immediately with the same
  diagnostics as today and create no job. Only the CLI run (and the upload's
  delete-after-ingest disposition) moves into a background task. The call
  returns immediately with a job identifier and the polling instruction.
- **New `job_status` tool**: reports one job's state (`running`, 
  `completed`, `failed`) plus kind, elapsed time, and — once terminal — the
  exact result text the synchronous call would have produced (including the
  staged-file disposition sentence for uploads). Called without arguments it
  lists all jobs known to this server process. Job-status results are always
  success results: the job's own failure is conveyed in the status text, so
  "the poll worked, the job failed" stays distinguishable.
- **A process-lifetime job registry**: ids are sequential (`job-1`,
  `job-2`, …), state is kept in server memory, finished jobs are retained
  up to a bounded count (oldest evicted). A detached job runs to completion
  regardless of the client connection, still bounded by the same subprocess
  timeout — a job that outlives the cap fails with the adapter's timeout
  diagnostic, visibly in the job status.
- **Documentation and tests**: README tool reference + an asynchronous
  workflow section, MCP guide rows, e2e coverage for the start/poll
  lifecycle, upload delete-parity in async mode, and the no-job-on-invalid
  rule.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the asynchronous-ingestion mode, the `job_status`
  polling tool, the upload delete-parity in async mode, and the registry's
  lifecycle semantics.

## Dependencies

- Requires: `add-mcp-ingest-tool` and `add-mcp-upload-tool` (the tools
  extended), `add-mcp-cli-adapter` and `add-mcp-cli-timeout` (the runner and
  its deadline reused unchanged), `add-mcp-upload-tool`'s delete-after-ingest
  contract (parity requirement below).

**Depended on by:** none yet.

## Impact

**Code**: `mcp-server/src/tools/jobs.rs` (new), `mcp-server/src/tools/ingest.rs`,
`mcp-server/src/tools/upload.rs`, `mcp-server/src/tools/mod.rs`,
`mcp-server/src/server.rs`, `mcp-server/src/main.rs`.

**Tests**: new `mcp-server/tests/tools_jobs.rs`; harness updates for the new
server field.

**Docs**: `mcp-server/README.md`, `docs/developer-guide/mcp.md`.

## Non-goals

- Job cancellation: a started job runs to completion (or to its subprocess
  deadline). Cancellation semantics are a separate change if needed.
- Persistence across restarts: the registry is in server memory and dies
  with the process — documented behavior, not a defect. The staged file of
  an interrupted async upload is retained (failed-ingest contract), so
  nothing is lost beyond the job record.
- Concurrency limiting: multiple jobs may run at once, each bounded by the
  worker cap (`revise-compose-mcp-worker-cap`); callers ingesting several
  heavy files should still do so sequentially, since parallel heavy parses
  contend for the same host memory.
- Progress reporting: the CLI exposes no progress protocol; polling returns
  running/completed/failed only.
