"""Tests for StorageFactory backend selection branches.

Covers the mock-backend branch, case-insensitive backend matching, the
qdrant branch wiring, and the ValueError for unknown backends.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage.factory import StorageFactory
from secondbrain.storage.mock import MockVectorStorage


class TestStorageFactoryBranches:
    def test_mock_backend_returns_mock_storage(self) -> None:
        """storage_backend='mock' returns a real MockVectorStorage instance."""
        cfg = MagicMock()
        cfg.storage_backend = "mock"

        result = StorageFactory.create_from_config(cfg)

        assert isinstance(result, MockVectorStorage)

    def test_backend_matching_is_case_insensitive(self) -> None:
        """Backend names are lowercased before matching."""
        cfg = MagicMock()
        cfg.storage_backend = "MOCK"

        result = StorageFactory.create_from_config(cfg)

        assert isinstance(result, MockVectorStorage)

    def test_qdrant_branch_passes_config_values(self) -> None:
        """storage_backend='qdrant' wires url/api_key/collection from config."""
        cfg = MagicMock()
        cfg.storage_backend = "qdrant"
        cfg.qdrant_url = "http://qdrant:6333"
        cfg.qdrant_api_key = "sk-qdrant"
        cfg.qdrant_collection = "embeddings"

        with patch("secondbrain.storage.factory.QdrantVectorStorage") as mock_qdrant:
            result = StorageFactory.create_from_config(cfg)

        assert result is mock_qdrant.return_value
        mock_qdrant.assert_called_once_with(
            url="http://qdrant:6333",
            api_key="sk-qdrant",
            collection_name="embeddings",
        )

    def test_unknown_backend_raises_value_error(self) -> None:
        """Unrecognized backends raise ValueError naming the backend."""
        cfg = MagicMock()
        cfg.storage_backend = "weaviate"

        with pytest.raises(ValueError, match="Unknown storage_backend: 'weaviate'"):
            StorageFactory.create_from_config(cfg)

    def test_default_config_singleton_when_cfg_omitted(self) -> None:
        """Without a cfg argument the process-wide config singleton is used."""
        with patch("secondbrain.storage.factory.get_config") as mock_get_config:
            cfg = MagicMock()
            cfg.storage_backend = "mock"
            mock_get_config.return_value = cfg

            result = StorageFactory.create_from_config()

        assert isinstance(result, MockVectorStorage)
        mock_get_config.assert_called_once_with()
