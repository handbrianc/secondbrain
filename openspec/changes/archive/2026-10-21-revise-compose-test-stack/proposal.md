# Revise Compose Test Stack — Proposal

## Why

`docker-compose.test.yml` currently provides only a Qdrant test instance (host port 6334) for the Python test suite.
Once the MCP server is the primary function, the test environment must run it the way production will: MCP clients →
server → Python CLI → (mock embeddings + test Qdrant). This proposal delivers that environment unit — the test-stack
`mcp-server` service, its fixture workspace, and coherence of the existing test-services entry point. The end-to-end
smoke harness that drives it is a separate unit (`add-mcp-e2e-smoke`).

## What Changes

- **`docker-compose.test.yml` extended**:
  - Existing test `qdrant` service keeps its host port 6334 / test volume / test network behavior; gains a healthcheck
    (mirroring the production hardening) so the server can depend on it healthily.
  - New `mcp-server` test service: built from the project Dockerfile, wired to the test Qdrant, the mock embedding
    provider configuration (as `.env.test` uses today), a fixture workspace volume, and an isolated test SQLite path;
    host port 8081 to avoid colliding with a running production stack.
- **Fixture workspace**: `tests/fixtures/mcp_workspace/` with a small deterministic document for ingest/search.
- **`scripts/start_test_services.sh` updated**: brings up the extended stack and waits for both services' health so
  the Python suite and MCP verification share one environment.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the test-stack requirement.

## Dependencies

- Requires: `revise-dockerfile-for-mcp` (the image).

**Depended on by:** `add-mcp-e2e-smoke`, `add-mcp-readme-feature-docs`.

## Impact

**Code**: `docker-compose.test.yml` (extended), `tests/fixtures/mcp_workspace/` (new),
`scripts/start_test_services.sh` (updated).

**Out of scope**: the e2e smoke script (separate proposal); Rust-side hermetic tests (tool proposals cover those).

## Non-goals

- Load/performance testing of the MCP server (existing performance markers remain Python-side).
- A second Qdrant instance (the existing test instance is reused).
