# mcp-deployment Specification

## Purpose
The mcp-deployment capability covers how the Secondbrain MCP server ships and runs in Docker: the production and test Compose stacks, the multi-stage image, the environment contract (.env.docker), Qdrant bundling and port decisions, healthchecks, writable-upload staging, HTTP exposure (ports, TLS, host allowlist), and the end-to-end smoke that verifies the stacks behave as specified. add-mcp-e2e-smoke. Update Purpose after archive.

## Requirements

### Requirement: End-to-end MCP smoke across both stacks

A parameterized smoke script SHALL drive a real MCP client flow over HTTP(S) against either compose stack (`test` or
`prod`): health → `tools/list` → `ingest_documents` of a fixture document → `search` returns the ingested document →
`chat_send` (only when a test LLM is configured), with teardown on exit (including failure).

#### Scenario: Full ingestion-search cycle on the test stack

- **WHEN** `scripts/mcp_e2e_smoke.sh --stack test` runs
- **THEN** it starts the test stack, waits for health, lists tools, ingests the fixture document through the MCP tool,
  and a subsequent MCP search returns that document's content
- **AND** the stack is torn down on exit

#### Scenario: Chat smoke when an LLM is configured

- **WHEN** the smoke runs and the test environment provides a usable LLM configuration
- **THEN** the `chat_send` step executes and returns a non-empty answer bound to a session id
- **WHEN** no LLM configuration is available
- **THEN** the chat step is skipped with an explicit warning and the rest of the smoke still validates

#### Scenario: Production stack smoke parity

- **WHEN** `scripts/mcp_e2e_smoke.sh --stack prod` runs
- **THEN** the same flow completes against the production stack (chat step gated identically)

### Requirement: MCP server is the primary compose service

The production compose stack SHALL define `mcp-server` as the primary application service, built from the project's
Dockerfile, serving the MCP endpoint (default host port 8080), with its lifecycle tied to a healthy Qdrant dependency.

#### Scenario: Stack brings up the server

- **WHEN** `docker compose up -d` runs with the production stack
- **THEN** the `mcp-server` service starts, becomes healthy, and serves `/healthz`
- **AND** Qdrant is awaited healthy before the server starts

#### Scenario: Stack configuration validates

- **WHEN** `docker compose config --quiet` runs
- **THEN** it passes with no errors or warnings

### Requirement: Environment passthrough to external integrations

The `mcp-server` service SHALL expose configuration for all integration points through the compose environment
(`env_file` plus explicit variables): Qdrant (`SECONDBRAIN_QDRANT_URL`, API key, collection), the embedding/vector
model API (`SECONDBRAIN_EMBEDDING_*`), the LLM API (`SECONDBRAIN_LLM_PROVIDER`, `SECONDBRAIN_OPENAI_BASE_URL`,
`SECONDBRAIN_OPENAI_API_KEY`, `SECONDBRAIN_ANTHROPIC_API_KEY`, `SECONDBRAIN_LLM_MODEL`, ...), SQLite path, and the
server's own `SECONDBRAIN_MCP_*` settings (bind, TLS cert/key paths, auth token, CLI binary, workspace root,
subprocess timeout, log level).

#### Scenario: External Qdrant integration

- **WHEN** the stack is run with `SECONDBRAIN_QDRANT_URL` pointing at an external instance
- **THEN** CLI subprocesses (and therefore MCP tool calls) reach that instance instead of the bundled service

#### Scenario: External LLM and embedding API integration

- **WHEN** the stack is run with external `SECONDBRAIN_OPENAI_BASE_URL`/key and `SECONDBRAIN_EMBEDDING_API_BASE`/key/model
- **THEN** search and chat tools operate against those endpoints (no image rebuild required)

#### Scenario: TLS and auth wiring

- **WHEN** `.env.docker` sets `SECONDBRAIN_MCP_HTTP_TLS_ENABLED=true` with cert/key paths mounted read-only
- **THEN** the server serves HTTPS to calling clients; when `SECONDBRAIN_MCP_AUTH_TOKEN` is set, unauthenticated MCP
  requests receive 401

### Requirement: Durable storage mounts

The `mcp-server` service SHALL mount the ingest workspace (read-only into the container at the configured workspace
root) and a persistent volume for SQLite conversation storage, so data survives container replacement.

#### Scenario: Workspace and SQLite persistence

- **WHEN** documents are ingested and a chat session is created, then the containers are recreated
- **THEN** the ingested workspace files and the SQLite session data persist

### Requirement: MCP-primary container image

The project's Docker image SHALL be a multi-stage build whose default entrypoint is the `secondbrain-mcp` MCP server,
and which also ships the `secondbrain` CLI tooling that the server drives (both on `PATH`).

#### Scenario: Image builds from source

- **WHEN** `docker build` runs at the repository root
- **THEN** the build compiles the Rust MCP server from `mcp-server/` in a Rust builder stage
- **AND** the runtime stage is based on `python:3.14-slim` with the Python CLI installed from the repository source

#### Scenario: Both binaries are present

- **WHEN** a container is started with the image's default CMD
- **THEN** the MCP server starts and serves `/healthz`
- **AND** `docker run --rm <image> secondbrain --help` prints the CLI help and exits 0

#### Scenario: MCP endpoint reachable in the container

- **WHEN** the container's health endpoint responds
- **AND** a `tools/list` request is POSTed to the MCP endpoint
- **THEN** a JSON response with the tool list is returned (empty list is acceptable before tool proposals land)

### Requirement: Container runtime hygiene

The image SHALL run commands as the non-root `app` user via the entrypoint's
privilege handover — the image's configured user stays root so the entrypoint
can prepare the writable staging directory and then `gosu` down to `app`
(revise-compose-writable-uploads) — SHALL expose the server port, declare a
HEALTHCHECK against `/healthz`, and use `/data/workspace` as the working
directory.

#### Scenario: Non-root execution

- **WHEN** a command is executed in the container through the image's default
  entrypoint
- **THEN** it runs as the non-root `app` user (the entrypoint hands privileges
  down after preparing the staging directory; the image's configured user
  stays root by design)

#### Scenario: Healthcheck wired

- **WHEN** the container runs and the server is healthy
- **THEN** the Docker HEALTHCHECK reports healthy

#### Scenario: Port declared

- **WHEN** the image is inspected
- **THEN** port 8080 is EXPOSEd (the default bind of `SECONDBRAIN_MCP_HTTP_BIND_ADDR`)

### Requirement: Runtime-configurable integration environment

The image SHALL carry image-default `SECONDBRAIN_MCP_*` values but MUST NOT bake in any endpoint addresses, API keys,
or model names: all `SECONDBRAIN_*` variables — server config, storage (Qdrant), embedding/vector-model settings, LLM
settings, and behavior tuning — SHALL be settable at `docker run`/compose time for integration with an external LLM,
an external embedding/vector-model API, and an external Qdrant instance.

#### Scenario: Environment override takes effect

- **WHEN** a container is run with `SECONDBRAIN_MCP_HTTP_BIND_ADDR=0.0.0.0:9090`
- **THEN** the server listens on 9090

#### Scenario: No baked secrets

- **WHEN** the image is inspected
- **THEN** it contains no API keys, tokens, or hardcoded endpoint URLs for the LLM, embedding API, or Qdrant
- **AND** `docker run -e SECONDBRAIN_QDRANT_URL=... -e SECONDBRAIN_OPENAI_API_KEY=... ...` propagates these to CLI subprocesses (verified in the compose-stack proposals)

### Requirement: Bundled Qdrant is a managed dependency

The production compose stack's `qdrant` service SHALL declare a healthcheck, SHALL persist vector data in a named
volume, and SHALL carry an explicit, documented host-port decision (this deployment publishes 6333 for host-side
CLI tooling; commenting the ports block makes the service internal-only).

#### Scenario: Qdrant reports healthy

- **WHEN** `docker compose up -d` starts the qdrant service
- **THEN** its healthcheck passes on Qdrant's own health endpoint

#### Scenario: Vector data persists

- **WHEN** the qdrant container is recreated
- **THEN** the named volume's vector data survives

#### Scenario: Host port publish is explicit and documented

- **WHEN** the stack is up with the shipped configuration
- **THEN** Qdrant's 6333 port is published for host-side CLI tooling, with the in-file note documenting that
  commenting the ports block makes the service internal-only
- **AND** `docker compose config --quiet` passes

### Requirement: Orphaned subprocess reaping under the server containers

The compose `mcp-server` services SHALL run under docker-init (`init: true`),
so the entrypoint-exec'd server does not hold the container's PID 1 seat:
orphaned processes left behind by each CLI-driven tool call (the Python CLI's
forkserver and resource tracker) reparent to the namespace init and are reaped
there, instead of accumulating as defunct children of the server — which, as
PID 1, adopts them and (as a tokio application) never waits children it did not
spawn itself. The entrypoint's root→runtime-user handover SHALL be unaffected:
docker-init runs the entrypoint as the container's original user, and the
entrypoint keeps re-exec'ing the command as the non-root runtime user. The test stack SHALL mirror the
production setting.

#### Scenario: An ingest-family call leaves no defunct processes

- **WHEN** a client drives a tool call whose CLI run spawns the multiprocessing
  helpers (e.g., `ingest_documents` or `upload_document`)
- **THEN** the helpers outlive the CLI by an instant, are reparented to
  docker-init, and are reaped — no defunct processes remain under the server or
  the init afterward

#### Scenario: Pre-existing zombies clear on recreate

- **WHEN** the `mcp-server` container is recreated with `init: true`
- **THEN** the defunct children accumulated under the previous server process
  are gone (the old namespace is torn down with it)

#### Scenario: The privilege handover is unchanged

- **WHEN** the stack starts the `mcp-server`
- **THEN** docker-init runs the entrypoint as the container's original user,
  the entrypoint performs its root-only staging-directory handover, and the
  server process runs as the non-root runtime user

#### Scenario: Test stack parity

- **WHEN** the test stack runs its `mcp-server`
- **THEN** it also runs under docker-init with the same reaping

### Requirement: 100 MB upload cap in the production stack

The production stack SHALL accept `upload_document` submissions with decoded
content up to 104857600 bytes (100 MB), configured via
`SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` in `.env.docker`. The derived `/mcp`
request-body budget SHALL continue to be computed from the cap as
`ceil(cap × 4/3) + 1 MiB` and SHALL be enforced at both the rmcp transport
and the axum body-limit layer. The CLI's own 100 MiB per-file processing cap
SHALL remain the ceiling applied at ingest time.

#### Scenario: A large PDF uploads in one call

- **WHEN** a client submits a file larger than the compiled-in 10 MB default
  (but at most 104857600 bytes decoded)
- **THEN** the submission passes the tool's budget check, is staged, and is
  ingested — no HTTP 413 and no over-cap tool error

#### Scenario: The body budget scales with the cap

- **WHEN** a `/mcp` request body exceeds the derived budget
  (`ceil(104857600 × 4/3) + 1 MiB` ≈ 141 MB)
- **THEN** the request is rejected with HTTP 413 by both enforcement points
  before reaching a tool handler

#### Scenario: Over-cap decoded content still fails cleanly

- **WHEN** a submission's decoded content exceeds 104857600 bytes while its
  base64 body fits the derived budget
- **THEN** `upload_document` returns an error result naming
  `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`, nothing is stored, and the process
  continues serving

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

### Requirement: Test compose stack includes the MCP server

The test compose stack SHALL include an `mcp-server` service built from the project Dockerfile, wired to the test
Qdrant instance and the repository's test configuration (mock embedding provider, fixture workspace, isolated SQLite
path), exposed on a host port distinct from the production stack (8081).

#### Scenario: Test stack brings up the server

- **WHEN** `docker compose -f docker-compose.test.yml up -d` runs
- **THEN** the `mcp-server` service starts and becomes healthy against the test Qdrant
- **AND** the existing test Qdrant service behavior (host port 6334, test volume) is unchanged

#### Scenario: Test stack configuration validates

- **WHEN** `docker compose -f docker-compose.test.yml config --quiet` runs
- **THEN** it passes

### Requirement: Test services entry point stays coherent

The local test-services script SHALL bring up the extended test stack so the Python test suite and MCP verification
share one environment.

#### Scenario: Local developer workflow

- **WHEN** `scripts/start_test_services.sh` runs
- **THEN** both the test Qdrant and the test `mcp-server` service are started and awaited healthy

### Requirement: Writable upload staging inside the read-only workspace

The `mcp-server` compose services SHALL keep the ingest workspace mounted read-only at the configured workspace
root and SHALL additionally mount the upload staging directory (default `<workspace root>/uploads`,
`SECONDBRAIN_MCP_UPLOAD_DIR`) read-write at its in-container path, so `upload_document` can create the directory
and store submitted files while the served corpus stays immutable. The image SHALL ship an entrypoint that, when
the container starts as root, hands the configured staging directory (resolved like the server's config: default
`uploads` anchored at the workspace root) to the non-root runtime user before re-exec'ing the command as that
user — a compose-auto-created (root-owned) host staging directory works without manual setup, and the server and
CLI never run as root. When the container starts as a non-root user, the entrypoint SHALL skip the handover
(ownership is the operator's). The test stack SHALL mirror the layering over its fixture workspace, with the
staging directory committed in the fixtures.

#### Scenario: Upload succeeds in the stacked server

- **WHEN** the compose stack boots (the staging directory may be a root-owned auto-created directory) and a
  client calls `upload_document` against the compose `mcp-server`
- **THEN** the entrypoint has handed the staging directory to the runtime user, the file is stored under the
  staged upload directory, and ingestion proceeds as in the native server

#### Scenario: The corpus stays read-only

- **WHEN** a tool call or CLI run attempts to write anywhere in the workspace outside the upload staging
  directory
- **THEN** the write fails: only the staged upload directory is writable

#### Scenario: Auto-created host directory works without manual setup

- **WHEN** the host staging directory does not exist and compose auto-creates it root-owned
- **THEN** the entrypoint hands the directory to the runtime user at container start and uploads succeed

#### Scenario: The server never runs as root

- **WHEN** the compose stack starts the `mcp-server`
- **THEN** the container process runs as the non-root runtime user, and the entrypoint performed the ownership
  handover only while starting as root

#### Scenario: Rootless start skips the handover

- **WHEN** the container is started as a non-root user (`docker run --user`, Kubernetes runAsNonRoot)
- **THEN** the entrypoint skips the ownership handover and runs the command as that user

#### Scenario: Test stack parity

- **WHEN** the test stack boots
- **THEN** its fixture workspace is read-only with the committed `uploads/` staging directory layered
  read-write, so `upload_document` works identically there
