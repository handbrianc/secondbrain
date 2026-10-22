# MCP Deployment

## ADDED Requirements

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

The image SHALL run as a non-root user, expose the server port, declare a HEALTHCHECK against `/healthz`, and use
`/data/workspace` as the working directory.

#### Scenario: Non-root execution

- **WHEN** a command is executed in the container
- **THEN** it runs as the non-root `app` user

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
