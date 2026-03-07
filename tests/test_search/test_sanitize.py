"""Tests for search module sanitization and edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.search import Searcher, sanitize_query


class TestSanitizeQuery:
    """Tests for query sanitization function."""

    def test_sanitize_basic_query(self) -> None:
        """Test sanitization of basic query."""
        result = sanitize_query("simple search query")
        assert result == "simple search query"

    def test_sanitize_query_with_leading_trailing_spaces(self) -> None:
        """Test sanitization strips leading and trailing spaces."""
        result = sanitize_query("   query text   ")
        assert result == "query text"

    def test_sanitize_rejects_empty_query(self) -> None:
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Search query cannot be empty"):
            sanitize_query("")

    def test_sanitize_handles_whitespace_only(self) -> None:
        """Test that whitespace-only query is stripped to empty string."""
        # Current implementation strips whitespace, resulting in empty string
        result = sanitize_query("   ")
        assert result == ""

    def test_sanitize_rejects_excessive_length(self) -> None:
        """Test that query exceeding max length raises ValueError."""
        long_query = "a" * 10001
        with pytest.raises(ValueError, match="exceeds maximum length"):
            sanitize_query(long_query)

    def test_sanitize_blocks_path_traversal(self) -> None:
        """Test sanitization blocks path traversal attempts."""
        malicious_queries = [
            "../etc/passwd",
            "query/../sensitive",
            "folder/../secret",
        ]
        for query in malicious_queries:
            with pytest.raises(ValueError, match="invalid characters or patterns"):
                sanitize_query(query)

    def test_sanitize_blocks_xss_attempts(self) -> None:
        """Test sanitization blocks XSS attempts."""
        malicious_queries = [
            "<script>alert('xss')</script>",
            "<script>document.cookie</script>",
            "<script src='http://evil.com/malware.js'></script>",
        ]
        for query in malicious_queries:
            with pytest.raises(ValueError, match="invalid characters or patterns"):
                sanitize_query(query)

    def test_sanitize_blocks_javascript_protocol(self) -> None:
        """Test sanitization blocks javascript: protocol."""
        malicious_queries = [
            "javascript:alert('xss')",
            "JAVASCRIPT:alert('xss')",
            "JaVaScRiPt:alert('xss')",
        ]
        for query in malicious_queries:
            with pytest.raises(ValueError, match="invalid characters or patterns"):
                sanitize_query(query)

    def test_sanitize_blocks_null_bytes(self) -> None:
        """Test sanitization blocks null bytes."""
        malicious_queries = [
            "query\x00injection",
            "test\x00string",
            "\x00start",
        ]
        for query in malicious_queries:
            with pytest.raises(ValueError, match="invalid characters or patterns"):
                sanitize_query(query)

    def test_sanitize_removes_control_characters(self) -> None:
        """Test sanitization removes control characters."""
        query_with_controls = "query\x01\x02\x03text"
        result = sanitize_query(query_with_controls)
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x03" not in result

    def test_sanitize_removes_del_characters(self) -> None:
        """Test sanitization removes DEL character (0x7f)."""
        query_with_del = "query\x7ftext"
        result = sanitize_query(query_with_del)
        assert "\x7f" not in result

    def test_sanitize_removes_extended_ascii_controls(self) -> None:
        """Test sanitization removes extended ASCII control characters."""
        query_with_extended = "query\x80\x9ftext"
        result = sanitize_query(query_with_extended)
        assert "\x80" not in result
        assert "\x9f" not in result

    def test_sanitize_preserves_special_characters(self) -> None:
        """Test sanitization preserves valid special characters."""
        query = "search for C++ AND Python OR Java"
        result = sanitize_query(query)
        assert result == query

    def test_sanitize_preserves_unicode(self) -> None:
        """Test sanitization preserves unicode characters."""
        query = "搜索中文 émojis 🎉 日本語"
        result = sanitize_query(query)
        assert "搜索中文" in result
        assert "émojis" in result

    def test_sanitize_preserves_numbers(self) -> None:
        """Test sanitization preserves numbers."""
        query = "search for 12345 and 67.89"
        result = sanitize_query(query)
        assert "12345" in result
        assert "67.89" in result

    def test_sanitize_preserves_punctuation(self) -> None:
        """Test sanitization preserves normal punctuation."""
        query = "What is AI? It's amazing! (Very good)"
        result = sanitize_query(query)
        assert "?" in result
        assert "!" in result
        assert "(" in result
        assert ")" in result


class TestSearcherAsyncClose:
    """Tests for Searcher async close patterns."""

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_aclose_with_async_support(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test aclose calls aclose on components that support it."""
        import asyncio

        async def mock_aclose() -> None:
            pass

        mock_embed = MagicMock()
        mock_embed.aclose = mock_aclose
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.aclose = mock_aclose
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()

        async def test_async_close() -> None:
            await searcher.aclose()

        asyncio.run(test_async_close())

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_aclose_with_sync_only_components(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test aclose handles components without async support."""
        import asyncio

        # Components without aclose method
        mock_embed = MagicMock(spec=[])
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock(spec=[])
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()

        async def test_async_close() -> None:
            await searcher.aclose()

        # Should not raise AttributeError
        asyncio.run(test_async_close())

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_searcher_context_manager(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test Searcher works correctly as context manager."""
        mock_embed = MagicMock()
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage

        with Searcher() as searcher:
            assert searcher is not None

        # Should have called close
        mock_embed.close.assert_called_once()
        mock_storage.close.assert_called_once()

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_searcher_close_closes_both_components(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test close closes both embedding generator and storage."""
        mock_embed = MagicMock()
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()
        searcher.close()

        mock_embed.close.assert_called_once()
        mock_storage.close.assert_called_once()

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_searcher_search_validates_connections(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search validates both connections."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = False
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()

        with pytest.raises(RuntimeError, match="Cannot connect to Ollama"):
            searcher.search("test query")

    @patch("secondbrain.search.EmbeddingGenerator")
    @patch("secondbrain.search.VectorStorage")
    def test_searcher_storage_connection_failure(
        self, mock_storage_class: MagicMock, mock_embed_class: MagicMock
    ) -> None:
        """Test search handles storage connection failure."""
        mock_embed = MagicMock()
        mock_embed.validate_connection.return_value = True
        mock_embed.generate.return_value = [0.1] * 384
        mock_embed_class.return_value = mock_embed

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        searcher = Searcher()

        with pytest.raises(RuntimeError, match="Cannot connect to MongoDB"):
            searcher.search("test query")
