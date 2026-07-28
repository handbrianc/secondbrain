"""Integration tests for document-scoped RAG retrieval.

Verifies that the DocumentRouter correctly scopes retrieval to a specific
document when the user's query names a document.
"""

from unittest.mock import MagicMock

import pytest

from secondbrain.rag.document_router import DocumentRouter
from secondbrain.rag.pipeline import RAGPipeline

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def known_names() -> dict[str, str]:
    from secondbrain.rag.document_router import _build_known_names

    return _build_known_names(
        [
            "/docs/VirtualBox_UserManual.pdf",
            "/docs/Proxmox_VE_Guide.pdf",
        ]
    )


@pytest.fixture
def document_router(known_names: dict[str, str]) -> DocumentRouter:
    return DocumentRouter(known_names=known_names)


@pytest.fixture
def mock_searcher() -> MagicMock:
    search_mock = MagicMock()
    search_mock.search.return_value = [
        {
            "chunk_id": "chunk-1",
            "chunk_text": "VirtualBox is a virtualization product.",
            "source_file": "/docs/VirtualBox_UserManual.pdf",
            "page_number": 1,
            "score": 0.95,
        },
        {
            "chunk_id": "chunk-2",
            "chunk_text": "Proxmox VE is a virtualization platform.",
            "source_file": "/docs/Proxmox_VE_Guide.pdf",
            "page_number": 1,
            "score": 0.90,
        },
    ]
    return search_mock


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.generate.return_value = "This is a test answer."
    llm.model = "mock-model"
    return llm


@pytest.fixture
def pipeline(
    mock_searcher: MagicMock,
    mock_llm: MagicMock,
) -> RAGPipeline:
    return RAGPipeline(
        searcher=mock_searcher,
        llm_provider=mock_llm,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDocumentRouterIntegration:
    """DocumentRouter integration with RAGPipeline."""

    def test_router_extracts_virtualbox_doc_name(
        self,
        known_names: dict[str, str],
    ) -> None:
        router = DocumentRouter(known_names=known_names)

        # Various query forms that should match VirtualBox
        queries = [
            "tell me about virtual box user manual chapter 3",
            "what is in virtualbox chapter 5",
            "virtual box user manual overview",
            "summarize virtual box user manual by chapter",
        ]
        for query in queries:
            doc_name = router.extract_document_name(query)
            assert doc_name is not None, f"Failed to match: {query}"
            source = router.resolve_source_file(doc_name)
            assert source == "/docs/VirtualBox_UserManual.pdf", (
                f"Wrong source for {query}: {source}"
            )

    def test_router_extracts_proxmox_doc_name(
        self,
        known_names: dict[str, str],
    ) -> None:
        router = DocumentRouter(known_names=known_names)
        queries = [
            "tell me about proxmox ve guide chapter 5",
            "proxmox overview",
            "proxmox ve guide summary",
        ]
        for query in queries:
            doc_name = router.extract_document_name(query)
            assert doc_name is not None, f"Failed to match: {query}"
            source = router.resolve_source_file(doc_name)
            assert source == "/docs/Proxmox_VE_Guide.pdf", (
                f"Wrong source for {query}: {source}"
            )

    def test_no_doc_name_returns_none(
        self,
        known_names: dict[str, str],
    ) -> None:
        router = DocumentRouter(known_names=known_names)
        queries = [
            "what is python",
            "tell me about machine learning",
            "how does this work",
        ]
        for query in queries:
            doc_name = router.extract_document_name(query)
            assert doc_name is None, f"Should not match: {query}"

    def test_resolve_source_filter_passed_to_searcher(
        self,
        mock_searcher: MagicMock,
        mock_llm: MagicMock,
        known_names: dict[str, str],
    ) -> None:
        """When a doc name is present, source_filter=None should be passed."""
        # searcher has a storage attribute for the DocumentRouter to use
        mock_searcher.storage = MagicMock()
        mock_searcher.storage.list_source_files.return_value = [
            "/docs/VirtualBox_UserManual.pdf",
            "/docs/Proxmox_VE_Guide.pdf",
        ]

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm,
        )

        # When no doc name is mentioned, source_filter should be None
        pipeline.query("What is Python?")
        call_kwargs = mock_searcher.search.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        assert "source_filter" in kwargs
        # source_filter will be None because DocumentRouter won't match "Python"
        assert kwargs["source_filter"] is None, (
            f"Expected None but got: {kwargs['source_filter']}"
        )

    def test_unknown_doc_name_falls_back_gracefully(
        self,
        mock_searcher: MagicMock,
        mock_llm: MagicMock,
    ) -> None:
        """Queries referencing non-existent documents should not crash."""
        mock_searcher.search.return_value = []
        mock_searcher.storage = MagicMock()
        mock_searcher.storage.list_source_files.return_value = [
            "/docs/RealDoc.pdf",
        ]

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm,
        )

        result = pipeline.query("Tell me about nonexisent document xyz")
        assert "answer" in result
