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

        def _has_relevant_chunks(self, chunks: list[dict[str, Any]]) -> bool: ...

        def _handle_no_results(
            self,
            query: str,
            allow_llm_fallback: bool = True,
            conversation_history: list[dict[str, Any]] | None = None,
        ) -> str: ...
