"""RAG pipeline for orchestrating retrieval and generation.

This module provides the RAGPipeline class that orchestrates the complete
Retrieval-Augmented Generation workflow for conversational Q&A.

The implementation is decomposed across cohesive sibling modules
(``_pipeline``, ``_orchestration``, and the helper-mixin modules); this
package ``__init__`` stays the thin public facade.
"""

from secondbrain.rag.pipeline._constants import (
    filter_chapters_by_target,
    strip_document_filenames,
)
from secondbrain.rag.pipeline._pipeline import RAGPipeline

__all__ = ["RAGPipeline", "filter_chapters_by_target"]
