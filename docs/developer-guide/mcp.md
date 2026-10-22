# MCP Server

The MCP (Model Context Protocol) server exposes SecondBrain — document
ingestion, semantic search, and retrieval-augmented chat — to MCP clients over
HTTP(S). It is a thin, hardened wrapper around the `secondbrain` CLI: every
tool call drives the CLI as a subprocess (no shell, per-call timeout), so the
server and the CLI always behave identically.

**Reference**: [`mcp-server/README.md`](https://github.com/handbrianc/secondbrain/blob/master/mcp-server/README.md)
is the source of truth — the full tool reference (parameters, defaults, result
shapes, error semantics), the complete `SECONDBRAIN_MCP_*` server
configuration table, the Python `SECONDBRAIN_*` integration surface, TLS and
auth details, and wire-level JSON-RPC examples. This page is the onboarding
path; the README is the deep reference.

## Quick Start (Compose)

```bash
docker compose up -d --build
curl -sS http://localhost:8080/healthz
# {"status":"ok"}
```

What the stack starts (see [Docker Setup](docker.md)):

| Service | Role | Exposure |
| ------- | ---- | -------- |
| `mcp-server` | The MCP server (primary) | Host port 8080 → container 8080 |
| `qdrant` | Vector database | Internal-only (no published ports) |

Configuration comes from `.env.docker` (loaded via the service's
`env_file`). The shipped file contains safe placeholders only — copy it and
fill in your endpoints and keys. Key entries: the ingest workspace root
(`/data/workspace`, with the host `./workspace` mounted read-only and
`./workspace/uploads` layered read-write for `upload_document` — the image
entrypoint fixes that directory's ownership at startup), the
Qdrant URL (`http://qdrant:6333` in-network), and the embedding and LLM
settings that real ingest/search/chat calls need (see
[Integration Environment](#integration-environment)).

## Pointing an MCP Client at the Server

The transport is MCP's Streamable HTTP in stateless mode: POST JSON-RPC to
`/mcp` — no initialize handshake and no session id handling are required from
the client, and every reply is a single `application/json` body.

A client needs three things:

- **URL**: `http://localhost:8080/mcp` (or `https://…` once TLS is on).
- **Headers**: `Content-Type: application/json` and an `Accept` offering both
  `application/json` and `text/event-stream` (anything else is rejected with
  `406`). With auth enabled, `Authorization: Bearer <token>`.
- **State**: none — requests are self-contained.

Typical client configuration (HTTP transport; adapt the shape to your
client):

```json
{
  "mcpServers": {
    "secondbrain": {
      "type": "http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

Smoke-check the endpoint with curl (drop the auth header when no token is
configured):

```console
$ curl -sS http://localhost:8080/mcp \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Tools at a Glance

| Tool | Purpose | Notable defaults |
| ---- | ------- | ---------------- |
| `search` | Semantic search over the ingested knowledge base | `top_k` 50 (CLI); `min_score` 0.46, applied by the server |
| `ingest_documents` | Ingest a file or directory | `recursive` false; `skip_existing` true; `async_mode` false — true detaches the CLI run into a job polled via `job_status` |
| `upload_document` | Store an uploaded file in the workspace and ingest it in one call | `skip_existing` true; stored under `SECONDBRAIN_MCP_UPLOAD_DIR` (default `uploads` inside the workspace root, 10 MB decoded cap), never overwrites an existing file; the staged file is deleted after its successful ingest; `async_mode` false — same detached-job contract as `ingest_documents` |
| `job_status` | Report the state of asynchronous ingest/upload jobs — one job with `job_id`, every job known to this server process without it | always a success result; a failed job is conveyed by its `[failed]` status text; only an unknown id is an error |
| `chat_send` | Ask one question in a session (RAG answer) | `top_k` 20, `temperature` 0.1 (CLI); generates + returns a UUID v4 `session_id` when omitted |
| `chat_list_sessions` | List stored chat sessions | — |
| `chat_get_history` | Fetch one session's history | requires `session_id` |

Parameter tables, result shapes, and the exact CLI invocation behind each tool
are documented in the README reference. Result highlights: `search` returns a
JSON array of chunk objects (fields include `chunk_id`, `source_file`,
`page_number`, `chunk_text`, `score`); `ingest_documents` returns the CLI's
human-readable ingest summary; `upload_document` returns the stored path
(relative to the workspace root) plus that same ingest summary, and deletes
the staged file after a successful ingest — a failed ingest keeps the
stored file and reports its path for a later re-ingest;
`ingest_documents` and `upload_document` also accept `async_mode: true`
(detached background job: the call returns a job id immediately, `job_status`
reports the job and finally the same text the synchronous call would have
returned — jobs live in server memory only and are cleared at restart);
`chat_send` returns
`{"session_id": "…", "answer": "…"}` — pass the returned id to continue the
conversation.

## Enabling TLS

Set the TLS block in `.env.docker`, mount the material read-only, and override
the image healthcheck (it probes plaintext by design):

```dotenv
SECONDBRAIN_MCP_HTTP_TLS_ENABLED=true
SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH=/certs/cert.pem
SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH=/certs/key.pem
```

```yaml
# docker-compose.override.yml
services:
  mcp-server:
    volumes:
      - ./certs:/certs:ro
    healthcheck:
      test:
        - CMD
        - python3
        - -c
        - "import ssl, urllib.request; ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE; urllib.request.urlopen('https://127.0.0.1:8080/healthz', timeout=4, context=ctx)"
```

The server terminates TLS itself on the same port, and loads the PEM
certificate/key **before** binding — a bad pair is a fail-fast refusal naming
the offending variable. For a quick self-signed pair:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem \
    -days 365 -nodes -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Clients must trust the certificate (`--cacert certs/cert.pem` for curl, or
your CA root). The README reference has the full HTTPS setup walkthrough.

## Authentication

Auth is enabled by setting a non-empty `SECONDBRAIN_MCP_AUTH_TOKEN` in
`.env.docker` (empty or unset = open mode). Every `/mcp` request must then
carry `Authorization: Bearer <token>`; failures are `401` with
`WWW-Authenticate: Bearer`. `/healthz` stays open. Restart the stack
(`docker compose up -d`) after changing the file.

## Integration Environment

The CLI subprocesses inherit the server's environment, so the stack's
`SECONDBRAIN_*` entries in `.env.docker` configure everything the tools need:

| Group | Variables |
| ----- | --------- |
| Storage / Qdrant | `SECONDBRAIN_STORAGE_BACKEND`, `SECONDBRAIN_QDRANT_URL`, `SECONDBRAIN_QDRANT_COLLECTION`, `SECONDBRAIN_QDRANT_API_KEY`, `SECONDBRAIN_SQLITE_PATH` |
| Embedding (OpenAI-compatible; required for real ingest/search) | `SECONDBRAIN_EMBEDDING_PROVIDER`, `SECONDBRAIN_EMBEDDING_MODEL`, `SECONDBRAIN_EMBEDDING_API_BASE`, `SECONDBRAIN_EMBEDDING_API_KEY`, `SECONDBRAIN_EMBEDDING_DIMENSIONS` |
| LLM (chat answers) | `SECONDBRAIN_LLM_PROVIDER`, `SECONDBRAIN_OPENAI_BASE_URL`, `SECONDBRAIN_OPENAI_API_KEY`, `SECONDBRAIN_ANTHROPIC_API_KEY`, `SECONDBRAIN_LLM_MODEL` |
| Behavior | `SECONDBRAIN_SHOW_THINKING` — forced to `0` by the server on every `chat_send` call |

The server's own settings (`SECONDBRAIN_MCP_*`: bind address, TLS, host
allow-list, auth token, CLI binary, workspace root, upload directory, upload
size cap, subprocess timeout, log level) are listed in the README reference
and in the [Docker Setup](docker.md) env-file section.

## Verifying End to End

`scripts/mcp_e2e_smoke.sh --stack test` (or `--stack prod`) boots the compose
stack and drives the real client flow with curl — health → `tools/list` →
`ingest_documents` → `search` → `chat_send` (only when a usable LLM is
configured) — asserting the documented wire shapes, then tears the stack down.
The `test` stack (`docker-compose.test.yml`, host port 8081) runs against a
deterministic fixture workspace and an isolated Qdrant collection.

## Troubleshooting

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| `401` from `/mcp` | Missing or wrong bearer token (auth is on) | Set the same token in the client's `Authorization: Bearer` header and `.env.docker`'s `SECONDBRAIN_MCP_AUTH_TOKEN`; an empty value means auth is off |
| TLS handshake / certificate errors | Wrong or untrusted certificate paths | Check `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` / `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH` point at a matching PEM pair; make the client trust the cert (`--cacert` or your CA root) |
| Tool error with CLI diagnostics | The CLI subprocess failed (or the LLM/embedding backend is misconfigured) | Read the error text: it carries the CLI's exit code and truncated output naming the cause — usually a `SECONDBRAIN_*` integration setting |
| Tool error naming `SECONDBRAIN_MCP_CLI_BIN` | The CLI binary could not be resolved | In containers the CLI ships in the image (default `secondbrain`); for non-container runs point `SECONDBRAIN_MCP_CLI_BIN` at the installed CLI |
| Tool error "ingest path escapes the workspace" | Requested path resolves outside `SECONDBRAIN_MCP_WORKSPACE_ROOT` (by design) | Ingest only paths inside the workspace root mounted into the container |
| Server refuses to start: "invalid configuration: SECONDBRAIN_MCP_UPLOAD_DIR: the upload directory escapes the workspace" | The configured upload directory resolves outside the workspace root | Set `SECONDBRAIN_MCP_UPLOAD_DIR` to a directory inside `SECONDBRAIN_MCP_WORKSPACE_ROOT` (relative values anchor at the root; the directory is created on demand) |
| Upload tool error: "the uploaded document could not be stored (… permission denied)" | The host staging directory is not writable by the container's runtime user (compose auto-creates bind sources as root) | Rebuild and restart the stack — the image entrypoint hands the staging directory to the runtime user at startup; under rootless deployment (`--user`, Kubernetes runAsNonRoot) the handover is skipped, so make the directory writable yourself |
| `413` on POST `/mcp` for an `upload_document` call | The request body exceeds the budget derived from `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (`ceil(cap × 4/3) + 1 MiB`; transport defaults are 2–4 MiB) | Send a smaller file, or raise `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` in `.env.docker` — the body budget grows with it |
| Tool error "the uploaded content is too large" | The decoded content exceeds `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`; nothing was stored | Send a smaller file or raise the cap; the CLI's own 100 MiB per-file processing cap still applies at ingest time |
| Tool error "the upload target already exists" | A file with that name is already in the upload directory (uploads never overwrite) | Pick another `filename`, or ingest the stored file as-is with `ingest_documents` |
| `406` on POST `/mcp` | `Accept` header missing one of the two media types | Send `Accept: application/json, text/event-stream` |
| `405` on `GET /mcp` | Wrong method | The stateless transport accepts `POST` only |
| `403` "Forbidden: Host header is not allowed" on `/mcp` | The client's `Host` is outside the server's allow-list (DNS-rebinding protection; default `localhost`, `127.0.0.1`, `::1`) | Point the client at `localhost`/`127.0.0.1`, or set `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` in `.env.docker` (comma-separated; an entry with a port must match exactly; the list replaces the default) |
| `search` returns nothing | No embedding endpoint configured, collection empty, or threshold too high | Configure the `SECONDBRAIN_EMBEDDING_*` entries, ingest documents first, or lower `min_score` (default 0.46) |
| Server unreachable | Bind address / port mismatch | Default bind is `0.0.0.0:8080`; compose publishes host 8080 (test stack 8081); check `docker logs secondbrain-mcp-server` |
