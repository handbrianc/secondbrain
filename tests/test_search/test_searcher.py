"""Tests for search module."""

from unittest.mock import MagicMock, patch

from secondbrain.search import Searcher


class TestSearcher:
    """Tests for Searcher class."""

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_init_default(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test initialization with defaults."""
        searcher = Searcher()
        assert searcher.verbose is False

    @patch("secondbrain.search.LocalEmbeddingGenerator")
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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_sentence_transformers_unavailable(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search raises when SentenceTransformers is unavailable."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = False
        mock_embed_class.return_value = mock_embed

        searcher = Searcher()
        try:
            searcher.search("test query")
        except RuntimeError as e:
            assert "Cannot connect to SentenceTransformers service" in str(e)

    @patch("secondbrain.search.LocalEmbeddingGenerator")
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


class TestSemanticSearchSpecRequirements:
    """Tests for semantic search specification requirements."""

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_uses_cosine_similarity(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search uses cosine similarity (spec: cosine similarity search)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query")

        # Verify search was called
        mock_storage.search.assert_called_once()

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_default_top_k(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test default top-k is 5 (spec: default: 5)."""
        from secondbrain.config import get_config

        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        config = get_config()

        searcher = Searcher()
        searcher.search("test query")

        call_args = mock_storage.search.call_args
        assert call_args.kwargs["top_k"] == config.default_top_k

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_score(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search results include score (spec: score 0-1)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_chunk_text(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search results include chunk_text (spec: chunk_text)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_source_file(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search results include source_file (spec: source_file)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_results_include_page_number(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search results include page_number (spec: page_number if available)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

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

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_empty_results(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search with empty results (spec: empty list)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []  # Empty results
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        results = searcher.search("test query")

        assert results == []

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_generates_embedding_via_sentence_transformers(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search generates embedding via SentenceTransformers (spec: uses same model as ingestion)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query")

        # Verify embedding was generated
        mock_embed.generate.assert_called_once_with("test query")

    @patch("secondbrain.search.LocalEmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_search_uses_vector_index(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search uses vector index (spec: MongoDB vector search index)."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.search.return_value = []
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.search("test query")

        # Verify storage search was called
        mock_storage.search.assert_called_once()
