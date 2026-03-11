"""Tests for management module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.management import BaseManager, Deleter, Lister, StatusChecker
from secondbrain.utils.connections import ServiceUnavailableError


class TestBaseManager:
    """Tests for BaseManager class."""

    @patch("secondbrain.management.VectorStorage")
    def test_init_default(self, mock_storage_class: MagicMock) -> None:
        """Test initialization with defaults."""
        manager = BaseManager()
        assert manager.verbose is False
        mock_storage_class.assert_called_once()

    @patch("secondbrain.management.VectorStorage")
    def test_init_verbose(self, mock_storage_class: MagicMock) -> None:
        """Test initialization with verbose flag."""
        manager = BaseManager(verbose=True)
        assert manager.verbose is True

    @patch("secondbrain.management.VectorStorage")
    def test_close(self, mock_storage_class: MagicMock) -> None:
        """Test close method."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage

        manager = BaseManager()
        manager.close()
        mock_storage.close.assert_called_once()

    @patch("secondbrain.management.VectorStorage")
    def test_context_manager(self, mock_storage_class: MagicMock) -> None:
        """Test context manager protocol."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage

        with BaseManager() as manager:
            assert isinstance(manager, BaseManager)

        mock_storage.close.assert_called_once()

    @patch("secondbrain.management.VectorStorage")
    def test_ensure_storage_available_success(
        self, mock_storage_class: MagicMock
    ) -> None:
        """Test _ensure_storage_available when service is available."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage_class.return_value = mock_storage

        manager = BaseManager()
        # Should not raise
        manager._ensure_storage_available()

    @patch("secondbrain.management.VectorStorage")
    def test_ensure_storage_available_failure(
        self, mock_storage_class: MagicMock
    ) -> None:
        """Test _ensure_storage_available raises when service unavailable."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        manager = BaseManager()
        with pytest.raises(ServiceUnavailableError) as exc_info:
            manager._ensure_storage_available()

        assert "MongoDB" in str(exc_info.value)


class TestLister:
    """Tests for Lister class."""

    @patch("secondbrain.management.VectorStorage")
    def test_init_default(self, mock_storage_class: MagicMock) -> None:
        """Test initialization with defaults."""
        lister = Lister()
        assert lister.verbose is False

    @patch("secondbrain.management.VectorStorage")
    def test_init_verbose(self, mock_storage_class: MagicMock) -> None:
        """Test initialization with verbose."""
        lister = Lister(verbose=True)
        assert lister.verbose is True

    @patch("secondbrain.management.VectorStorage")
    def test_list_chunks_all(self, mock_storage_class: MagicMock) -> None:
        """Test listing all chunks."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.list_chunks.return_value = [
            {"chunk_id": "1", "source_file": "test.pdf"},
            {"chunk_id": "2", "source_file": "test2.pdf"},
        ]
        mock_storage_class.return_value = mock_storage

        lister = Lister()
        results = lister.list_chunks()
        assert len(results) == 2
        mock_storage.list_chunks.assert_called_once_with(
            source_filter=None, chunk_id=None, limit=50, offset=0
        )

    @patch("secondbrain.management.VectorStorage")
    def test_list_chunks_with_source_filter(
        self, mock_storage_class: MagicMock
    ) -> None:
        """Test listing with source filter."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.list_chunks.return_value = [
            {"chunk_id": "1", "source_file": "test.pdf"},
        ]
        mock_storage_class.return_value = mock_storage

        lister = Lister()
        results = lister.list_chunks(source_filter="test.pdf")
        assert len(results) == 1
        mock_storage.list_chunks.assert_called_once_with(
            source_filter="test.pdf", chunk_id=None, limit=50, offset=0
        )

    @patch("secondbrain.management.VectorStorage")
    def test_list_chunks_with_pagination(self, mock_storage_class: MagicMock) -> None:
        """Test listing with pagination."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.list_chunks.return_value = []
        mock_storage_class.return_value = mock_storage

        lister = Lister()
        lister.list_chunks(limit=10, offset=20)
        mock_storage.list_chunks.assert_called_once_with(
            source_filter=None, chunk_id=None, limit=10, offset=20
        )

    @patch("secondbrain.management.VectorStorage")
    def test_list_chunks_connection_error(self, mock_storage_class: MagicMock) -> None:
        """Test list_chunks raises on connection error."""
        from secondbrain.utils.connections import ServiceUnavailableError

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        lister = Lister()
        try:
            lister.list_chunks()
        except ServiceUnavailableError as e:
            assert "MongoDB" in str(e)


class TestDeleter:
    """Tests for Deleter class."""

    @patch("secondbrain.management.VectorStorage")
    def test_init_default(self, mock_storage_class: MagicMock) -> None:
        """Test initialization with defaults."""
        deleter = Deleter()
        assert deleter.verbose is False

    @patch("secondbrain.management.VectorStorage")
    def test_delete_all(self, mock_storage_class: MagicMock) -> None:
        """Test deleting all documents."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.delete_all.return_value = 100
        mock_storage_class.return_value = mock_storage

        deleter = Deleter()
        result = deleter.delete(all=True)
        assert result == 100
        mock_storage.delete_all.assert_called_once()

    @patch("secondbrain.management.VectorStorage")
    def test_delete_by_source(self, mock_storage_class: MagicMock) -> None:
        """Test deleting by source file."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.delete_by_source.return_value = 5
        mock_storage_class.return_value = mock_storage

        deleter = Deleter()
        result = deleter.delete(source="test.pdf")
        assert result == 5
        mock_storage.delete_by_source.assert_called_once_with("test.pdf")

    @patch("secondbrain.management.VectorStorage")
    def test_delete_by_chunk_id(self, mock_storage_class: MagicMock) -> None:
        """Test deleting by chunk ID."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.delete_by_chunk_id.return_value = 1
        mock_storage_class.return_value = mock_storage

        deleter = Deleter()
        result = deleter.delete(chunk_id="chunk-123")
        assert result == 1
        mock_storage.delete_by_chunk_id.assert_called_once_with("chunk-123")

    @patch("secondbrain.management.VectorStorage")
    def test_delete_no_params(self, mock_storage_class: MagicMock) -> None:
        """Test delete with no parameters."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage_class.return_value = mock_storage

        deleter = Deleter()
        result = deleter.delete()
        assert result == 0

    @patch("secondbrain.management.VectorStorage")
    def test_delete_priority_all_over_chunk_id(
        self, mock_storage_class: MagicMock
    ) -> None:
        """Test that all=True takes priority over chunk_id."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.delete_all.return_value = 100
        mock_storage.delete_by_chunk_id.return_value = 1
        mock_storage_class.return_value = mock_storage

        deleter = Deleter()
        result = deleter.delete(all=True, chunk_id="chunk-123")

        assert result == 100
        mock_storage.delete_all.assert_called_once()
        mock_storage.delete_by_chunk_id.assert_not_called()

    @patch("secondbrain.management.VectorStorage")
    def test_delete_priority_chunk_id_over_source(
        self, mock_storage_class: MagicMock
    ) -> None:
        """Test that chunk_id takes priority over source."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.delete_by_chunk_id.return_value = 1
        mock_storage.delete_by_source.return_value = 5
        mock_storage_class.return_value = mock_storage

        deleter = Deleter()
        result = deleter.delete(chunk_id="chunk-123", source="test.pdf")

        assert result == 1
        mock_storage.delete_by_chunk_id.assert_called_once_with("chunk-123")
        mock_storage.delete_by_source.assert_not_called()

    @patch("secondbrain.management.VectorStorage")
    def test_delete_connection_error(self, mock_storage_class: MagicMock) -> None:
        """Test delete raises on connection error."""
        from secondbrain.utils.connections import ServiceUnavailableError

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        deleter = Deleter()
        try:
            deleter.delete(all=True)
        except ServiceUnavailableError as e:
            assert "MongoDB" in str(e)


class TestStatusChecker:
    """Tests for StatusChecker class."""

    @patch("secondbrain.management.VectorStorage")
    def test_init_default(self, mock_storage_class: MagicMock) -> None:
        """Test initialization with defaults."""
        status_checker = StatusChecker()
        assert status_checker.verbose is False

    @patch("secondbrain.management.VectorStorage")
    def test_get_status(self, mock_storage_class: MagicMock) -> None:
        """Test getting status."""
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.get_stats.return_value = {
            "total_chunks": 100,
            "unique_sources": 5,
            "database": "secondbrain",
            "collection": "embeddings",
        }
        mock_storage_class.return_value = mock_storage

        status_checker = StatusChecker()
        stats = status_checker.get_status()
        assert stats["total_chunks"] == 100
        assert stats["unique_sources"] == 5
        assert stats["database"] == "secondbrain"
        assert stats["collection"] == "embeddings"
        mock_storage.get_stats.assert_called_once()

    @patch("secondbrain.management.VectorStorage")
    def test_get_status_connection_error(self, mock_storage_class: MagicMock) -> None:
        """Test get status raises on connection error."""
        from secondbrain.utils.connections import ServiceUnavailableError

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = False
        mock_storage_class.return_value = mock_storage

        status_checker = StatusChecker()
        try:
            status_checker.get_status()
        except ServiceUnavailableError as e:
            assert "MongoDB" in str(e)
