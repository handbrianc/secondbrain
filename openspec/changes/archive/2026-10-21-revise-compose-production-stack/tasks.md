# Revise Compose Production Stack — Tasks

## 1. Compose service

- [x] 1.1 In `docker-compose.yml`: add the `mcp-server` service — `build: .`, `ports: ["8080:8080"]`, `env_file: .env.docker`, volumes (workspace read-only at `SECONDBRAIN_MCP_WORKSPACE_ROOT`; `secondbrain-sqlite` named volume at the SQLite path; optional `./certs` read-only at `/certs`), `depends_on: qdrant: condition: service_healthy`, `restart: unless-stopped`
- [x] 1.2 Rewrite/expand `.env.docker`: `SECONDBRAIN_MCP_*` block (bind, TLS enabled/cert/key commented examples, auth token commented, workspace root, subprocess timeout, log level) + integration block (`SECONDBRAIN_QDRANT_URL=http://qdrant:6333` default with external-URL comment, collection/API key, `SECONDBRAIN_EMBEDDING_*` external-API placeholders, `SECONDBRAIN_LLM_PROVIDER`/`SECONDBRAIN_OPENAI_BASE_URL`/`SECONDBRAIN_OPENAI_API_KEY`/`SECONDBRAIN_LLM_MODEL` placeholders, `SECONDBRAIN_SQLITE_PATH` inside the persisted volume) — every entry documented inline
  *Amended 2026-10-21 (deployment decision): values were committed as this
  deployment's documented working entries, then redacted to safe placeholders
  the same day after the push exposed them; the `.env.docker` header describes
  the placeholder contract and the real values live in an uncommitted local
  copy. The missing `SECONDBRAIN_ANTHROPIC_API_KEY` slot was added as a
  commented line, matching the delta requirement's variable list.*

## 2. Tests proving the unit of work

- [x] 2.1 `docker compose -f docker-compose.yml config --quiet` passes
- [x] 2.2 Bring-up check: `docker compose up -d` → `mcp-server` healthy (image healthcheck), `/healthz` reachable on 8080; teardown
- [x] 2.3 Full end-to-end automation is `add-mcp-e2e-smoke`'s unit
  *Done (2026-10-21): the e2e prod run passed — see add-mcp-e2e-smoke task 2.2
  (health → tools/list → ingest with real embeddings → search assert →
  chat_send with a live LLM answer, then teardown + immediate restore, live
  store verified intact at the 12,593-point baseline).*
