# Writable Upload Staging Mounts — Proposal

## Why

The compose stacks mount the ingest workspace read-only at the configured workspace root
(`revise-compose-production-stack`, `revise-compose-test-stack`) — a posture that served `ingest_documents` (a
pure reader) but breaks `add-mcp-upload-tool`, which must create the upload directory and write the submitted
bytes into it: `upload_document` fails with a storage error on a read-only filesystem. Making the whole
workspace writable would fix uploads but discard the deliberate hardening (the served corpus must stay
immutable), so the fix layers writability only where the upload tool needs it.

## What Changes

- **`docker-compose.yml` (`mcp-server`)**: the workspace stays `:ro`; `./workspace/uploads` is layered
  read-write at `/data/workspace/uploads` (the default `SECONDBRAIN_MCP_UPLOAD_DIR` inside the root).
- **`docker-compose.test.yml` (`mcp-server`)**: the same layering over the fixture workspace; the `uploads/`
  staging directory is committed in the fixtures so the host directory exists with usable ownership.
- **Image entrypoint** (`scripts/docker_entrypoint.sh`, wired in the `Dockerfile` with `gosu`): when the
  container starts as root, it creates and chowns the configured staging directory (resolved exactly like the
  server's config: default `uploads` anchored at `SECONDBRAIN_MCP_WORKSPACE_ROOT`) to the non-root runtime
  user, then re-execs the command as that user — a compose-auto-created (root-owned) host staging directory is
  healed at every start, and the server and CLI never run as root. Started as a non-root user
  (`docker run --user`, Kubernetes runAsNonRoot), it skips the handover.
- **No manual host setup**: the entrypoint's ownership handover makes a compose-auto-created (root-owned)
  staging directory work out of the box; the rootless exception (handover skipped — operator owns ownership) is
  documented in the README, the docker guide, and the MCP guide troubleshooting table; `.env.docker` gains
  commented `SECONDBRAIN_MCP_UPLOAD_*` entries.

No Python changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the writable upload staging requirement (layered read-write mount inside the
  read-only workspace, host-directory prerequisite, fixture-stack parity).

## Dependencies

- Requires: `revise-compose-production-stack` and `revise-compose-test-stack` (the stacks being revised),
  `add-mcp-upload-tool` (the write path being enabled).

**Depended on by:** none yet.

## Impact

**Code**: `Dockerfile` (gosu, entrypoint wiring, pre-created default staging dir),
`scripts/docker_entrypoint.sh`, `.dockerignore` (entrypoint exception — a wholesale `scripts` exclusion cannot
be re-included per-file), `docker-compose.yml`, `docker-compose.test.yml`, committed fixture directory
(`tests/fixtures/mcp_workspace/uploads/`), `mcp-server/README.md`, `docs/developer-guide/docker.md`,
`docs/developer-guide/mcp.md`, `.env.docker`.

## Non-goals

- Making the whole workspace writable (defeats the corpus-immutability hardening).
- A named volume for uploads (hides uploaded files from the host workspace; the bind mount keeps them
  inspectable and re-ingestable).
- Rootless deployments (`docker run --user`, Kubernetes runAsNonRoot): the entrypoint skips the handover there,
  so staging-directory ownership remains the operator's responsibility.
