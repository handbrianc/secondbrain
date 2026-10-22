# MCP Tools

## ADDED Requirements

### Requirement: Asynchronous ingestion mode

The `ingest_documents` and `upload_document` tools SHALL accept an
`async_mode` parameter (default false). When false or absent, the tools
SHALL behave exactly as before (synchronous). When true, the tools SHALL
complete all fast validation synchronously — path resolution and workspace
confinement and argv build for both tools; base64 decode, size budget,
filename checks, existing-target check, and staging write for
`upload_document` — so an invalid call fails immediately with the same
diagnostics as the synchronous call and creates no job. Only the CLI run
(and, for `upload_document`, the delete-after-ingest disposition) SHALL run
as a detached job, and the call SHALL return immediately with the job's
identifier and the instruction to poll `job_status`.

#### Scenario: An async start returns a job id, not the ingest result

- **WHEN** a client calls an ingest-family tool with `async_mode: true` and
  valid parameters
- **THEN** the call returns promptly with a job identifier and the polling
  instruction, and the response does not contain the CLI's ingest summary

#### Scenario: An invalid async call fails immediately and creates no job

- **WHEN** a client calls an ingest-family tool with `async_mode: true` and
  parameters that fail validation (a path escaping the workspace, an over-
  budget or invalid upload submission)
- **THEN** the call returns the same immediate error the synchronous call
  would produce, and no job is created

#### Scenario: A detached job outlives its client's connection

- **WHEN** the client's connection closes after starting an async job
- **THEN** the job's CLI run continues and reaches a terminal state (or the
  subprocess deadline), and its outcome is retrievable via `job_status`

### Requirement: Job status polling

A `job_status` tool SHALL report the state of asynchronous jobs: with a
`job_id` argument it SHALL return that job's state (`running`, `completed`,
or `failed`), its kind (`ingest` or `upload`), its elapsed running time,
and — once terminal — the exact result text the synchronous call would have
produced, including the staged-file disposition sentence for uploads.
Without arguments it SHALL list every job known to this server process.
Job-status results SHALL always be success results: a failed job is conveyed
by its status text, never by a failed poll. An unknown job id SHALL produce
an error result naming the id and explaining that jobs are kept in server
memory.

#### Scenario: Polling a running job

- **WHEN** a client polls `job_status` with the id of a job whose CLI run is
  still executing
- **THEN** the result reports `running` with the job's kind, id, and elapsed
  time

#### Scenario: Polling a completed job returns the sync-equivalent text

- **WHEN** a client polls `job_status` with the id of a finished job
- **THEN** the result reports the terminal state and carries the same text
  (ingest summary, CLI failure diagnostics, or upload disposition sentence)
  the synchronous call would have returned

#### Scenario: Polling an unknown id

- **WHEN** a client polls `job_status` with an id the server does not know
- **THEN** the result is an error naming the id and noting that jobs are
  kept in server memory (cleared on restart), not a hang or a crash

### Requirement: Upload delete-parity in async mode

In `async_mode`, `upload_document` SHALL apply the same staged-file
disposition as the synchronous contract: the staged file is deleted after a
successful ingest, kept on a failed ingest, and a failed deletion is
reported inside an otherwise-successful result without failing the job. The
disposition SHALL be visible in the job's recorded status text.

#### Scenario: An async upload success deletes the staged file

- **WHEN** an async upload's ingest succeeds
- **THEN** the staged file is removed and the job's status text carries the
  deletion sentence

#### Scenario: An async upload failure keeps the staged file

- **WHEN** an async upload's ingest fails
- **THEN** the staged file remains on disk and the job records the CLI's
  failure diagnostics

#### Scenario: An async upload delete-failure is reported without failing the job

- **WHEN** an async upload's ingest succeeds but the staged-file deletion
  fails
- **THEN** the job completes with the deletion-failure sentence in its
  status text, exactly as the synchronous contract reports it

### Requirement: Job registry lifecycle

The server SHALL track asynchronous jobs in a process-lifetime, in-memory
registry: job identifiers SHALL be sequential (`job-1`, `job-2`, …) and
unique per server process; finished jobs SHALL be retained up to a bounded
count with the oldest evicted. When the server process restarts, the
registry SHALL start empty — previously issued job ids SHALL be reported as
unknown, and a CLI run detached at restart time SHALL have been terminated
with the process (its staged upload file, if any, retained per the
failed-ingest contract).

#### Scenario: Finished jobs are retained up to a bound

- **WHEN** more than the bounded number of jobs have finished
- **THEN** the oldest finished jobs are evicted from the registry while
  running jobs are never evicted

#### Scenario: A restart clears the registry

- **WHEN** the server process restarts after jobs were started
- **THEN** `job_status` reports the old ids as unknown and lists no jobs
