# RAG Pipeline Duplicate — Tasks

> **Note (2026-10-11):** Stub created during a 2026-10-11 archive-staleness pass. This change was a superseded
> duplicate of `openspec/changes/archive/add-conversational-rag` (its "ADDED Requirements (RAG Pipeline)"
> section); its `specs/rag-pipeline/spec.md:3-5` header already records the supersession. No implementation was
> performed under this change — the tasks below are marked complete **by supersession**, not by work done
> here: all seven rag-pipeline requirements are implemented and recorded under the conversational-rag change
> (`openspec/changes/archive/add-conversational-rag/specs/conversational-rag/spec.md`; code in
> `src/secondbrain/rag/`). The local-LLM defaults this spec describes (Ollama as default provider, `llama3.2`
> default model, `SECONDBRAIN_LLM_ENDPOINT`) were dropped in favor of OpenAI-compatible remote providers
> (`openai`/`anthropic`, default `gpt-4o-mini`, `openai_base_url` for self-hosted endpoints).

- [x] 1.1 RAG pipeline orchestration

  > Superseded — implemented under add-conversational-rag (RAG pipeline orchestration).

- [x] 1.2 Pluggable LLM provider

  > Superseded — implemented under add-conversational-rag (Pluggable LLM provider). The Ollama-default
  > provider scenario was dropped; shipped defaults are OpenAI-compatible remote providers.

- [x] 1.3 Context formatting for LLM

  > Superseded — implemented under add-conversational-rag (Context formatting for LLM).

- [x] 1.4 Retrieval integration

  > Superseded — implemented under add-conversational-rag (Retrieval integration).

- [x] 1.5 Answer generation

  > Superseded — implemented under add-conversational-rag (Answer generation). The "Handle ambiguous queries"
  > clarifying-question scenario was intentionally not implemented (see the 2026-10-11 note there).

- [x] 1.6 Performance monitoring

  > Superseded — implemented under add-conversational-rag (Performance monitoring).

- [x] 1.7 Async support

  > Superseded — implemented under add-conversational-rag (Async support; session storage is SQLite, not
  > MongoDB).
