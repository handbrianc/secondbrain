# Harden Compose Qdrant Service — Proposal

## Why

The production compose stack's `qdrant` service currently publishes its port to the host with no healthcheck. Before
the MCP server can become the stack's primary service depending on a *healthy* Qdrant
(`depends_on: condition: service_healthy` requires a healthcheck), the bundled vector DB must become a managed
dependency: healthchecked, persistent, and internal-only by default. This is its own unit of work — an independently
rejectable change to an existing service (operators could prefer the status quo) — and it must land before the
server-primary stack revision.

## What Changes

- **`docker-compose.yml` `qdrant` service**: explicit `healthcheck` (Qdrant's own health endpoint), named persistent
  volume (pinned), host port publish removed by default (kept as a commented block for local CLI access), dedicated
  bridge network pinned.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the bundled Qdrant hygiene requirement.

## Dependencies

- None (change to the existing compose service; no image dependency).

**Depended on by:** `revise-compose-production-stack` (its `depends_on: service_healthy` needs this healthcheck),
`revise-compose-test-stack` (mirrors the pattern on the test stack).

## Impact

**Code**: `docker-compose.yml` (qdrant service block only).

**Behavior change for existing users**: `localhost:6333` stops being published by default; local CLI users re-enable
the commented port block or use the in-network URL (`http://qdrant:6333`) once the stack revision lands. Flagged in
docs by the documentation proposals.

**Out of scope**: the MCP server service (next proposal), test stack (later proposal).

## Non-goals

- Qdrant authentication/API key enablement (operators' choice, env-based).
- Backup/restore automation for the vector volume.
