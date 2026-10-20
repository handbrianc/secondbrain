# MCP End-to-End Smoke — Proposal

## Why

The Rust integration tests prove tool behavior against stub CLIs; the compose stacks prove the wiring exists. What
neither proves is the real chain: MCP client → HTTP(S) → Rust server → **real Python CLI** → mock embeddings → test
Qdrant. This proposal delivers the verification harness as its own unit: a parameterized smoke script that drives a
real MCP client flow over HTTP(S) against either compose stack (test or prod) — health, tool discovery, ingestion of
a fixture document, search finding it, and (when an LLM is configured) a chat turn.

## What Changes

- **`scripts/mcp_e2e_smoke.sh --stack <test|prod>`**: compose file selection, bring-up, wait-for-health, then
  JSON-RPC over HTTP(S): `tools/list` → `ingest_documents` (fixture document) → `search` (assert fixture content in
  results) → `chat_send` (gated: skipped with an explicit warning when no test LLM is configured) → teardown on exit
  (including failure).

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-deployment** — adds the end-to-end smoke requirement.

## Dependencies

- Requires: the tool proposals (`add-mcp-search-tool`, `add-mcp-ingest-tool`, `add-mcp-ingest-path-confinement`,
  `add-mcp-chat-send-tool`), `revise-compose-production-stack`, `revise-compose-test-stack`.

**Depended on by:** `add-mcp-readme-feature-docs` (the documented verification entry point).

## Impact

**Code**: `scripts/mcp_e2e_smoke.sh` (new).

**Out of scope**: CI wiring for the smoke (verification plumbing stays bundled with the Docker proposal's smoke
workflow; extending it to compose stacks is a follow-up if desired); LLM-judge answer quality (qualitative markers
remain Python-side).

## Non-goals

- Load/performance assertions in the smoke (functional correctness only).
- TLS-mode smoke variation (HTTPS exercise documented; the smoke defaults to the stack's configured scheme).
