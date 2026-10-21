# MCP End-to-End Smoke — Tasks

## 1. Smoke harness

- [x] 1.1 Create `scripts/mcp_e2e_smoke.sh` with `--stack <test|prod>` (compose file selection), up, wait-for-health loop, JSON-RPC driver (embedded Python one-shot via the image's runtime or `curl`+`jq` — pin the choice at implementation; no new dependencies beyond what exists), steps: `tools/list` → `ingest_documents` (`tests/fixtures/mcp_workspace` doc) → `search` (assert fixture content) → gated `chat_send` → teardown `trap`
  *Amended 2026-10-21 (from the prod-stack verification run, task 2.2): the
  driver also (a) follows the stack's `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS`
  (sends the first allowlisted host as the Host header — a 127.0.0.1 request
  is otherwise rejected with 403, as /healthz is not gated), (b) normalizes
  JSON-escaped tool-result payloads before the chat assertions, and (c) takes
  an optional `SMOKE_PROJECT_ROOT` override to drive another checkout's stack
  (used to target the deployed production checkout from this worktree). No
  new dependencies; all additions follow the script's existing
  detect-from-stack-env pattern.*
- [x] 1.2 Chat gate: detect usable LLM config (e.g. `SECONDBRAIN_OPENAI_API_KEY` present in the test env); absent → warn and skip

## 2. Tests proving the unit of work

- [x] 2.1 Run `scripts/mcp_e2e_smoke.sh --stack test` → full ingest+search cycle passes; chat step skips cleanly without LLM config
  *Verification 2026-10-15: smoke ran green through health, tools/list and the ingest summary step, but the full ingest+search cycle is blocked-by-environment — no OpenAI-compatible embedding endpoint exists (stack `SECONDBRAIN_EMBEDDING_*` commented out, no ollama/LM Studio/vLLM locally, no credentials; the CLI defaults to api.openai.com and the ingest summary reports `Successfully ingested 0 files / Failed: 1 files` with `Error code: 401 - invalid_api_key`, search then fails with the CLI's exit-1 httpx trace to api.openai.com). Chat-skip confirmed at the gate level (all LLM vars UNSET in the server env); the in-flight skip warning is unreachable because search fails first. Teardown ran. NOT checked off — blocked by missing embedding endpoint, not by a code defect.*
  Done (2026-10-21, blocker resolved): the deployment's embedding endpoint
  (litellm proxy, embeddinggemma-300m.f16, 768 dims — same entries as
  .env.docker) was activated in `docker-compose.test.yml` and the smoke was
  re-run from the worktree: image built, stack healthy, tools/list OK,
  `ingest_documents` returned the CLI success summary (real embeddings through
  the endpoint), `search` returned fixture chunks, and the chat step skipped
  cleanly at the gate (no LLM config in the test stack). Teardown ran; named
  volumes kept. Full cycle green. (The endpoint's real host/key were redacted
  from the committed file the same day, after the push exposed them — fill
  SECONDBRAIN_EMBEDDING_* locally to reproduce.)
- [x] 2.2 Run `scripts/mcp_e2e_smoke.sh --stack prod` → same flow passes against the production stack
  *Verification 2026-10-15: smoke ran green through health, tools/list, then is blocked-by-environment: the host `./workspace` bind mount ships empty (repo commits no workspace content), so ingest_documents fails with CLI exit 2 `Path '/data/workspace/sample-document.md' does not exist`; with a document present it would hit the same 401 invalid_api_key embedding gap as the test stack (no credentials exist anywhere). Teardown ran. NOT checked off — blocked by environment.*
  Done (2026-10-21, blockers resolved): fixture staged on the host
  `./workspace` root (read-only bind by design — staged with a throwaway
  container, removed after); stack env carries the deployment's embedding
  endpoint. Full cycle green: health → tools/list → ingest_documents (real
  embeddings) → search returned the fixture chunks → chat_send ran with the
  configured LLM and returned a non-empty answer bound to a session id →
  teardown, immediate `up -d` restore (healthz 200). The two environment
  interactions the run surfaced were closed in the script itself:
  (1) the deployment's `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` rejects
  `Host: 127.0.0.1` with 403 — the smoke now detects the allowlist from the
  stack env and sends the first allowlisted host as the Host header
  (mirroring its TLS detection; /healthz is not gated); (2) tools/call
  results are wrapped as JSON-escaped strings inside content[].text, so the
  chat assertions normalize escapes before matching. Store side effects
  cleaned: the 6 ingested chunks deleted via `secondbrain delete --source
  /data/workspace/sample-document.md -y`; live collection back to the exact
  12,593-point baseline, status green; chat_send left two smoke sessions in
  the prod SQLite store (harmless history). The script gained a documented
  SMOKE_PROJECT_ROOT override so this worktree's driver can target the
  deployed checkout's compose project.
- [x] 2.3 Failure path: kill the server mid-smoke → script exits non-zero and still tears the stack down
