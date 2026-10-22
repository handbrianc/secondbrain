# Revise Dockerfile for MCP — Tasks

## 1. Image definition

- [x] 1.1 Rewrite `Dockerfile`:
  - Stage `mcp-builder` (`rust:1-slim`): copy `mcp-server/` (with `Cargo.lock`), `cargo build --release --locked`, output binary `secondbrain-mcp`
  - Stage `runtime` (`python:3.14-slim`): `pip install --no-cache-dir .` (runtime deps only — not the dev extras), copy the Rust binary to `/usr/local/bin/secondbrain-mcp`, create non-root `app` user, `WORKDIR /data/workspace`, `ENV` image defaults for `SECONDBRAIN_MCP_HTTP_BIND_ADDR=0.0.0.0:8080` / `SECONDBRAIN_MCP_WORKSPACE_ROOT=/data/workspace`, `EXPOSE 8080`, `HEALTHCHECK` hitting `http://127.0.0.1:8080/healthz` (python stdlib urllib one-liner), `USER app`, `CMD ["secondbrain-mcp"]`
- [x] 1.2 Add `.dockerignore` (`.git`, `mcp-server/target`, `tests`, `docs`, `.venv`, caches) so build context stays small and no secrets ship

## 2. Smoke verification

- [x] 2.1 Create `scripts/docker-smoke.sh`: `docker build` → run container (ephemeral port) → poll `/healthz` until healthy → POST `tools/list` expecting JSON → `docker run --rm <image> secondbrain --help` exit 0 → teardown with trap
- [x] 2.2 Non-root check in the smoke: `docker run --rm --entrypoint id <image>` shows the `app` user

## 3. CI

- [x] 3.1 Add `.github/workflows/docker-smoke.yml`: run `scripts/docker-smoke.sh` on PRs/pushes touching `Dockerfile`, `mcp-server/**`, `pyproject.toml` (single job, no registry push)
