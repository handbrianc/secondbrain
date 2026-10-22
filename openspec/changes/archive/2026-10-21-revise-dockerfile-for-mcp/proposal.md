# Revise Dockerfile for MCP — Proposal

## Why

The current Dockerfile only packages the Python CLI as a PyInstaller one-file binary — there is no service image. The
user requirement makes the MCP server the container's primary function while keeping the CLI tooling available for it
to drive. This proposal rebuilds the image as a multi-stage build: a Rust builder stage compiles `secondbrain-mcp`,
and a Python runtime stage installs the CLI as a wheel alongside the server binary. All `SECONDBRAIN_*` configuration
remains runtime-injectable so the image can integrate with an external LLM, an external embedding/vector model
endpoint, and a Qdrant instance of the operator's choosing.

## What Changes

- **Dockerfile rewritten** as multi-stage:
  - Stage 1 `mcp-builder` (`rust:1-slim`): builds the release binary from `mcp-server/` (`cargo build --release --locked`).
  - Stage 2 `runtime` (`python:3.14-slim`): installs the Python package (runtime deps only — `pip install .`, not dev
    extras), copies the `secondbrain-mcp` binary, sets `SECONDBRAIN_MCP_*` image defaults, `WORKDIR /data/workspace`,
    runs as a non-root `app` user, `EXPOSE 8080`, `HEALTHCHECK` against `/healthz`, `CMD ["secondbrain-mcp"]`.
  - Both `secondbrain-mcp` (default) and `secondbrain` (CLI) are on `PATH` — CLI tooling ships in the image.
- **Smoke script** `scripts/docker-smoke.sh`: builds the image, starts a container, asserts `/healthz`, asserts
  `tools/list` over the MCP endpoint, asserts `docker run --rm <image> secondbrain --help` exits 0, stops the container.
- **CI**: new `.github/workflows/docker-smoke.yml` running the smoke script on PRs touching `Dockerfile`,
  `mcp-server/**`, or `pyproject.toml`.
- The PyInstaller path is retired from the Dockerfile; host-side packaging (`scripts/build.sh`, `secondbrain.spec`)
  is untouched (its stale `pymongo`/`dotenv` hidden imports are pre-existing debt, noted for separate cleanup).

No Python source changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — new capability covering the MCP server's containerization (image, compose stacks, smoke).

## Dependencies

- Requires: `add-mcp-server-scaffold` (the crate), `add-mcp-server-runtime` (`/healthz`; benefits from the transport
  proposal for the `tools/list` smoke step).

**Depended on by:** `revise-compose-production-stack`, `revise-compose-test-stack`.

## Impact

**Code**: `Dockerfile` (rewritten), `scripts/docker-smoke.sh` (new), `.github/workflows/docker-smoke.yml` (new).

**Dependencies**: image size grows (Rust binary + Python runtime deps incl. document parsers); build time includes a
cargo release build (first build is slow; lockfile keeps it reproducible).

**Out of scope**: compose stack contents (next proposal), docs (final proposal).

## Non-goals

- Publishing images to a registry (local build + CI smoke only; registry push is a future proposal).
- Retiring `scripts/build.sh` / `secondbrain.spec` (host-side PyInstaller packaging stays as-is).
