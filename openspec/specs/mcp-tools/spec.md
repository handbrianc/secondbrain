# mcp-tools Specification

## Purpose
The mcp-tools capability covers the MCP tool surface the server exposes: tool names, argument schemas, and result envelopes for ingest_documents, search, chat_send, document listing/deletion, and file upload, including their validation and error behavior. add-mcp-upload-tool. Update Purpose after archive.

## Requirements

### Requirement: Upload tool

The MCP server SHALL expose an `upload_document` tool that stores a submitted document inside the workspace and
ingests it by driving the same confined CLI ingest invocation the `ingest_documents` tool uses. Its input schema
SHALL declare `filename` (string, required), `content_base64` (string, required), `skip_existing` (boolean,
optional), `chunk_size` (integer, optional), `chunk_overlap` (integer, optional), `batch_size` (integer, optional),
and `cores` (integer, optional), and the tool description SHALL state that the document is stored in the workspace
and ingested.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `upload_document`
- **AND** its input schema declares `filename` and `content_base64` as required strings plus the optional ingest
  parameters

#### Scenario: Successful upload-and-ingest

- **WHEN** the tool is called with a valid filename and base64 content, the file is stored, and the CLI ingest
  exits 0
- **THEN** the tool result is success carrying text with the stored path relative to the workspace root and the
  CLI's ingest summary
- **AND** the staged file is deleted from the upload directory

#### Scenario: Ingest parameters map to the CLI

- **WHEN** the tool is called with `skip_existing: false` and `chunk_size: 1024`
- **THEN** the CLI is invoked with `--no-skip-existing` and `--chunk-size 1024` (verified against the shared argv
  tests used by `ingest_documents`)

### Requirement: Upload content validation

The server SHALL validate submitted content before storing anything: `content_base64` MUST decode as base64, and
the decoded size MUST NOT exceed `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (default 10485760 bytes = 10 MB — a
conservative floor below the CLI's 100 MiB per-file processing cap; raise the variable to admit larger files).
Invalid base64 or oversize content SHALL produce a tool error and nothing SHALL be stored.

#### Scenario: Oversize content is rejected

- **WHEN** the decoded content exceeds `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`
- **THEN** the tool result is an error and nothing is stored

#### Scenario: Invalid base64 is rejected

- **WHEN** `content_base64` is not valid base64
- **THEN** the tool result is an error and nothing is stored

#### Scenario: Default limit applies when unset

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` is unset or empty
- **THEN** the effective decoded-size limit is 10485760 bytes

#### Scenario: Configured limit overrides the default

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` is set to a positive value (e.g. 52428800)
- **THEN** the effective decoded-size limit is that value

### Requirement: Upload storage

The server SHALL store uploads under `SECONDBRAIN_MCP_UPLOAD_DIR`, defaulting to `uploads` inside
`SECONDBRAIN_MCP_WORKSPACE_ROOT`. The configured directory SHALL be validated at startup to resolve inside the
workspace root (fail-fast config error naming the variable otherwise, including via symlink) and SHALL be created on
demand when absent. The stored filename SHALL be the provided `filename` reduced to its bare name (directory
components stripped); a filename that is empty or reduces to `.` or `..` SHALL be rejected. When the derived path
already exists, the server SHALL reject the call with a tool error naming the existing path and SHALL NOT overwrite
the existing file.

#### Scenario: Default location

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_DIR` is unset
- **THEN** uploads are stored in `<workspace root>/uploads`

#### Scenario: Upload dir outside the workspace root fails startup

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_DIR` resolves (lexically or through symlinks) outside
  `SECONDBRAIN_MCP_WORKSPACE_ROOT`
- **THEN** the server fails to start with a config error naming `SECONDBRAIN_MCP_UPLOAD_DIR`

#### Scenario: Directory components are stripped

- **WHEN** the tool is called with `filename: "nested/report.pdf"`
- **THEN** the file is stored as `report.pdf` under the upload directory

#### Scenario: Unusable filename is rejected

- **WHEN** `filename` is empty or reduces to `.` or `..`
- **THEN** the tool result is an error and nothing is stored

#### Scenario: Collision is rejected without overwrite

- **WHEN** the upload dir already contains `report.pdf` and another upload derives the same name
- **THEN** the tool result is an error naming the existing path and the existing file is unchanged

### Requirement: Ingestion after upload

After storing the file, the server SHALL ingest it through the shared ingest invocation of `ingest_documents`
(resolve → confine → argv → CLI adapter), mapping `skip_existing` (default true), `chunk_size`, `chunk_overlap`,
`batch_size`, and `cores` to the CLI flags. The server SHALL NOT introduce a new ingestion pipeline. When the CLI
exits 0, the server SHALL delete the stored file — the upload directory is transient staging and the ingested
content lives in the knowledge base — while keeping the stored path in the result; a deletion that itself fails
SHALL be reported inside the otherwise-successful result and SHALL NOT fail the call. When the CLI
exits non-zero after the file was stored (e.g. unsupported extension, Qdrant unreachable), the tool result SHALL be
an error carrying the stored path and the CLI's captured output, and the stored file SHALL remain in place for
later re-ingest via `ingest_documents`.

#### Scenario: Ingest failure after successful storage

- **WHEN** the file is stored but the CLI ingest exits non-zero
- **THEN** the tool result is an error carrying the stored path and the CLI's captured output for diagnosis
- **AND** the stored file remains in place

#### Scenario: Staged file deleted after a successful ingest

- **WHEN** the CLI ingest exits 0 after the file was stored
- **THEN** the stored file is deleted from the upload directory
- **AND** the tool result still carries the stored path as the source path recorded in the knowledge base

#### Scenario: A failed deletion is reported without failing the call

- **WHEN** the CLI ingest exits 0 but deleting the stored file fails
- **THEN** the tool result remains a success carrying the ingest summary
- **AND** the result reports the deletion failure and that the file remains in place

#### Scenario: Ingestion reuses confinement

- **WHEN** the stored file's path is passed to the ingest invocation
- **THEN** it passes the same workspace-root confinement check as any `ingest_documents` path before the CLI starts

### Requirement: Workspace path confinement

The ingest tool SHALL only ingest paths inside `SECONDBRAIN_MCP_WORKSPACE_ROOT`: the resolved target and the root
are canonicalized, and any target that escapes the root — including via `..` traversal, absolute paths outside the
root, or symlinks pointing outside — SHALL be rejected as a tool error before the CLI is invoked. Valid paths inside
the root continue to work as before.

#### Scenario: Valid paths still ingest

- **WHEN** the tool is called with a relative or absolute path that canonicalizes inside the workspace root
- **THEN** ingestion proceeds exactly as in the base ingest tool behavior

#### Scenario: Traversal escape is rejected

- **WHEN** the tool is called with `path: "../etc/passwd"` (resolving outside the workspace root)
- **THEN** the tool result is an error before any CLI subprocess starts
- **AND** the error describes the confinement rule and names `SECONDBRAIN_MCP_WORKSPACE_ROOT`

#### Scenario: Absolute escape is rejected

- **WHEN** the tool is called with an absolute path outside the workspace root
- **THEN** the tool result is an error before any CLI subprocess starts

#### Scenario: Symlink escape is rejected

- **WHEN** the workspace contains a symlink pointing outside the root and the tool is called with that symlink's path
- **THEN** the tool result is an error (canonicalization resolves the symlink to a path outside the root)

### Requirement: Ingest tool

The MCP server SHALL expose an `ingest_documents` tool that ingests a file or directory by driving the secondbrain
CLI (`ingest <path>` with mapped optional flags) through the CLI adapter.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `ingest_documents`
- **AND** its input schema declares `path` (string, required), `recursive` (boolean, optional), `skip_existing`
  (boolean, optional), `chunk_size` (integer, optional), `chunk_overlap` (integer, optional), `batch_size` (integer,
  optional), `cores` (integer, optional)

#### Scenario: Successful ingest returns the CLI summary

- **WHEN** the tool is called with a path to an ingestable file and the CLI exits 0
- **THEN** the tool result is success carrying the CLI's stdout (its human-readable summary) as text content

#### Scenario: Relative paths resolve against the workspace root

- **WHEN** the tool is called with `path: "docs/report.pdf"` (existing file relative to `SECONDBRAIN_MCP_WORKSPACE_ROOT`)
- **THEN** the CLI is invoked with the resolved absolute path under the workspace root

#### Scenario: Absolute paths are passed through

- **WHEN** the tool is called with an absolute path
- **THEN** the CLI is invoked with that path as provided (validation is the confinement proposal's unit)

#### Scenario: Flags map to the CLI

- **WHEN** the tool is called with `recursive: true`, `skip_existing: false`, `chunk_size: 1024`,
  `chunk_overlap: 100`, `batch_size: 10`, `cores: 2`
- **THEN** the CLI is invoked with `-r`, `--no-skip-existing`, `--chunk-size 1024`, `--chunk-overlap 100`,
  `-b 10`, `-c 2` (verified against the argv-building unit tests)

#### Scenario: Missing path surfaces as a tool error

- **WHEN** the tool is called with a path that does not exist
- **THEN** the tool result is an error carrying the CLI's captured output (the CLI exits non-zero on missing paths)

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero for any reason (e.g. unsupported file, Qdrant unreachable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis

### Requirement: Search tool

The MCP server SHALL expose a `search` tool that performs semantic search by driving the secondbrain CLI
(`search <query> --format json` with mapped optional flags) through the CLI adapter, and SHALL return the results as
a JSON text block in the tool result.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `search`
- **AND** its input schema declares `query` (string, required), `top_k` (integer, optional), `source` (string,
  optional), `file_type` (string, optional), `min_score` (number, optional)

#### Scenario: Successful search returns filtered results

- **WHEN** the tool is called with a query and the CLI (stub or real) returns a JSON array of result objects
- **THEN** the tool result content is a JSON array containing exactly the returned results whose `score` is greater
  than or equal to the effective `min_score` (default 0.46)
- **AND** the results preserve the CLI's fields (e.g. `source_file`, `chunk_text`, `score`, `chunk_id`, `page_number`)

#### Scenario: Server-side threshold applied

- **WHEN** the tool is called with `min_score: 0.9` and the CLI returns results scored 0.95 and 0.5
- **THEN** only the 0.95 result is returned (the CLI JSON output is not threshold-filtered; the server applies it)

#### Scenario: Empty result set is success

- **WHEN** the search yields no results (CLI exits 0, JSON array is empty)
- **THEN** the tool result is success with an empty JSON array

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero (e.g. Qdrant unreachable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis (truncated to a bounded size)

#### Scenario: Unparseable output maps to a tool error

- **WHEN** the CLI exits 0 but stdout is not valid JSON
- **THEN** the tool result is an error indicating malformed CLI output (not a server panic)

### Requirement: Safe argument passing for search

The search tool SHALL pass user input to the CLI as argv elements only, never through a shell, and SHALL prevent a
query from being parsed as CLI flags.

#### Scenario: Hostile query is inert

- **WHEN** the tool is called with a query containing `--top-k 1 && rm -rf /` or other metacharacters/flag-like text
- **THEN** the query reaches the CLI as a single literal positional argument (after a `--` separator) and is searched as-is

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

### Requirement: Chat history tool

The MCP server SHALL expose a `chat_get_history` tool that returns a session's conversation history
(`chat --history --session <id>`) as text content, and SHALL map a missing session to a tool error.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `chat_get_history`
- **AND** its input schema declares `session_id` (string, required)

#### Scenario: History of an existing session

- **WHEN** the tool is called with a `session_id` that exists
- **THEN** the result carries the CLI's history rendering for that session

#### Scenario: History of an unknown session

- **WHEN** the tool is called with a `session_id` that does not exist
- **THEN** the tool result is an error reporting the session was not found (surfaced from the CLI's non-zero exit)

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero for any other reason (e.g. SQLite storage unavailable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis

### Requirement: Chat send tool

The MCP server SHALL expose a `chat_send` tool that submits one query into a chat session by driving the secondbrain
CLI (`chat <query> --session <id>` with mapped optional flags and `SECONDBRAIN_SHOW_THINKING=0` in the subprocess
environment), and SHALL return the session id with the answer text.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `chat_send`
- **AND** its input schema declares `query` (string, required), `session_id` (string, optional), `top_k` (integer,
  optional), `temperature` (number, optional), `model` (string, optional)

#### Scenario: New session gets a generated id

- **WHEN** the tool is called without `session_id`
- **THEN** the server generates a UUID v4, passes it to the CLI as `--session <id>`, and returns it in the result
  (the CLI auto-creates the session silently, so no `Created new session:` line appears)

#### Scenario: Answer is extracted cleanly

- **WHEN** the CLI stdout consists of a `▸ Thinking: ...` indicator line followed by the streamed answer
- **THEN** the returned `answer` is the stdout with every `▸ Thinking:`-prefixed line stripped, preserving the rest
- **AND** the subprocess environment contained `SECONDBRAIN_SHOW_THINKING=0` for this call

#### Scenario: Existing session continues

- **WHEN** the tool is called with a `session_id` that already exists
- **THEN** the query is appended to that session's context (CLI receives `--session <existing-id>`) and the returned
  `session_id` matches

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero (e.g. LLM unreachable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis

### Requirement: Chat session listing tool

The MCP server SHALL expose a `chat_list_sessions` tool that returns the CLI's session listing
(`chat --list-sessions`) as text content.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `chat_list_sessions` with an empty input schema (no parameters)

#### Scenario: Listing sessions

- **WHEN** the tool is called
- **THEN** the result carries the CLI's session listing output (one `session_id: N messages (created: ...)` line per session)

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis
