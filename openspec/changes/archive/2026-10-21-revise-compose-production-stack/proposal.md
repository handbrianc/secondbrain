# Revise Compose Production Stack — Proposal

## Why

`docker-compose.yml` today contains only a (now healthchecked) Qdrant service — the application is expected to run
natively on the host. With the MCP server as the container's primary function, the stack must reflect that. This
proposal delivers the core unit: the `mcp-server` primary service with its environment contract, storage mounts, and
dependency wiring.

## What Changes

- **`mcp-server` service (primary)**: built from the revised Dockerfile, host port 8080, `env_file` wiring
  (`.env.docker`), volume mounts — ingest workspace read-only at the workspace root, SQLite storage on a persistent
  volume, optional read-only TLS cert/key mounts — `depends_on` a healthy Qdrant (enabled by
  `harden-compose-qdrant-service`), restart policy, image healthcheck.
- **Environment contract**: the service exposes configuration for all integration points — Qdrant
  (`SECONDBRAIN_QDRANT_URL`/API key/collection), embedding/vector-model API (`SECONDBRAIN_EMBEDDING_*`), LLM API
  (`SECONDBRAIN_LLM_PROVIDER`, `SECONDBRAIN_OPENAI_BASE_URL`, `SECONDBRAIN_OPENAI_API_KEY`,
  `SECONDBRAIN_ANTHROPIC_API_KEY`, `SECONDBRAIN_LLM_MODEL`, ...), SQLite path, and the server's `SECONDBRAIN_MCP_*`
  settings (bind, TLS, auth, CLI binary, workspace root, subprocess timeout, log level) — so the stack can target
  external infrastructure with no image rebuild.
- **`.env.docker` revised** with every variable present and documented inline.
  (2026-10-21 amendment: values were initially committed as this deployment's
  documented working entries; redacted to safe placeholders the same day
  after the push exposed them — fill the real endpoint/key from your
  uncommitted local copy. The missing `SECONDBRAIN_ANTHROPIC_API_KEY` slot
  is present as a commented line.)

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the MCP-primary production stack requirement.

## Dependencies

- Requires: `revise-dockerfile-for-mcp` (the image), `harden-compose-qdrant-service` (healthy dependency target).

**Depended on by:** `revise-compose-test-stack` (pattern), `add-mcp-e2e-smoke`,
`add-mcp-readme-feature-docs`.

## Impact

**Code**: `docker-compose.yml` (new primary service), `.env.docker` (rewritten/expanded).

**Out of scope**: test stack, e2e smoke, docs.

## Non-goals

- TLS termination via external reverse proxy (the server terminates TLS itself; the cert mount is provided).
- Secrets management integrations (Docker secrets/Vault) — env-file based for v1.
- Horizontal scaling/load balancing (single server instance).
