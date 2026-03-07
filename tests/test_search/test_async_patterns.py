"""Tests for async patterns in search module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from secondbrain.search import Searcher


class TestAsyncClosePatterns:
    """Tests for async close patterns and resource management."""

    @pytest.mark.asyncio
    async def test_async_close_releases_resources(self) -> None:
        """Test that aclose properly releases all resources."""
        with (
            patch("secondbrain.search.EmbeddingGenerator") as mock_embed_class,
            patch("secondbrain.search.VectorStorage") as mock_storage_class,
        ):
            mock_embed = MagicMock()
            mock_embed.aclose = AsyncMock()
            mock_embed_class.return_value = mock_embed

            mock_storage = MagicMock()
            mock_storage.aclose = AsyncMock()
            mock_storage_class.return_value = mock_storage

            searcher = Searcher()
            await searcher.aclose()

            mock_embed.aclose.assert_called_once()
            mock_storage.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_close_idempotent(self) -> None:
        """Test that calling aclose multiple times is safe."""
        with (
            patch("secondbrain.search.EmbeddingGenerator") as mock_embed_class,
            patch("secondbrain.search.VectorStorage") as mock_storage_class,
        ):
            mock_embed = MagicMock()
            mock_aclose = AsyncMock()
            mock_embed.aclose = mock_aclose
            mock_embed_class.return_value = mock_embed

            mock_storage = MagicMock()
            mock_storage_aclose = AsyncMock()
            mock_storage.aclose = mock_storage_aclose
            mock_storage_class.return_value = mock_storage

            searcher = Searcher()
            await searcher.aclose()
            await searcher.aclose()

            # Should be called twice (idempotent means safe to call multiple times)
            assert mock_aclose.call_count == 2
            assert mock_storage_aclose.call_count == 2

    @pytest.mark.asyncio
    async def test_async_search_releases_resources(self) -> None:
        """Test that resources are properly managed during async search."""
        with (
            patch("secondbrain.search.EmbeddingGenerator") as mock_embed_class,
            patch("secondbrain.search.VectorStorage") as mock_storage_class,
        ):
            mock_embed = MagicMock()
            mock_embed.validate_connection.return_value = True
            mock_embed.generate.return_value = [0.1] * 384
            mock_aclose = AsyncMock()
            mock_embed.aclose = mock_aclose
            mock_embed_class.return_value = mock_embed

            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage.search.return_value = []
            mock_storage_aclose = AsyncMock()
            mock_storage.aclose = mock_storage_aclose
            mock_storage_class.return_value = mock_storage

            searcher = Searcher()
            results = await asyncio.to_thread(lambda: searcher.search("test query"))

            assert results == []
            # Cleanup
            await searcher.aclose()
            assert mock_aclose.called
            assert mock_storage_aclose.called

    def test_context_manager_async(self) -> None:
        """Test context manager pattern for synchronous usage."""
        with (
            patch("secondbrain.search.EmbeddingGenerator") as mock_embed_class,
            patch("secondbrain.search.VectorStorage") as mock_storage_class,
        ):
            mock_embed = MagicMock()
            mock_embed.validate_connection.return_value = True
            mock_embed_class.return_value = mock_embed

            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage_class.return_value = mock_storage

            with Searcher() as searcher:
                assert searcher is not None
                # Can perform operations
                assert searcher.verbose is False

            # After exit, resources should be closed
            mock_embed.close.assert_called_once()
            mock_storage.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_close_handles_missing_aclose(self) -> None:
        """Test that aclose handles objects without aclose method gracefully."""
        with (
            patch("secondbrain.search.EmbeddingGenerator") as mock_embed_class,
            patch("secondbrain.search.VectorStorage") as mock_storage_class,
        ):
            # Embedding generator without aclose
            mock_embed = MagicMock()
            mock_embed.aclose = None
            del mock_embed.aclose
            mock_embed_class.return_value = mock_embed

            mock_storage = MagicMock()
            mock_storage.aclose = AsyncMock()
            mock_storage_class.return_value = mock_storage

            searcher = Searcher()
            # Should not raise even if embedding_gen doesn't have aclose
            await searcher.aclose()
            mock_storage.aclose.assert_called_once()
