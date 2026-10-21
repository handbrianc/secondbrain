# MCP Deployment

## ADDED Requirements

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
