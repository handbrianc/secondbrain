"""Tests for search module."""

from unittest.mock import MagicMock, patch

from secondbrain.search import Searcher


class TestSearcher:
    """Tests for Searcher class."""

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_init_default(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test initialization with defaults."""
        searcher = Searcher()
        assert searcher.verbose is False

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_basic(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test basic search."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

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

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_top_k(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search with custom top_k."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query", top_k=10)
        mock_storage.search.assert_called_once()
        call_args = mock_storage.search.call_args
        assert call_args.kwargs["top_k"] == 10

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_source_filter(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search with source filter."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query", source_filter="test.pdf")
        call_args = mock_storage.search.call_args
        assert call_args.kwargs["source_filter"] == "test.pdf"

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_with_file_type_filter(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search with file type filter."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query", file_type_filter="pdf")
        call_args = mock_storage.search.call_args
        assert call_args.kwargs["file_type_filter"] == "pdf"

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_ollama_unavailable(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search raises when Ollama is unavailable."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = False
        mock_embed_class.return_value = mock_embed

        searcher = Searcher()
        try:
            searcher.search("test query")
        except RuntimeError as e:
            assert "Cannot connect to Ollama service" in str(e)

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_mongodb_unavailable(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search raises when MongoDB is unavailable."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        try:
            searcher.search("test query")
        except RuntimeError as e:
            assert "Cannot connect to MongoDB" in str(e)
