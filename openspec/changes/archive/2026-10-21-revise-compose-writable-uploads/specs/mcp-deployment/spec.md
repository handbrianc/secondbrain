# MCP Deployment

## ADDED Requirements

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
