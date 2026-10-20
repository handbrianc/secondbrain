# MCP End-to-End Smoke — Tasks

## 1. Smoke harness

- [x] 1.1 Create `scripts/mcp_e2e_smoke.sh` with `--stack <test|prod>` (compose file selection), up, wait-for-health loop, JSON-RPC driver (embedded Python one-shot via the image's runtime or `curl`+`jq` — pin the choice at implementation; no new dependencies beyond what exists), steps: `tools/list` → `ingest_documents` (`tests/fixtures/mcp_workspace` doc) → `search` (assert fixture content) → gated `chat_send` → teardown `trap`
- [x] 1.2 Chat gate: detect usable LLM config (e.g. `SECONDBRAIN_OPENAI_API_KEY` present in the test env); absent → warn and skip

## 2. Tests proving the unit of work

- [ ] 2.1 Run `scripts/mcp_e2e_smoke.sh --stack test` → full ingest+search cycle passes; chat step skips cleanly without LLM config
  *Verification 2026-10-15: smoke ran green through health, tools/list and the ingest summary step, but the full ingest+search cycle is blocked-by-environment — no OpenAI-compatible embedding endpoint exists (stack `SECONDBRAIN_EMBEDDING_*` commented out, no ollama/LM Studio/vLLM locally, no credentials; the CLI defaults to api.openai.com and the ingest summary reports `Successfully ingested 0 files / Failed: 1 files` with `Error code: 401 - invalid_api_key`, search then fails with the CLI's exit-1 httpx trace to api.openai.com). Chat-skip confirmed at the gate level (all LLM vars UNSET in the server env); the in-flight skip warning is unreachable because search fails first. Teardown ran. NOT checked off — blocked by missing embedding endpoint, not by a code defect.*
- [ ] 2.2 Run `scripts/mcp_e2e_smoke.sh --stack prod` → same flow passes against the production stack
  *Verification 2026-10-15: smoke ran green through health, tools/list, then is blocked-by-environment: the host `./workspace` bind mount ships empty (repo commits no workspace content), so ingest_documents fails with CLI exit 2 `Path '/data/workspace/sample-document.md' does not exist`; with a document present it would hit the same 401 invalid_api_key embedding gap as the test stack (no credentials exist anywhere). Teardown ran. NOT checked off — blocked by environment.*
- [x] 2.3 Failure path: kill the server mid-smoke → script exits non-zero and still tears the stack down
