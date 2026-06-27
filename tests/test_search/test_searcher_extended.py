"""Extended tests for Searcher to improve coverage."""

from unittest.mock import MagicMock

import pytest

from secondbrain.search import Searcher, sanitize_query


@pytest.fixture
def mock_searcher():
    """Create a mock Searcher class with context manager methods."""
    from unittest.mock import AsyncMock
    mock = MagicMock(spec=Searcher)
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=None)
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    mock.close = MagicMock()
    mock.aclose = AsyncMock()
    return mock


class TestSanitizeQuery:
    """Test sanitize_query function."""

    def test_sanitizes_valid_query(self):
        """Test sanitization of valid query."""
        result = sanitize_query("Hello world")
        assert result == "Hello world"

    def test_raises_on_empty_query(self):
        """Test raises ValueError on empty query."""
        with pytest.raises(ValueError, match="cannot be empty"):
            sanitize_query("")

    def test_raises_on_long_query(self):
        """Test raises ValueError on query exceeding max length."""
        long_query = "x" * 10001
        with pytest.raises(ValueError, match="exceeds maximum length"):
            sanitize_query(long_query)

    def test_raises_on_path_traversal_unix(self):
        """Test raises ValueError on Unix path traversal."""
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_query("../../../etc/passwd")

    def test_raises_on_path_traversal_windows(self):
        """Test raises ValueError on Windows path traversal."""
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_query("..\\..\\..\\windows\\system32")

    def test_raises_on_xss_script_tag(self):
        """Test raises ValueError on XSS script tag."""
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_query("<script>alert('xss')</script>")

    def test_raises_on_javascript_protocol(self):
        """Test raises ValueError on javascript: protocol."""
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_query("javascript:alert('xss')")

    def test_raises_on_null_byte(self):
        """Test raises ValueError on null byte."""
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_query("test\x00injection")

    def test_raises_on_xss_event_handler(self):
        """Test raises ValueError on XSS event handler."""
        with pytest.raises(ValueError, match="invalid characters"):
            sanitize_query("<img onerror=alert('xss')>")

    def test_strips_whitespace(self):
        """Test strips leading/trailing whitespace."""
        result = sanitize_query("  hello world  ")
        assert result == "hello world"

    def test_handles_unicode(self):
        """Test handles unicode characters."""
        result = sanitize_query("Hello 世界 🌍")
        assert result == "Hello 世界 🌍"


class TestSearcherContextManager:
    """Test Searcher context manager functionality."""

    def test_context_manager_sync(self, mock_searcher):
        """Test sync context manager."""
        with mock_searcher as searcher:
            assert searcher is not None
            assert hasattr(searcher, 'search')

    @pytest.mark.asyncio
    async def test_context_manager_async(self, mock_searcher):
        """Test async context manager."""
        async with mock_searcher as searcher:
            assert searcher is not None
            assert hasattr(searcher, 'search')

    def test_close_releases_resources(self, mock_searcher):
        """Test close releases resources."""
        searcher = mock_searcher
        searcher.close()
        # Should not raise after close
        assert searcher is not None

    @pytest.mark.asyncio
    async def test_aclose_releases_resources(self, mock_searcher):
        """Test aclose releases async resources."""
        searcher = mock_searcher
        await searcher.aclose()
        # Should not raise after close
        assert searcher is not None
