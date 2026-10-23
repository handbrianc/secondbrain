"""Shared instance-attribute declarations for the RAG pipeline mixins.

``RAGPipeline.__init__`` is the sole place these attributes are assigned, but the
cohesive helper mixins (``_mixins.py``) also reference them. Declaring them once
here lets mypy resolve ``self._searcher``, ``self._config`` etc. inside the
mixins without an import cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from secondbrain.config import Config as _Config
    from secondbrain.conversation import ConversationSession as _ConversationSession
    from secondbrain.conversation import QueryRewriter as _QueryRewriter
    from secondbrain.document.scoped_retriever import (
        ScopedRetriever as _ScopedRetriever,
    )
    from secondbrain.rag.document_router import DocumentRouter as _DocumentRouter
    from secondbrain.rag.intent_parser import (
        StructuralIntentParser as _StructuralIntentParser,
    )
    from secondbrain.rag.interfaces import LocalLLMProvider as _LocalLLMProvider
    from secondbrain.rag.interfaces import StreamingCallback as _StreamingCallback
    from secondbrain.rag.security_filter import SecurityFilter as _SecurityFilter
    from secondbrain.search import Searcher as _Searcher


class _RAGPipelineState:
    """Declares instance attributes shared across the RAG pipeline mixins."""

    if TYPE_CHECKING:  # pragma: no cover
        _searcher: _Searcher
        _scoper: _ScopedRetriever
        _llm_provider: _LocalLLMProvider
        _rewriter: _QueryRewriter | None
        _top_k: int
        _context_window: int
        _config: _Config
        _intent_parser: _StructuralIntentParser
        _security_filter: _SecurityFilter
        _on_chunk: _StreamingCallback | None
        _document_router: _DocumentRouter | None

        # Cross-referenced helpers defined on other mixins (visible once composed).
        def _format_context(
            self,
            chunks: list[dict[str, Any]],
            max_chars: int | None = None,
        ) -> str: ...

        def _build_prompt(
            self,
            query: str,
            context: str,
            conversation_history: list[dict[str, Any]] | None = None,
        ) -> str: ...

        def _format_history(self, history: list[dict[str, Any]]) -> str: ...

        @staticmethod
        def _infer_section_label(
            chunk_text: str, chunk_role: str | None
        ) -> str | None: ...

        def _has_relevant_chunks(
            self,
            chunks: list[dict[str, Any]],
            threshold: float | None = None,
        ) -> bool: ...

        def _relevance_gate_threshold(
            self, source_filter: str | None
        ) -> float | None: ...

        def _scoped_search_query(self, query: str) -> str: ...

        @staticmethod
        def _display_chapter_title(title: str) -> str: ...

        def _dedupe_by_text_hash(
            self, chunks: list[dict[str, Any]]
        ) -> list[dict[str, Any]]: ...

        def _union_opener_chunks(
            self,
            query: str,
            chunks: list[dict[str, Any]],
            source_filter: str | None,
            *,
            top_k: int | None = None,
        ) -> list[dict[str, Any]]: ...

        def _apply_heading_diversity(
            self,
            chunks: list[dict[str, Any]],
            max_headings: int | None = None,
        ) -> list[dict[str, Any]]: ...

        def _handle_no_results(
            self,
            query: str,
            allow_llm_fallback: bool = True,
            conversation_history: list[dict[str, Any]] | None = None,
        ) -> str: ...

        async def _handle_no_results_async(
            self,
            query: str,
            allow_llm_fallback: bool = True,
            conversation_history: list[dict[str, Any]] | None = None,
        ) -> str: ...

        def _generate(self, prompt: str) -> str: ...

        async def _agenerate(self, prompt: str) -> str: ...

        def _generate_guarded(
            self,
            prompt: str,
            *,
            temperature: float | None = None,
            max_tokens: int | None = None,
        ) -> str: ...

        def _stream_generate(
            self, prompt: str, prefix: str = ""
        ) -> tuple[str, bool]: ...

        def _iterative_query(
            self,
            query: str,
            top_k: int,
            show_sources: bool,
            source_filter: str | None = None,
        ) -> dict[str, Any]: ...

        def _answer_page_query(self, query: str) -> dict[str, Any] | None: ...

        async def _answer_page_query_async(
            self, query: str
        ) -> dict[str, Any] | None: ...

        def _create_error_response(
            self,
            error: str,
            query: str,
        ) -> dict[str, Any]: ...

        def _grounded_context_retry(
            self,
            query: str,
            conversation_history: list[dict[str, Any]] | None,
            top_k: int,
            show_sources: bool,
        ) -> dict[str, Any] | None: ...

        async def _grounded_context_retry_async(
            self,
            query: str,
            conversation_history: list[dict[str, Any]] | None,
            top_k: int,
            show_sources: bool,
        ) -> dict[str, Any] | None: ...

        def _list_sources_result(self, query: str) -> dict[str, Any]: ...

        def _resolve_source_filter(self, query: str) -> str | None: ...

        def _rewrite_query_with_history(
            self,
            query: str,
            session: _ConversationSession,
        ) -> str: ...

        def _save_turn(
            self,
            session: _ConversationSession,
            query: str,
            answer: str,
        ) -> None: ...

        # Anthology-aware chapter summarization
        # (add-anthology-aware-chapter-summarization).  Defined on
        # ``_StructureMixin`` / ``_FallbackMixin``, called from
        # ``_pipeline.py``.

        @staticmethod
        def _detect_anthology_parts(
            heading_chunks: list[dict[str, Any]],
            source: str,
        ) -> list[dict[str, Any]] | None: ...

        def _enrich_anthology_parts(
            self,
            parts: list[dict[str, Any]],
            body_chunks_by_page: dict[int, list[dict[str, Any]]],
            headings: list[dict[str, Any]],
            total_pages: int,
        ) -> list[dict[str, Any]] | None: ...

        def _chapter_range_gate(
            self,
            chapter_ranges_: dict[int, tuple[int, int]],
            evidence_pin_pg_: dict[int, int],
            src: str,
        ) -> bool: ...

        def _generate_anthology_summary(
            self, parts: list[dict[str, Any]]
        ) -> str: ...

        def _generate_whole_document_overview(
            self, chunks: list[dict[str, Any]]
        ) -> str: ...
