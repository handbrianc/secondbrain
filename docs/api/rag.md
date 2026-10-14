# RAG

Retrieval-augmented generation: the `RAGPipeline` rewrites follow-up queries,
retrieves relevant chunks via the [`Searcher`](search.md), formats context,
and generates grounded answers through a pluggable LLM provider
(OpenAI-compatible or Anthropic).

::: secondbrain.rag
