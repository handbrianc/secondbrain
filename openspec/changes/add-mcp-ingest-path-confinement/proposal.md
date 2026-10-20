# MCP Ingest Path Confinement — Proposal

## Why

`add-mcp-ingest-tool` exposes ingestion but resolves paths without validation: as delivered, a caller could ingest
any path the container can read. Because the server runs in a container where the CLI only sees a mounted workspace,
ingestion must be confined to `SECONDBRAIN_MCP_WORKSPACE_ROOT`. Confinement is its own unit of work — an
independently rejectable security policy (a deployment could choose to trust its callers) with its own failure modes
(traversal, symlink escapes) and its own tests — layered onto the ingest tool from the previous proposal.

## What Changes

- **Workspace confinement for `ingest_documents`**:
  - Canonicalize both the workspace root and the resolved target; require the target to lie within the root
    (`starts_with` on canonical paths).
  - Reject before any CLI subprocess starts: `..` traversal, absolute paths outside the root, and symlink escapes
    resolve to a path outside the root and are rejected.
  - Rejection errors describe the rule and name `SECONDBRAIN_MCP_WORKSPACE_ROOT`.
  - Valid relative/absolute-inside resolutions from the ingest tool keep working unchanged.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the workspace path confinement requirement.

## Dependencies

- Requires: `add-mcp-ingest-tool` (the tool being hardened).

**Depended on by:** `add-mcp-e2e-smoke`, `add-mcp-readme-feature-docs`.

## Impact

**Code**: `mcp-server/src/tools/ingest.rs` (path validation), new fixture + tests.

**Dependencies**: none beyond existing (canonicalization via `std::fs` — Linux containers only).

## Non-goals

- Read-only vs read-write workspace distinctions (the workspace is read-only to the CLI by compose mount; enforced at
  the mount, not in code).
- Confinement for other tools (only ingest takes filesystem paths; `search --source` is a value filter, not a file read).
- Allow-listing multiple roots (single workspace root, v1).
