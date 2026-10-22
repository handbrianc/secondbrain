# Revise Compose Test Stack — Tasks

## 1. Test stack

- [x] 1.1 In `docker-compose.test.yml`: add a healthcheck to the existing test `qdrant` (mirroring the production hardening; host port 6334 and test volume unchanged)
- [x] 1.2 Add the `mcp-server` test service: `build: .`, host port 8081, env: test Qdrant URL `http://qdrant:6333`, mock embedding settings mirroring `.env.test`, `SECONDBRAIN_SQLITE_PATH` on a test volume, `SECONDBRAIN_MCP_WORKSPACE_ROOT` on a fixture-workspace volume, image healthcheck; `depends_on` test qdrant healthy
- [x] 1.3 Create `tests/fixtures/mcp_workspace/` with a small deterministic text document for ingest/search assertions (committed, stable content)

## 2. Entry point coherence

- [x] 2.1 Update `scripts/start_test_services.sh`: compose up the extended test stack; wait for both qdrant and mcp-server health

## 3. Tests proving the unit of work

- [x] 3.1 `docker compose -f docker-compose.test.yml config --quiet` passes
- [x] 3.2 `docker compose -f docker-compose.test.yml up -d` → both services healthy; test qdrant still reachable on host port 6334
- [x] 3.3 Existing Python test-suite flow (`scripts/start_test_services.sh` + pytest against 6334) still works
