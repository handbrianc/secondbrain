# MCP Docs Site Integration — Proposal

## Why

The README (see `add-mcp-readme-feature-docs`) documents the feature set next to the code, but the project's
documentation site is where users start — and `docs/developer-guide/docker.md` is currently inaccurate for the new
reality ("Docker primarily for Qdrant; the application runs natively"). This proposal delivers the site-integration
unit: an MkDocs MCP guide wired into the navigation, and the Docker guide corrected for the MCP-primary container.
Its verification is the strict docs build.

## What Changes

- **`docs/developer-guide/mcp.md`**: MkDocs page for client onboarding — pointing an MCP client at the server over
  HTTPS, compose quick start, tool examples, troubleshooting table (401 → token, TLS errors → cert paths, tool errors
  → CLI diagnostics).
- **`mkdocs.yml`**: nav entry for the new page.
- **`docs/developer-guide/docker.md`** updated: MCP server as the container's primary function, env-file
  configuration; the stale "application runs natively / Docker only for Qdrant" framing
  removed.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-documentation** — adds the docs-site integration requirements.

## Dependencies

- Requires: `add-mcp-readme-feature-docs` (the source of truth it links), the deployment proposals for accuracy
  (`revise-dockerfile-for-mcp`, `harden-compose-qdrant-service`, `revise-compose-production-stack`,
  `revise-compose-test-stack`, `add-mcp-e2e-smoke`).

**Depended on by:** nothing (terminal proposal of the series).

## Impact

**Code**: `docs/developer-guide/mcp.md` (new), `mkdocs.yml` (nav), `docs/developer-guide/docker.md` (update).

**Out of scope**: README content, architecture deep-dive, API reference generation (rustdoc covers the crate).

## Non-goals

- Publishing a standalone docs site or landing page for the MCP server.
- Documenting pre-existing CLI behavior beyond what the MCP tools consume.
