# secondbrain-mcp

An MCP (Model Context Protocol) server that exposes the secondbrain document
intelligence CLI — ingestion, semantic search, and retrieval-augmented chat —
to MCP clients over HTTP(S).

The server is a thin, hardened wrapper, not a reimplementation: every tool call
drives the Python `secondbrain` CLI as a subprocess through a dedicated
adapter (argument-vector spawning only — no shell, per-call timeout,
process-group cleanup), and the CLI's output is mapped onto MCP tool results.
The server's architecture and its design rationale live in the scaffold
change's design doc: [`openspec/changes/add-mcp-server-scaffold/design.md`](../openspec/changes/add-mcp-server-scaffold/design.md).

## Architecture in one paragraph

`secondbrain-mcp` is a single Rust binary (rmcp + axum on Tokio). It serves
the MCP Streamable HTTP transport at `/mcp` in **stateless mode** — no
initialize handshake, no session ids; each request is self-contained and every
reply is a single `application/json` body — plus a plain `/healthz` health
endpoint. Configuration is parsed once at startup from the `SECONDBRAIN_MCP_*`
environment table and is fail-fast: an invalid value is refused on stderr
before anything binds. The CLI binary also resolves once at startup; a
resolution failure is *not* fatal — the server still boots so `/healthz` and
`tools/list` work, and every tool call then returns an error naming
`SECONDBRAIN_MCP_CLI_BIN`. Structured logs go to stderr (no ANSI); stdout
carries only the machine-readable listen announcement
(`secondbrain-mcp listening on <addr>`). SIGINT/SIGTERM start a graceful
shutdown: the accept loop stops, in-flight requests drain, the process exits
0. Optional TLS is terminated by the server itself on the same port, and
optional bearer-token auth guards `/mcp`.

## Tool reference

| Tool | Purpose | Result | Tool-level errors |
| ---- | ------- | ------ | ----------------- |
| `search` | Semantic search over the ingested knowledge base | JSON array of result chunks (text) | CLI failure; malformed CLI JSON |
| `ingest_documents` | Ingest a file or directory into the knowledge base; `async_mode: true` starts a background job polled via `job_status` | CLI's human-readable ingest summary (text) | path outside the workspace; CLI failure |
| `upload_document` | Store a base64-submitted file in the workspace and ingest it in one call; `async_mode: true` starts a background job polled via `job_status` | Stored path relative to the workspace root + the CLI's ingest summary; the staged file is deleted after a successful ingest and kept on failure (text) | invalid base64; content over `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`; unusable filename; existing target; CLI failure |
| `job_status` | Report the state of asynchronous ingest/upload jobs — with `job_id` one job, without it every job known to this server process | Status text, always a success result: a failed job is conveyed by its `[failed]` status text | unknown job id |
| `chat_send` | Ask one question in a chat session (RAG answer) | JSON `{"session_id","answer"}` (text) | CLI failure (LLM unreachable, …) |
| `chat_list_sessions` | List stored chat sessions | CLI session table (text) | CLI failure |
| `chat_get_history` | Fetch one session's conversation history | CLI history rendering (text) | unknown session; CLI failure |

Every tool is served by the same adapter rules: the subprocess never runs
through a shell, its argv is built element-by-element, hostile text (queries
containing flags or shell metacharacters) stays one verbatim element, and a
failed CLI exit maps to a tool error with truncated diagnostics. Failures at
the tool level are HTTP 200 responses with `"isError": true` — including a
missing required tool argument, which rmcp's argument deserialization rejects
with a message naming the missing field (the CLI never runs). Protocol-level
failures (unknown tool, malformed JSON-RPC) are JSON-RPC errors.

### `search`

Semantic search over the secondbrain knowledge base.

| Parameter | Type | Required | Default | Meaning |
| --------- | ---- | -------- | ------- | ------- |
| `query` | string | yes | — | The semantic search query text |
| `top_k` | integer | no | 50 (CLI default) | Maximum number of results |
| `source` | string | no | — | Only results from this source file path |
| `file_type` | string | no | — | Only results of this file type/category |
| `min_score` | number | no | 0.46 | Minimum similarity score, applied by the **server** (the CLI's JSON output is not threshold-filtered) |

Result: a text content block carrying a compact JSON array of result objects.
Fields include `chunk_id`, `source_file`, `page_number`, `chunk_text`,
`element_type`, `chunk_role`, `section_label`, and `score`; every field the
CLI emits is preserved verbatim through the parse/re-serialize round trip.
Results scoring below `min_score` are dropped (the threshold is inclusive);
a result without a `score` counts as 0.

CLI invocation: `secondbrain search --format json [--top-k N] [--source S]
[--file-type T] -- <query>` — the query always travels after the `--`
separator, as a single verbatim argument.

Errors: the CLI exiting non-zero yields a tool error describing the exit code
with truncated stdout/stderr; unparseable CLI JSON yields a
`malformed CLI output: …` tool error with a truncated preview.

### `ingest_documents`

Ingest a file or directory into the knowledge base (documents are chunked,
embedded, and stored in the vector store).

| Parameter | Type | Required | Default | Meaning |
| --------- | ---- | -------- | ------- | ------- |
| `path` | string | yes | — | File or directory; relative paths resolve against `SECONDBRAIN_MCP_WORKSPACE_ROOT` |
| `recursive` | boolean | no | `false` | Recurse into subdirectories (`-r`) |
| `skip_existing` | boolean | no | `true` | Skip chunks already present; `false` passes `--no-skip-existing` |
| `chunk_size` | integer | no | CLI default | Override the default chunk size |
| `chunk_overlap` | integer | no | CLI default | Override the default chunk overlap |
| `batch_size` | integer | no | CLI default | Batch size for the CLI's processing pool (`-b`) |
| `cores` | integer | no | CLI default | CPU cores for parallel processing (`-c`) |
| `async_mode` | boolean | no | `false` | Run the CLI ingest as a detached background job and return a job id immediately; poll `job_status` for the result (see [Asynchronous ingestion](#asynchronous-ingestion)) |

Result: a text content block reading
`ingest summary (from the secondbrain CLI):` followed by the CLI's
human-readable summary. Documented limitation: the CLI has no JSON ingest
output, so the summary is passed through verbatim.

With `async_mode: true`, path resolution, workspace confinement, and the
argv build stay inside the call — a rejection is the same immediate error as
the synchronous call and creates no job — and only the CLI run moves into a
background job (see [Asynchronous ingestion](#asynchronous-ingestion)).

CLI invocation: `secondbrain ingest <resolved-path> [-r]
[--no-skip-existing] [--chunk-size N] [--chunk-overlap N] [-b N] [-c N]`.

**Path confinement.** The requested path must resolve *inside* the workspace
root — enforced before any argv is built or any subprocess is started:

- The canonicalized root and the canonicalized target are compared, so `..`
  traversal, absolute paths outside the root, and symlinks that resolve
  outside the root are all rejected.
- A target that does not exist (and therefore cannot be canonicalized) is
  compared lexically after `.`/`..` normalization: a missing path *inside*
  the root still reaches the CLI, which reports it as missing, while a
  lexically escaping path is rejected here. A dangling outbound symlink is
  the CLI's missing-path failure, never an ingestion.
- Every rejection names the rule and `SECONDBRAIN_MCP_WORKSPACE_ROOT`, and
  starts no subprocess.

### `upload_document`

Store a document in the workspace and ingest it into the knowledge base in
one call. The file travels base64-encoded in the request; on success it is
stored under `SECONDBRAIN_MCP_UPLOAD_DIR` and ingested through the same
confined CLI flow as `ingest_documents`, after which the staged file is
deleted — the upload directory is a transient inbox and the content lives
in the knowledge base.

| Parameter | Type | Required | Default | Meaning |
| --------- | ---- | -------- | ------- | ------- |
| `filename` | string | yes | — | Name the stored file gets; directory components are stripped (`nested/report.pdf` stores as `report.pdf`) |
| `content_base64` | string | yes | — | The document's bytes, standard-alphabet base64 with canonical padding (the wire payload is ~4/3 of the file size) |
| `skip_existing` | boolean | no | `true` | Skip chunks already present; `false` passes `--no-skip-existing` |
| `chunk_size` | integer | no | CLI default | Override the default chunk size |
| `chunk_overlap` | integer | no | CLI default | Override the default chunk overlap |
| `batch_size` | integer | no | CLI default | Batch size for the CLI's processing pool (`-b`) |
| `cores` | integer | no | CLI default | CPU cores for parallel processing (`-c`) |
| `async_mode` | boolean | no | `false` | Run the CLI ingest as a detached background job and return a job id immediately; poll `job_status` for the result (see [Asynchronous ingestion](#asynchronous-ingestion)) |

Result: a text content block carrying the stored path relative to the
workspace root — the source path recorded in the knowledge base, and the
form a caller can hand back to `ingest_documents` — whether the staged file
was deleted, and the CLI's ingest summary:

```
stored at uploads/report.txt (relative to the workspace root); the staged
file was deleted after the successful ingest
ingest summary (from the secondbrain CLI):
…
```

**Validation before storage.** Every submission is validated before anything
is written, in this order; a rejection stores nothing and starts no
subprocess:

1. `content_base64` must decode as strict standard base64: whitespace,
   URL-safe characters, and non-canonical trailing bits are errors.
2. The decoded size must be at most `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`
   (default 10 MB; inclusive).
3. `filename` must reduce to a usable bare name: empty names, `.`, `..`, and
   directory-only forms are rejected, while any leading directory components
   (absolute paths included) are simply stripped.

**Storage.** The decoded bytes are written into the upload directory, created
on demand by the first upload. The file is created exclusively (`create_new`):
an existing file with the same name is never overwritten — the rejection
names the existing path. A failed write removes the partial file, so a
corrected retry is not blocked by leftover bytes.

**Ingestion.** The stored file is ingested exactly like `ingest_documents`
(recursion never applies — one file, not a directory), with the same
`skip_existing` / chunking / batching knobs. A successful ingest deletes the
staged file: the upload directory stays empty between uploads, and an
upload whose chunks are all already stored also exits 0 as a skip, so its
file is deleted all the same. A CLI failure — or a CLI that could not be
resolved at startup — does not undo the storage: the tool error carries the
stored path ("the document was stored at …, but its ingestion failed / did
not run") so the file can be re-ingested later with `ingest_documents`. If
deleting the file itself fails after a successful ingest, the result stays
a success but says so, and the file remains in place. With `async_mode:
true`, all validation and the staging write stay inside the call, and the
CLI ingest and this staged-file disposition run in the background job —
the job records the same text, disposition sentence included (see
[Asynchronous ingestion](#asynchronous-ingestion)).

**Request-body budget.** An upload at the cap is ~4/3 of it on the wire plus
JSON-RPC framing, so the `/mcp` POST body limit is derived from
`SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` as `ceil(cap × 4/3) + 1 MiB`. This
replaces the transport's built-in defaults (4 MiB on rmcp's streamable
transport, 2 MB on axum): a body over the derived budget is rejected with
`413` before the tool runs, and a call at the configured cap reaches the tool
handler. Raising the cap raises the budget with it.

### `job_status`

Check the status of asynchronous ingest/upload jobs started with
`async_mode: true`.

| Parameter | Type | Required | Default | Meaning |
| --------- | ---- | -------- | ------- | ------- |
| `job_id` | string | no | — | The job to report (a `job-<n>` id from an async start response); omit to list every job known to this server process |

Result: always a success result — the job's own failure lives in the status
text, so "the poll worked, the job failed" stays distinguishable. With a
`job_id`, the text is `Job <id> [<state>] kind=<kind> elapsed=<n>s` followed
by the job's summary while it is running (plus the instruction to poll
again), or the exact result text the synchronous call would have produced
once terminal — including the staged-file disposition sentence for uploads.
Without a `job_id`, the text lists one line per job
(`[<state>] <id> kind=<kind> elapsed=<n>s <summary>`), or
`No jobs have been started since the server started.` on a fresh process.
The one error result is an unknown job id, naming the id and explaining
that jobs are kept in server memory (cleared on restart).

CLI invocation: none — `job_status` is served entirely by the server's
in-memory job registry; no subprocess runs.

### Asynchronous ingestion

Long ingests are the norm for large PDFs (parse plus embedding takes
minutes), so waiting inside the tool call is the wrong contract for them:
any client whose own request timeout is shorter than the CLI run loses the
connection mid-run and never sees the diagnostic. `ingest_documents` and
`upload_document` therefore accept `async_mode` (default `false` — the
synchronous contract is unchanged): with `true` the call validates
everything fast synchronously — path resolution and workspace confinement
and the argv build for both tools; base64 decode, size budget, filename
checks, existing-target check, and the staging write for `upload_document`
— so an invalid call fails immediately with the same diagnostics as the
synchronous call and creates no job. Only the CLI run (and, for uploads,
the delete-after-ingest disposition) detaches into a job, and the call
returns immediately with the job's identifier and the polling instruction:

```console
$ curl -sS http://127.0.0.1:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"ingest_documents","arguments":{"path":"sample-document.md","async_mode":true}}}'
{"jsonrpc":"2.0","id":8,"result":{"content":[{"type":"text","text":"Started ingest job job-1: ingest sample-document.md\nPoll the job_status tool with {\"job_id\": \"job-1\"} for the result; the job runs to completion even if this connection closes."}],"isError":false,…}}
```

Then poll `job_status` with the returned id:

```console
$ curl -sS http://127.0.0.1:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"job_status","arguments":{"job_id":"job-1"}}}'
# while the CLI is still running:
{"jsonrpc":"2.0","id":9,"result":{"content":[{"type":"text","text":"Job job-1 [running] kind=ingest elapsed=42s\ningest sample-document.md\nPoll again with job_status to check completion."}],"isError":false,…}}
# once terminal, the recorded text is what the synchronous call would have returned:
{"jsonrpc":"2.0","id":9,"result":{"content":[{"type":"text","text":"Job job-1 [completed] kind=ingest elapsed=75s\ningest summary (from the secondbrain CLI):\n…"}],"isError":false,…}}
```

The properties of a detached job:

- **The job outlives the connection.** A started job runs to completion (or
  to its subprocess deadline) even if the client disconnects or the
  connection closes; its outcome stays retrievable via `job_status`. The
  same `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` deadline (default
  900 s) bounds it — a job that outlives the cap fails with the adapter's
  timeout diagnostic, visibly in the job status.
- **Polls never fail for a failed job.** Job-status results are always
  success results; a failed job is conveyed by its `[failed]` status text
  (carrying the same diagnostics the synchronous call would have returned).
  Only an unknown job id is an error result.
- **The registry is in server memory.** Job ids are sequential per process
  (`job-1`, `job-2`, …), finished jobs are retained up to 100 (the oldest
  evicted; running jobs are never evicted), and the registry is cleared
  when the server restarts — previously issued ids are reported as unknown,
  and a CLI run detached at restart time was terminated with the process
  (a staged upload file, if any, is retained per the failed-ingest
  contract).
- **No concurrency limiting.** Multiple jobs may run at once, each bounded
  by its subprocess timeout; concurrent heavy jobs contend for the same
  host memory, so callers ingesting several heavy files should still do so
  sequentially.
- **No progress reporting.** The CLI exposes no progress protocol; polling
  returns running/completed/failed only. Job cancellation is a recorded
  non-goal: a started job runs to completion.

### `chat_send`

Send one query into a secondbrain chat session (retrieval-augmented answer
over the ingested knowledge base).

| Parameter | Type | Required | Default | Meaning |
| --------- | ---- | -------- | ------- | ------- |
| `query` | string | yes | — | The question to ask |
| `session_id` | string | no | generated | The session to continue; when omitted a fresh UUID v4 session id is generated and returned |
| `top_k` | integer | no | 20 (CLI default) | Number of chunks to retrieve |
| `temperature` | number | no | 0.1 (CLI default) | LLM temperature |
| `model` | string | no | CLI-configured | LLM model override |

Result: a text content block carrying a JSON object —
`{"session_id":"…","answer":"…"}`. Pass the returned `session_id` to continue
the conversation. The server sets `SECONDBRAIN_SHOW_THINKING=0` for the call
and strips any `▸ Thinking:` reasoning-indicator lines from the CLI's output;
interior blank lines of a streamed answer are preserved.

CLI invocation: `secondbrain chat --session <id> [--top-k N]
[--temperature T] [--model M] -- <query>`.

Errors: CLI failure (LLM unreachable, provider error, …) yields a tool error
with truncated stdout/stderr.

### `chat_list_sessions`

List the stored chat sessions. Takes no parameters.

Result: the CLI's session listing passed through as text — one line per
session in the CLI's human-readable format
`session_id: N messages (created: ...)`. Documented limitation: the CLI has
no JSON mode for session listing, so the table is passed through verbatim.

CLI invocation: `secondbrain chat --list-sessions`.

### `chat_get_history`

Fetch the full conversation history of a chat session.

| Parameter | Type | Required | Default | Meaning |
| --------- | ---- | -------- | ------- | ------- |
| `session_id` | string | yes | — | The session whose history to fetch |

Result: the CLI's history rendering passed through as text (one message per
line; no JSON mode exists). Errors: a session that does not exist makes the
CLI exit non-zero, which maps to a tool error; omitting the required
`session_id` likewise fails as a tool error whose message names the missing
field (rmcp's argument deserialization rejects it before the CLI runs).

CLI invocation: `secondbrain chat --history --session <id>`.

## Server configuration (`SECONDBRAIN_MCP_*`)

All server settings are environment variables, parsed and validated once at
startup. An **empty value is treated as unset**, so the documented default
applies. An invalid value is a fail-fast refusal: the message is printed to
stderr as `secondbrain-mcp: invalid configuration: <VARIABLE>: <reason>` and
the process exits 1 before anything binds.

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `SECONDBRAIN_MCP_HTTP_BIND_ADDR` | `0.0.0.0:8080` | Listen address, parsed as a socket address (`IP:PORT`); hostnames are not resolved |
| `SECONDBRAIN_MCP_HTTP_TLS_ENABLED` | `false` | Serve HTTPS instead of plaintext HTTP |
| `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` | — | PEM certificate chain; only read (and validated) when TLS is enabled |
| `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH` | — | PEM private key; only read (and validated) when TLS is enabled |
| `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` | rmcp's default: `localhost`, `127.0.0.1`, `::1` | `Host` header allow-list on `/mcp` (DNS-rebinding protection): comma-separated entries; an entry without a port matches any port, an entry with a port must match exactly; setting the list replaces the default |
| `SECONDBRAIN_MCP_AUTH_TOKEN` | unset (open) | Bearer token guarding `/mcp`; unset or empty leaves the surface open |
| `SECONDBRAIN_MCP_CLI_BIN` | `secondbrain` | The CLI binary to drive — a name looked up on `PATH` or a path; resolved once at startup |
| `SECONDBRAIN_MCP_WORKSPACE_ROOT` | `.` | Root of the ingest path allow-list; relative ingest paths resolve against it |
| `SECONDBRAIN_MCP_UPLOAD_DIR` | `<workspace root>/uploads` | Where `upload_document` stores uploaded files; a relative value joins `SECONDBRAIN_MCP_WORKSPACE_ROOT` like a relative ingest path. Must resolve inside the workspace root — canonical comparison for an existing directory, lexical for a not-yet-created one — and an escaping value refuses startup like any other invalid configuration |
| `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` | `10485760` (10 MB) | Decoded-size cap for `upload_document` submissions, inclusive. Raising it raises the derived `/mcp` request-body budget with it (see the tool reference); the CLI's own 100 MiB per-file processing cap still applies at ingest time |
| `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` | `900` | Per-call CLI subprocess timeout in seconds; must be greater than 0; expiry kills the process group |
| `SECONDBRAIN_MCP_LOG_LEVEL` | `info` | Log filter: `trace`, `debug`, `info`, `warn`, or `error` (case-insensitive) |

Independently of auth, `/mcp` refuses a `Host` header outside the allow-list
with `403 Forbidden` — rmcp's DNS-rebinding protection, admitting only the
loopback names by default; `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` replaces that
set when clients must reach the server through a real hostname.

A failed TLS load is likewise fail-fast —
`secondbrain-mcp: invalid TLS configuration: <VARIABLE>: <reason>` on stderr,
exit 1, before the socket ever listens.

## Integration environment (Python `SECONDBRAIN_*`)

The CLI subprocesses inherit the server's process environment, so every
`SECONDBRAIN_*` variable set for the server — in practice the compose
stack's `env_file` (`.env.docker`) — reaches the CLI. The one exception is
deliberate: the server itself sets `SECONDBRAIN_SHOW_THINKING=0` on every
`chat_send` call (see below). Any other `SECONDBRAIN_*` variable passes
through untouched; the authoritative CLI-side knob list lives in the Python
configuration (`src/secondbrain/config/`) and in `.env.docker`.

The groups the bundled stack relies on:

### Storage / Qdrant

| Variable | Meaning |
| -------- | ------- |
| `SECONDBRAIN_STORAGE_BACKEND` | Vector store backend (`qdrant` in the bundled stacks) |
| `SECONDBRAIN_QDRANT_URL` | Qdrant endpoint; in-network for compose (`http://qdrant:6333`) |
| `SECONDBRAIN_QDRANT_COLLECTION` | Collection name |
| `SECONDBRAIN_QDRANT_API_KEY` | Optional Qdrant API key |
| `SECONDBRAIN_SQLITE_PATH` | Conversation/session storage; on the persistent `secondbrain-sqlite` volume in compose |

**Embedding** (OpenAI-compatible; required for real ingest/search — the mock
embedding provider is a pytest fixture only and cannot be selected via
environment)

| Variable | Meaning |
| -------- | ------- |
| `SECONDBRAIN_EMBEDDING_PROVIDER` | Embedding provider (`openai` for the OpenAI-compatible API) |
| `SECONDBRAIN_EMBEDDING_MODEL` | Embedding model name |
| `SECONDBRAIN_EMBEDDING_API_BASE` | OpenAI-compatible base URL |
| `SECONDBRAIN_EMBEDDING_API_KEY` | API key (or none for a self-hosted endpoint) |
| `SECONDBRAIN_EMBEDDING_DIMENSIONS` | Vector dimensions; must match the Qdrant collection |

**LLM** (chat answers)

| Variable | Meaning |
| -------- | ------- |
| `SECONDBRAIN_LLM_PROVIDER` | `openai` (default) or `anthropic` |
| `SECONDBRAIN_OPENAI_BASE_URL` | OpenAI-compatible endpoint (self-hosted endpoints need no key) |
| `SECONDBRAIN_OPENAI_API_KEY` | API key for the OpenAI-compatible provider |
| `SECONDBRAIN_ANTHROPIC_API_KEY` | API key (with `SECONDBRAIN_LLM_PROVIDER=anthropic`) |
| `SECONDBRAIN_LLM_MODEL` | Model name |

### Behavior

| Variable | Meaning |
| -------- | ------- |
| `SECONDBRAIN_SHOW_THINKING` | The CLI's reasoning-indicator toggle. The server forces `0` on every `chat_send` call so answers can be extracted cleanly; set it to `1` for interactive CLI runs (it does not affect MCP calls) |

## Authentication (bearer token)

Auth is enforced when and only when `SECONDBRAIN_MCP_AUTH_TOKEN` is set to a
non-empty value; unset or empty leaves `/mcp` open — the v1 posture for the
private stack (a full OAuth 2.1 resource-server flow is the recorded
follow-up).

With a token configured, every `/mcp` request must carry
`Authorization: Bearer <token>`:

- The scheme match is case-insensitive; the separator must be exactly one
  space; extra or embedded spaces reject.
- More than one `Authorization` header, a non-UTF-8 value, a wrong scheme, or
  a missing/empty token all reject.
- The comparison is constant-time.
- Rejections are `401` with `WWW-Authenticate: Bearer`, logged at `warn`.
- `/healthz` stays open regardless of auth.

```console
$ curl -sS https://127.0.0.1:8080/mcp \
    -H 'Authorization: Bearer '"$SECONDBRAIN_MCP_AUTH_TOKEN" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## TLS / HTTPS

Set `SECONDBRAIN_MCP_HTTP_TLS_ENABLED=true` and point
`SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` / `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH` at
a PEM-encoded certificate chain and PEM-encoded private key. The server
terminates TLS itself, on the same listen address it would serve HTTP on.
The material loads **before** the socket binds: a missing or invalid pair is
a fail-fast refusal naming the offending variable — the server never listens
with broken TLS. With TLS disabled, the cert/key variables are ignored
entirely (no validation runs).

**Self-signed** (single host, quick start):

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem \
    -days 365 -nodes -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

SECONDBRAIN_MCP_HTTP_TLS_ENABLED=true \
SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH=$PWD/certs/cert.pem \
SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH=$PWD/certs/key.pem \
SECONDBRAIN_MCP_HTTP_BIND_ADDR=127.0.0.1:8080 \
./target/release/secondbrain-mcp
```

Clients must then trust the certificate — for curl, either `--cacert
certs/cert.pem` or, for throwaway tests only, `-k`.

**Internal CA**: issue the server certificate (and key) from your
organization's CA with the host's DNS name / IP in the subject alternative
name, and pass both PEM files. Clients that already trust the CA root need no
per-client configuration.

**In compose**: mount the material read-only (`- ./certs:/certs:ro` —
uncommented in `docker-compose.yml`), set the TLS block in `.env.docker`, and
override the image healthcheck: the image's built-in healthcheck probes
plaintext `http://127.0.0.1:8080/healthz` by design, so TLS deployments
should replace it with an HTTPS probe (skipping local certificate
verification).

## JSON-RPC wire examples

The transport is MCP's Streamable HTTP, serving stateless mode: POST JSON-RPC
to `/mcp` — no initialize handshake, no session id header. Requests must
carry `Content-Type: application/json` and an `Accept` offering **both**
`application/json` and `text/event-stream` (anything else is `406`);
`GET`/`DELETE` on `/mcp` are `405`. Every reply is a single
`application/json` body (no event streams). Depending on the negotiated
protocol revision, result objects may carry additional fields (e.g.
`resultType`) — clients should treat unknown fields as opaque.

The examples below mirror what `scripts/mcp_e2e_smoke.sh` drives against the
compose stacks (with the auth header omitted because those stacks run in
open mode).

List the tools:

```console
$ curl -sS http://127.0.0.1:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"search",…},{"name":"ingest_documents",…},{"name":"upload_document",…},{"name":"job_status",…},{"name":"chat_send",…},{"name":"chat_list_sessions",…},{"name":"chat_get_history",…}],…}}
```

Call `ingest_documents` with a workspace-relative path:

```console
$ curl -sS http://127.0.0.1:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ingest_documents","arguments":{"path":"sample-document.md"}}}'
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"ingest summary (from the secondbrain CLI):\n…"}],"isError":false,…}}
```

Call `upload_document` (the payload is the document's bytes, base64-encoded;
the result carries the stored path and the CLI's ingest summary):

```console
$ curl -sS http://127.0.0.1:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"upload_document","arguments":{"filename":"report.txt","content_base64":"Q2h1bmsgdGV4dCBmcm9tIHRoZSBzYW1wbGUgZG9jdW1lbnQu"}}}'
{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"stored at uploads/report.txt (relative to the workspace root)\ningest summary (from the secondbrain CLI):\n…"}],"isError":false,…}}
```

Call `search` (the text content is a JSON array of chunk objects):

```console
$ curl -sS http://127.0.0.1:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"search","arguments":{"query":"Secondbrain semantic search embedding vectors Qdrant ingestion"}}}'
{"jsonrpc":"2.0","id":4,"result":{"content":[{"type":"text","text":"[{\"chunk_id\":\"…\",\"source_file\":\"sample-document.md\",\"chunk_text\":\"…\",\"score\":0.93},…]"}],"isError":false,…}}
```

Call `chat_send` (omitting `session_id` generates and returns one):

```console
$ curl -sS http://127.0.0.1:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"chat_send","arguments":{"query":"What does the sample document say about semantic search?"}}}'
{"jsonrpc":"2.0","id":5,"result":{"content":[{"type":"text","text":"{\"session_id\":\"2f0c…\",\"answer\":\"The sample document says…\"}"}],"isError":false,…}}
```

Tool-level error (HTTP 200, `"isError": true`):

```json
{"jsonrpc":"2.0","id":6,"result":{"content":[{"type":"text","text":"ingest path escapes the workspace: SECONDBRAIN_MCP_WORKSPACE_ROOT is \"/data/workspace\" and only paths inside it may be ingested, …"}],"isError":true,…}}
```

Protocol-level error (unknown tool, e.g. `tools/call` naming `no_such_tool`):

```json
{"jsonrpc":"2.0","id":7,"error":{"code":-32602,"message":"…"}}
```

Health (no auth, no JSON-RPC):

```console
$ curl -sS http://127.0.0.1:8080/healthz
{"status":"ok"}
```

## Build and run

```bash
cd mcp-server
cargo build --release
# binary: mcp-server/target/release/secondbrain-mcp
```

Running it needs the `secondbrain` CLI resolvable (`SECONDBRAIN_MCP_CLI_BIN`
or on `PATH`) and the CLI's integration environment pointing at Qdrant, the
embedding API, and the LLM (see the `SECONDBRAIN_*` reference above):

```bash
SECONDBRAIN_MCP_HTTP_BIND_ADDR=127.0.0.1:8080 \
SECONDBRAIN_MCP_CLI_BIN=/path/to/secondbrain \
SECONDBRAIN_MCP_WORKSPACE_ROOT=$HOME/workspace \
./target/release/secondbrain-mcp
# stdout: secondbrain-mcp listening on 127.0.0.1:8080
# stderr: structured logs
```

SIGINT/SIGTERM drain in-flight requests and exit 0. The Rust test suite
(`cargo test` inside `mcp-server/`) boots the real binary on ephemeral ports
against stub CLI fixtures and exercises every tool, the transport, auth, TLS,
logging, and shutdown.

## Container and compose usage

The image is a two-stage build (`Dockerfile`): `rust:1-slim` compiles
`secondbrain-mcp`; `python:3.14-slim` installs the `secondbrain` CLI from the
repository source and carries the server binary. No endpoints, API keys, or
model names are baked in — everything is runtime-injectable.

Production stack (`docker-compose.yml`, contract in `.env.docker`):

```bash
docker compose up -d --build      # mcp-server on host port 8080; qdrant internal-only
```

- `mcp-server` mounts `./workspace` read-only at `/data/workspace` (the
  configured `SECONDBRAIN_MCP_WORKSPACE_ROOT`) and persists chat sessions on
  the `secondbrain-sqlite` volume. The one writable exception is the upload
  staging directory: `./workspace/uploads` is layered read-write at
  `/data/workspace/uploads` so `upload_document` can store files while the
  served corpus stays immutable (staged uploads are transient — deleted
  again after their successful ingest). No manual setup: the image's entrypoint
  starts as root only to hand the staging directory (compose auto-creates
  missing bind sources as root-owned) to the non-root runtime user, then
  drops privileges — the server itself never runs as root.
- The stack runs only the `mcp-server` and `qdrant` services (no `cli`
  companion). CLI-only management commands (`delete`, `ls`, `status`) run
  outside the stack: publish Qdrant's port (the documented opt-in in
  `docker-compose.yml`) and run the host CLI, or start an ad-hoc container on
  the stack's network with `--env-file .env.docker`.

Test stack (`docker-compose.test.yml`): same topology on host port **8081**,
with the deterministic fixture workspace
(`tests/fixtures/mcp_workspace/`, containing `sample-document.md`) mounted
read-only and its `uploads/` staging directory layered read-write (committed
in the fixtures) — the stack `scripts/mcp_e2e_smoke.sh --stack test` drives.

```bash
docker compose -f docker-compose.test.yml up -d --build
```

## Verification

- `./scripts/mcp_e2e_smoke.sh --stack test` (or `--stack prod`) — the
  end-to-end verification entry point: boots the compose stack, then drives
  health → `tools/list` → `ingest_documents` → `search` → `chat_send` (only
  when a usable LLM is configured) with curl over HTTP(S), asserting the
  documented wire shapes above, and tears the stack down on exit.
- `./scripts/run_all_tests.sh` — both suites in one command: the Python
  suite (pytest, repo defaults apply) followed by the Rust gate (`cargo
  fmt --check`, `clippy --all-targets -- -D warnings`, `cargo test`);
  `--python-only` / `--rust-only` scope it. Skips the Rust part with a note
  when no toolchain is present; CI still gates the suites separately
  (`test-quality-gates.yml`, `rust-checks.yml`).
- `cargo test` (in `mcp-server/`) — the server's own suite.
- `tests/test_docs/test_mcp_docs.py` — keeps this README honest: it parses
  the registered tool names from `mcp-server/src/tools/*.rs` and the
  `SECONDBRAIN_MCP_*` variables from `mcp-server/src/config.rs`, and fails if
  any of them is missing from this README (documentation drift alarm).

## Documented limitations

- Chat session listing and history are the CLI's human-readable text: the
  CLI has no JSON modes for them (only `chat_send`'s answer is extracted into
  a structured `{"session_id","answer"}` result).
- Ingestion (via `ingest_documents` and via `upload_document`) returns the
  CLI's human-readable summary; no JSON ingest output exists.
- Uploads travel base64-encoded — roughly 4/3 of the file size on the wire —
  with no streaming or multipart form; raising
  `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` above the CLI's own 100 MiB per-file
  processing cap does not lift that cap at ingest time.
- Search results mirror whatever fields the CLI emits — new CLI fields flow
  through verbatim, so treat the field list above as the current shape.
- Session deletion is interactive in the CLI and is deliberately not exposed
  as an MCP tool.
- Asynchronous ingestion jobs live in one server process's memory: ids are
  unknown after a restart, and there is no shared registry across replicas.
  A job reports running/completed/failed only — the CLI has no progress
  protocol, and cancellation is a recorded non-goal (a started job runs to
  completion).
- Sources/citations in chat answers are a recorded non-goal for v1.
