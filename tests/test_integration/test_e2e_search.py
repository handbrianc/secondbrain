"""Integration tests for semantic search with MongoDB."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.search import Searcher


class TestSearchE2E:
    """Test suite for end-to-end search integration."""

    @pytest.mark.e2e
    @pytest.mark.integration
    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.slow
    def test_search_e2e(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test that end-to-end search returns expected results."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.5, 0.3, 0.8]
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = [
            {
                "chunk_id": "chunk-001",
                "source_file": "test_document.pdf",
                "page_number": 1,
                "chunk_text": "This is a sample result from the document.",
                "score": 0.95,
            },
            {
                "chunk_id": "chunk-002",
                "source_file": "test_document.pdf",
                "page_number": 2,
                "chunk_text": "Another relevant result found in the search.",
                "score": 0.87,
            },
        ]
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("sample query")

        assert len(results) == 2
        assert results[0]["score"] == 0.95
        assert results[0]["source_file"] == "test_document.pdf"

        mock_embed.generate.assert_called_once_with("sample query")
        import os

        from secondbrain.config import get_config

        os.environ["SECONDBRAIN_DEFAULT_TOP_K"] = "5"
        config = get_config()
        expected_top_k = config.default_top_k

        mock_storage.search.assert_called_once_with(
            embedding=[0.5, 0.3, 0.8],
            top_k=expected_top_k,
            source_filter=None,
            file_type_filter=None,
        )

    @pytest.mark.e2e
    @pytest.mark.integration
    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.slow
    def test_search_with_filters(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test that search applies filters correctly."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.4, 0.6, 0.2]
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = [
            {
                "chunk_id": "chunk-filtered",
                "source_file": "specific_doc.pdf",
                "page_number": 5,
                "chunk_text": "Filtered result",
                "score": 0.78,
            }
        ]
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search(
            "filtered query",
            top_k=10,
            source_filter="specific_doc.pdf",
            file_type_filter="pdf",
        )

        assert len(results) == 1
        assert results[0]["source_file"] == "specific_doc.pdf"

        mock_storage.search.assert_called_once_with(
            embedding=[0.4, 0.6, 0.2],
            top_k=10,
            source_filter="specific_doc.pdf",
            file_type_filter="pdf",
        )


class TestSearchIntegration:
    """Test suite for search integration scenarios."""

    @pytest.mark.e2e
    @pytest.mark.integration
    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.slow
    def test_search_with_custom_top_k(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test that search with custom top_k parameter works correctly."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 768
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("query", top_k=20)

        call_args = mock_storage.search.call_args
        assert call_args.kwargs["top_k"] == 20

    @pytest.mark.e2e
    @pytest.mark.integration
    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.slow
    def test_search_no_results(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test that search returns empty list when no results found."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.5] * 768
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("no match query")

        assert results == []

    @pytest.mark.e2e
    @pytest.mark.integration
    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.slow
    def test_search_empty_embed_result(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test that search handles empty embedding results."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = []
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("empty embedding test")

        assert results == []
