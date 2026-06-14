"""Tests for search module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from secondbrain.search import Searcher


class TestSearcher:
    """Tests for Searcher class."""

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_init_default(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test initialization with defaults."""
        searcher = Searcher()
        assert searcher.verbose is False

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_basic(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test basic search."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = [
            {"chunk_id": "1", "source_file": "test.pdf", "score": 0.9},
            {"chunk_id": "2", "source_file": "test2.pdf", "score": 0.8},
        ]
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("test query")
        assert len(results) == 2
        mock_embed.generate.assert_called_once_with("test query")
        mock_storage.search.assert_called_once()

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_top_k(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search with custom top_k."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query", top_k=10)
        mock_storage.search.assert_called_once()
        call_args = mock_storage.search.call_args
        assert call_args.kwargs["top_k"] == 10

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_source_filter(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search with source filter."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query", source_filter="test.pdf")
        call_args = mock_storage.search.call_args
        assert call_args.kwargs["source_filter"] == "test.pdf"

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_file_type_filter(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search with file type filter."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query", file_type_filter="pdf")
        call_args = mock_storage.search.call_args
        assert call_args.kwargs["file_type_filter"] == "pdf"

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_sentence_transformers_unavailable(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search raises when SentenceTransformers is unavailable."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = False
        mock_create_from_config.return_value = mock_embed

        searcher = Searcher()
        try:
            searcher.search("test query")
        except RuntimeError as e:
            assert "Cannot connect to SentenceTransformers service" in str(e)

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_mongodb_unavailable(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search raises when MongoDB is unavailable."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        try:
            searcher.search("test query")
        except RuntimeError as e:
            assert "Cannot connect to MongoDB" in str(e)


class TestSemanticSearchSpecRequirements:
    """Tests for semantic search specification requirements."""

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_uses_cosine_similarity(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search uses cosine similarity (spec: cosine similarity search)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query")

        # Verify search was called
        mock_storage.search.assert_called_once()

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_default_top_k(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test default top-k is 5 (spec: default: 5)."""
        from secondbrain.config import get_config

        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        config = get_config()

        searcher = Searcher()
        searcher.search("test query")

        call_args = mock_storage.search.call_args
        assert call_args.kwargs["top_k"] == config.default_top_k

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_score(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search results include score (spec: score 0-1)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = [
            {
                "chunk_id": "1",
                "source_file": "test.pdf",
                "chunk_text": "Sample text",
                "page_number": 1,
                "score": 0.95,
            }
        ]
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("test query")

        assert len(results) == 1
        assert "score" in results[0]
        assert 0 <= results[0]["score"] <= 1

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_chunk_text(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search results include chunk_text (spec: chunk_text)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = [
            {
                "chunk_id": "1",
                "source_file": "test.pdf",
                "chunk_text": "The quick brown fox jumps over the lazy dog",
                "page_number": 1,
                "score": 0.9,
            }
        ]
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("test query")

        assert "chunk_text" in results[0]

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_source_file(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search results include source_file (spec: source_file)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = [
            {
                "chunk_id": "1",
                "source_file": "/path/to/document.pdf",
                "chunk_text": "Sample",
                "page_number": 1,
                "score": 0.9,
            }
        ]
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("test query")

        assert "source_file" in results[0]

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_page_number(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search results include page_number (spec: page_number if available)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = [
            {
                "chunk_id": "1",
                "source_file": "test.pdf",
                "chunk_text": "Sample",
                "page_number": 5,
                "score": 0.9,
            }
        ]
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("test query")

        assert "page_number" in results[0]
        assert results[0]["page_number"] == 5

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_empty_results(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search with empty results (spec: empty list)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []  # Empty results
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("test query")

        assert results == []

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_generates_embedding_via_sentence_transformers(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search generates embedding via SentenceTransformers (spec: uses same model as ingestion)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query")

        # Verify embedding was generated
        mock_embed.generate.assert_called_once_with("test query")

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_uses_vector_index(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search uses vector index (spec: MongoDB vector search index)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query")

        # Verify storage search was called
        mock_storage.search.assert_called_once()

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_span_attributes_source_filter(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search sets span attributes for source_filter (lines 160-165)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        # Create a mock span that captures set_attribute calls
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        with patch("secondbrain.search.trace_operation", return_value=mock_span):
            searcher = Searcher()
            searcher.search("test query", source_filter="test.pdf")

        # Verify span attributes were set
        assert mock_span.set_attribute.call_count >= 3
        # Check that source_filter attribute was set
        calls = mock_span.set_attribute.call_args_list
        source_filter_set = any(
            call[0][0] == "search.source_filter" for call in calls
        )
        assert source_filter_set

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_span_attributes_file_type_filter(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search sets span attributes for file_type_filter (lines 160-165)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        # Create a mock span that captures set_attribute calls
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)

        with patch("secondbrain.search.trace_operation", return_value=mock_span):
            searcher = Searcher()
            searcher.search("test query", file_type_filter="pdf")

        # Verify span attributes were set
        assert mock_span.set_attribute.call_count >= 3
        # Check that file_type_filter attribute was set
        calls = mock_span.set_attribute.call_args_list
        file_type_filter_set = any(
            call[0][0] == "search.file_type_filter" for call in calls
        )
        assert file_type_filter_set

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_span_attributes_embedding_dim(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test search sets span attributes for embedding_dim (lines 171-172)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        # Create mock spans for both trace_operation calls
        mock_span_embedding = MagicMock()
        mock_span_embedding.__enter__ = MagicMock(return_value=mock_span_embedding)
        mock_span_embedding.__exit__ = MagicMock(return_value=None)

        mock_span_storage = MagicMock()
        mock_span_storage.__enter__ = MagicMock(return_value=mock_span_storage)
        mock_span_storage.__exit__ = MagicMock(return_value=None)

        # Alternate between the two spans
        span_iter = iter([mock_span_embedding, mock_span_storage])
        with patch("secondbrain.search.trace_operation", side_effect=span_iter):
            searcher = Searcher()
            searcher.search("test query")

        # Check that embedding_dim attribute was set in storage span
        calls = mock_span_storage.set_attribute.call_args_list
        embedding_dim_set = any(
            call[0][0] == "search.embedding_dim" for call in calls
        )
        assert embedding_dim_set

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.asyncio
    async def test_search_async_basic(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test async search basic functionality (lines 192-217)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search_async = AsyncMock(
            return_value=[
                {"chunk_id": "1", "source_file": "test.pdf", "score": 0.9},
                {"chunk_id": "2", "source_file": "test2.pdf", "score": 0.8},
            ]
        )
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = await searcher.search_async("test query")

        assert len(results) == 2
        assert results[0]["chunk_id"] == "1"
        assert results[1]["chunk_id"] == "2"

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.asyncio
    async def test_search_async_with_top_k(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test async search with custom top_k (lines 192-217)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search_async = AsyncMock(return_value=[])
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        await searcher.search_async("test query", top_k=10)

        mock_storage.search_async.assert_called_once()
        call_args = mock_storage.search_async.call_args
        assert call_args.kwargs["top_k"] == 10

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.asyncio
    async def test_search_async_with_source_filter(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test async search with source_filter (lines 192-217)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search_async = AsyncMock(return_value=[])
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        await searcher.search_async("test query", source_filter="test.pdf")

        mock_storage.search_async.assert_called_once()
        call_args = mock_storage.search_async.call_args
        assert call_args.kwargs["source_filter"] == "test.pdf"

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.asyncio
    async def test_search_async_with_file_type_filter(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test async search with file_type_filter (lines 192-217)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search_async = AsyncMock(return_value=[])
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        await searcher.search_async("test query", file_type_filter="pdf")

        mock_storage.search_async.assert_called_once()
        call_args = mock_storage.search_async.call_args
        assert call_args.kwargs["file_type_filter"] == "pdf"

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.asyncio
    async def test_search_async_span_attributes(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test async search sets span attributes (lines 192-217)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search_async = AsyncMock(return_value=[])
        mock_storage_class.return_value = mock_storage

        # Create mock spans for both trace_operation calls
        mock_span_embedding = MagicMock()
        mock_span_embedding.__enter__ = MagicMock(return_value=mock_span_embedding)
        mock_span_embedding.__exit__ = MagicMock(return_value=None)

        mock_span_storage = MagicMock()
        mock_span_storage.__enter__ = MagicMock(return_value=mock_span_storage)
        mock_span_storage.__exit__ = MagicMock(return_value=None)

        # Alternate between the two spans
        span_iter = iter([mock_span_embedding, mock_span_storage])
        with patch("secondbrain.search.trace_operation", side_effect=span_iter):
            searcher = Searcher()
            await searcher.search_async("test query")

        # Verify span attributes were set in embedding span
        embedding_calls = mock_span_embedding.set_attribute.call_args_list
        assert any(call[0][0] == "search.query_length" for call in embedding_calls)
        assert any(call[0][0] == "search.top_k" for call in embedding_calls)

        # Verify span attributes were set in storage span
        storage_calls = mock_span_storage.set_attribute.call_args_list
        assert any(call[0][0] == "search.top_k" for call in storage_calls)
        assert any(call[0][0] == "search.embedding_dim" for call in storage_calls)

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.asyncio
    async def test_search_async_empty_results(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test async search returns empty list when no results (lines 192-217)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search_async = AsyncMock(return_value=[])
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = await searcher.search_async("test query")

        assert results == []
        assert isinstance(results, list)

    @patch("secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config")
    @patch("secondbrain.search.VectorStorage")
    @pytest.mark.asyncio
    async def test_search_async_connection_error(
        self, mock_storage_class: MagicMock, mock_create_from_config: MagicMock
    ) -> None:
        """Test async search raises RuntimeError on connection failure (lines 192-217)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_create_from_config.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()

        with pytest.raises(RuntimeError, match="Cannot connect to MongoDB"):
            await searcher.search_async("test query")