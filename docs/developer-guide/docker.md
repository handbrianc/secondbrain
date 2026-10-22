# Docker Setup

Running the SecondBrain MCP server and its services with Docker.

## Docker Architecture

The container image's primary function is the **`secondbrain-mcp` MCP
server** (it is the image's `CMD`). The same image carries the `secondbrain`
CLI: the server drives the CLI as a subprocess for every tool call. The
stack runs exactly two containers — the MCP server and Qdrant (a hardened
companion service, internal to the compose network). One env file —
`.env.docker` — configures
the whole stack, so endpoints, keys, and model names are runtime-injectable
with no image rebuild.

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose plugin (v2)

Verify installations:

```bash
docker --version
docker compose version
```

## The Production Stack

`docker-compose.yml` defines two services:

| Service | Role | Exposure |
| ------- | ---- | -------- |
| `mcp-server` | The MCP server (primary). Serves `/mcp` (MCP Streamable HTTP, stateless) and `/healthz` | Host port 8080 → container 8080 |
| `qdrant` | Vector database | Internal-only — stack services reach it at `http://qdrant:6333`; publishing 6333 for local tooling is a documented opt-in |

The `mcp-server` service waits for Qdrant's healthcheck before starting and
restarts unless stopped. It also runs under docker-init (`init: true`): the
image entrypoint re-execs into the server, so without an init wrapper the
server itself would be the container's PID 1 — adopting (and never reaping)
the orphaned helper processes each CLI-driven call leaves behind, which shows
up as two defunct `python3.14` processes per ingest-family call. docker-init
(tini) takes the PID 1 seat and reaps them.

The stack's configuration is also bounded for the host it ships on:
`.env.docker` caps the CLI's ingest worker pool at 2
(`SECONDBRAIN_MAX_WORKERS=2`). The default of four parallel docling workers
exhausted a 6 GiB host during heavy PDF parses — the kernel OOM-killed pool
workers inside the server container's cgroup and the CLI died with
`BrokenProcessPool`. The server passes `--cores` to the CLI only when the
caller sets it, so the cap governs default ingest calls; an explicit per-call
`cores` still wins (see the [ingest tool](mcp.md) parameters).

The stack also accepts large uploads: `.env.docker` sets
`SECONDBRAIN_MCP_UPLOAD_MAX_BYTES=104857600` (100 MB; the code default is
10 MB), which raises the derived `/mcp` request-body budget to ≈141 MB with
it — both enforcement points (the rmcp transport and the axum body-limit
layer) derive from the one variable. The CLI's own 100 MiB per-file
processing cap still applies at ingest time.

## Quick Start

```bash
docker compose up -d --build
curl -sS http://localhost:8080/healthz
# {"status":"ok"}
```

Then point your MCP client at `http://localhost:8080/mcp` — the onboarding
path lives in the [MCP Server](mcp.md) guide.

## Configuration (env file)

The stack is configured through `.env.docker`, loaded into the
`mcp-server` service via `env_file`:

- The shipped file contains **safe placeholders only** — keep real secrets
  out of version control and edit your local copy instead.
- Every value is runtime-injectable: retargeting Qdrant, the embedding API,
  or the LLM requires only an env change and `docker compose up -d`, no
  rebuild.
- Groups: the server's `SECONDBRAIN_MCP_*` settings (bind address, workspace
  root, CLI binary, subprocess timeout, log level, and the commented TLS and
  auth blocks), storage/Qdrant, embedding (OpenAI-compatible; required for
  real ingest/search), and LLM (chat).
- The full variable tables live in
  [`mcp-server/README.md`](https://github.com/handbrianc/secondbrain/blob/master/mcp-server/README.md)
  and the [MCP Server](mcp.md) guide.

What the stack mounts:

- `./workspace` → `/data/workspace` (read-only) — the ingest path
  allow-list root (`SECONDBRAIN_MCP_WORKSPACE_ROOT`).
- `./workspace/uploads` → `/data/workspace/uploads` (read-write) — the
  upload staging directory `upload_document` stores into; the only writable
  path in the workspace. No manual setup needed: the container starts as
  root only to hand the staging directory (compose auto-creates missing bind
  sources as root-owned) to the non-root runtime user, then drops
  privileges — the server itself never runs as root.
- `secondbrain-sqlite` volume → `/data/secondbrain` — conversation/session
  storage (`SECONDBRAIN_SQLITE_PATH`).
- `./certs` → `/certs` (read-only) — optional TLS material, uncommented
  together with the TLS block in `.env.docker`.

### Connecting to a Remote Qdrant

To use a managed or remote Qdrant instead of the bundled one, set
`SECONDBRAIN_QDRANT_URL` in `.env.docker` (plus collection name and API key)
and restart the stack — no rebuild, and the bundled service simply goes
unused.

## CLI Commands Against the Stack

The stack runs only the `mcp-server` and `qdrant` containers — there is no
`cli` service. The MCP tools (`ingest_documents`, `search`, `chat_*`,
`upload_document`) cover day-to-day server-side operations. CLI-only
management commands (`delete`, `ls`, `status`) run from an environment that
can reach Qdrant directly: uncomment the documented port publish in
`docker-compose.yml` and run the host-installed CLI against
`localhost:6333`, or start an ad-hoc container on the stack's network:

```bash
docker run --rm --network daring-walrus_secondbrain-network \
  --env-file .env.docker daring-walrus-mcp-server secondbrain status
```

## Test Stack

`docker-compose.test.yml` mirrors the production topology with test
isolation: host port **8081**, an isolated Qdrant collection
(`embeddings_test`), an isolated SQLite database, and the deterministic
fixture workspace (`tests/fixtures/mcp_workspace/`, containing
`sample-document.md`) mounted read-only, with its `uploads/` staging
directory layered read-write for `upload_document`. Its `mcp-server` also
runs under docker-init (`init: true`) for the same PID 1 reaping rationale as
the production stack.

Verify the whole client flow against it:

```bash
./scripts/mcp_e2e_smoke.sh --stack test
```

The smoke drives health → `tools/list` → `ingest_documents` → `search` →
`chat_send` (only when a usable LLM is configured) with curl over HTTP(S) and
tears the stack down on exit. Note: real ingest/search need a usable
embedding endpoint — the mock embedding provider is a pytest fixture only and
cannot be selected via environment, so the stack's `SECONDBRAIN_EMBEDDING_*`
entries must point at an OpenAI-compatible endpoint (documented inline in the
test compose file).

## TLS

Set the TLS block in `.env.docker`
(`SECONDBRAIN_MCP_HTTP_TLS_ENABLED=true` plus cert/key paths inside the
container, e.g. `/certs/cert.pem`), uncomment the `./certs:/certs:ro` mount
in `docker-compose.yml`, and **override the image healthcheck** — it probes
plaintext `http://127.0.0.1:8080/healthz` by design. The server terminates
TLS itself on the same port and loads the material before binding (a bad pair
is a fail-fast refusal naming the offending variable). Self-signed and
internal-CA setup walkthroughs are in the [MCP Server](mcp.md) guide and the
README reference.

## Dockerfile Reference

The repository `Dockerfile` is a two-stage build; there is no need to write
your own:

1. **`mcp-builder`** (`rust:1-slim` + cmake for the TLS crypto provider)
   compiles the `secondbrain-mcp` server binary.
2. **`runtime`** (`python:3.14-slim`) installs the `secondbrain` CLI from the
   repository source and copies the server binary on top.

No endpoints, API keys, or model names are baked into the image — every
`SECONDBRAIN_*` variable is settable at `docker run` / compose time. The
image runs as a non-root `app` user, its healthcheck probes
`http://127.0.0.1:8080/healthz` via the Python stdlib (the slim base ships no
curl/wget), and the default `CMD` is the MCP server. To smoke-verify an image
(build, health, `tools/list`, CLI presence, non-root user):

```bash
./scripts/docker-smoke.sh
```

## Troubleshooting

### Docker Not Found

Install Docker Desktop or Engine:

- macOS/Windows: [Docker Desktop](https://docs.docker.com/desktop/)
- Linux: [Docker Engine](https://docs.docker.com/engine/install/)

### Port Already in Use

The published host port is 8080 (test stack: 8081):

```bash
# Find the process on port 8080
lsof -ti:8080

# Or map a different host port in your compose override
ports:
  - "8090:8080"
```

### Permission Denied (Linux)

Add your user to the docker group:

```bash
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Server Container Fails to Start

Configuration is fail-fast: an invalid `SECONDBRAIN_MCP_*` value (or broken
TLS material) is refused on stderr with the variable named, and the container
exits before listening.

```bash
docker logs secondbrain-mcp-server --tail 100
```

### Healthcheck Fails with TLS Enabled

The image healthcheck probes plaintext HTTP by design; override it with an
HTTPS probe in compose when `SECONDBRAIN_MCP_HTTP_TLS_ENABLED=true` (see the
[MCP Server](mcp.md) guide for a ready-made override).

### Tool Calls Fail with Backend Errors

The MCP tool error text carries the CLI's own diagnostics (exit code and
truncated output). Missing embedding or LLM configuration is the usual
`docker compose up` surprise — check the `SECONDBRAIN_EMBEDDING_*` and
`SECONDBRAIN_LLM_*` / `SECONDBRAIN_OPENAI_*` / `SECONDBRAIN_ANTHROPIC_*`
entries in `.env.docker`.

### Defunct (Zombie) Processes Under the Server Container

`ps` shows defunct (`[python3.14] <defunct>`) children under
`secondbrain-mcp-server`, roughly two per ingest-family call. Cause: the
entrypoint re-execs into the server, so without an init wrapper the server is
the container's PID 1 and adopts the orphans its CLI calls leave behind (the
Python CLI's forkserver + resource tracker) — and the server (tokio) reaps
only children it spawned itself. Fix: the compose services set `init: true`
(docker-init holds PID 1 and reaps them). Recreating the container
(`docker compose up -d`) also clears any zombies the previous process
accumulated — they cannot be killed or reaped from outside.

### Out of Memory During Heavy Ingests (BrokenProcessPool)

An ingest-family tool call fails with `BrokenProcessPool: worker process
crashed mid-batch` (often after many quiet minutes), the staged file stays on
disk, and the store gains no points for it. Cause: the CLI's parallel parse
workers exhausted host memory and the kernel OOM killer killed them inside the
server container's cgroup.

Confirm the kills through the cgroup's own counters — no elevated privileges
needed:

```bash
cat "/sys/fs/cgroup/system.slice/docker-$(docker inspect secondbrain-mcp-server \
  --format '{{.Id}}').scope/memory.events"
# oom_kill N  (N > 0 confirms the kills)
```

`docker inspect` also shows `OOMKilled=true` while the container keeps
running: dockerd recorded the in-cgroup OOM events, but PID 1 (docker-init)
survived them.

Fix: keep the shipped `SECONDBRAIN_MAX_WORKERS=2` cap in `.env.docker`. For
still-larger files, lower `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE`, pass a
smaller per-call `cores`, or split the document. Also make sure the client's
MCP request timeout exceeds the server's
`SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` (900 s) — a shorter client
timeout cancels the call before the CLI can report this diagnostic, which the
client then misreads as a crashed server.

### Container Crash Logs

Debug Qdrant-side failures:

```bash
docker logs secondbrain-qdrant --tail 100
```
