"""Tests for ``has_existing_hashes`` re-ingest skip queries.

Covers the sync and async storage methods that answer which of a set of text
hashes already exist in the collection. Uses the ``_execute_find`` seam so the
fast suite needs no real MongoDB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from secondbrain.storage import AsyncVectorStorage, VectorStorage


class _FakeCursor:
    """Minimal async cursor exposing ``to_list`` like a Motor cursor."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    async def to_list(self, length=None):
        return self._docs


class TestSyncHasExistingHashes:
    """Sync ``VectorStorage.has_existing_hashes``."""

    def test_no_hit_returns_empty(self, storage_with_mock: VectorStorage) -> None:
        storage = storage_with_mock
        with patch.object(storage, "_execute_find", return_value=[]) as mock_find:
            result = storage.has_existing_hashes(["a", "b"])
        assert result == set()
        mock_find.assert_called_once_with(
            {"text_hash": {"$in": ["a", "b"]}}, {"text_hash": 1}, skip=0, limit=0
        )

    def test_partial_hit(self, storage_with_mock: VectorStorage) -> None:
        storage = storage_with_mock
        fake = [{"text_hash": "a"}, {"text_hash": "c"}]
        with patch.object(storage, "_execute_find", return_value=fake):
            result = storage.has_existing_hashes(["a", "b", "c"])
        assert result == {"a", "c"}

    def test_full_hit(self, storage_with_mock: VectorStorage) -> None:
        storage = storage_with_mock
        fake = [{"text_hash": "a"}, {"text_hash": "b"}]
        with patch.object(storage, "_execute_find", return_value=fake):
            result = storage.has_existing_hashes(["a", "b"])
        assert result == {"a", "b"}

    def test_empty_input_never_queries(self, storage_with_mock: VectorStorage) -> None:
        storage = storage_with_mock
        with patch.object(storage, "_execute_find") as mock_find:
            result = storage.has_existing_hashes([])
        assert result == set()
        mock_find.assert_not_called()

    def test_ignores_docs_without_text_hash(
        self, storage_with_mock: VectorStorage
    ) -> None:
        storage = storage_with_mock
        fake = [{"text_hash": "a"}, {"other": "b"}]
        with patch.object(storage, "_execute_find", return_value=fake):
            result = storage.has_existing_hashes(["a", "b"])
        assert result == {"a"}


class TestAsyncHasExistingHashes:
    """Async ``AsyncVectorStorage.has_existing_hashes_async``."""

    def _make_storage(self, docs: list[dict]) -> tuple[AsyncVectorStorage, AsyncMock]:
        storage = AsyncVectorStorage.__new__(AsyncVectorStorage)
        mock_find = AsyncMock(return_value=_FakeCursor(docs))
        storage._execute_find = mock_find  # type: ignore[assignment]
        return storage, mock_find

    @pytest.mark.asyncio
    async def test_no_hit_returns_empty(self) -> None:
        storage, mock_find = self._make_storage([])
        result = await storage.has_existing_hashes_async(["a", "b"])
        assert result == set()
        mock_find.assert_called_once_with(
            {"text_hash": {"$in": ["a", "b"]}}, {"text_hash": 1}, skip=0, limit=0
        )

    @pytest.mark.asyncio
    async def test_partial_hit(self) -> None:
        storage, _mock = self._make_storage([{"text_hash": "a"}, {"text_hash": "c"}])
        result = await storage.has_existing_hashes_async(["a", "b", "c"])
        assert result == {"a", "c"}

    @pytest.mark.asyncio
    async def test_full_hit(self) -> None:
        storage, _mock = self._make_storage([{"text_hash": "a"}, {"text_hash": "b"}])
        result = await storage.has_existing_hashes_async(["a", "b"])
        assert result == {"a", "b"}

    @pytest.mark.asyncio
    async def test_empty_input_never_queries(self) -> None:
        storage = AsyncVectorStorage.__new__(AsyncVectorStorage)
        mock_find = AsyncMock()
        storage._execute_find = mock_find  # type: ignore[assignment]
        result = await storage.has_existing_hashes_async([])
        assert result == set()
        mock_find.assert_not_called()
