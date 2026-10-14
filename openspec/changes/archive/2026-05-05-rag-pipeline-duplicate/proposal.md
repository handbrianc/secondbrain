# Proposal: RAG Pipeline (superseded duplicate)

> **Note (2026-10-11):** Stub created during a 2026-10-11 archive-staleness pass. This change was a superseded
> duplicate of `openspec/changes/archive/add-conversational-rag` (its "ADDED Requirements (RAG Pipeline)"
> section) — its `specs/rag-pipeline/spec.md` header already documents the supersession. No proposal was
> originally filed and no separate work happened under this change; this stub records that status. The stub is
> the only amendment made here — the historical spec text was not rewritten.

## Why

The same RAG pipeline requirements were drafted twice in parallel. The authoritative version lives under
`add-conversational-rag`; this change's spec remained as an unimplemented duplicate. Its local-LLM defaults
(Ollama as default provider, `llama3.2` default model, `SECONDBRAIN_LLM_ENDPOINT`) were dropped in favor of
OpenAI-compatible remote providers (`SECONDBRAIN_LLM_PROVIDER=openai`/`anthropic`, default model
`gpt-4o-mini`, `openai_base_url` for self-hosted endpoints).

## What Changes

- None. This change shipped nothing of its own; it is superseded by `add-conversational-rag`, where all seven
  rag-pipeline requirements were implemented (see its spec, "ADDED Requirements (RAG Pipeline)", and
  `src/secondbrain/rag/`).

## Impact

- No code impact.
- Archived for the record only; see `tasks.md` in this directory for the per-requirement supersession notes.
