"""Compact embedding transport (float32 rows) across the ingest boundary.

Tests for task 4/5.4 of ``add-pdf-ingest-memory-bounds``: embeddings are
accumulated, pickled across the worker→parent process boundary, and handed to
storage as fixed-width ``float32`` arrays (per ``cfg.embedding_dtype``)
instead of Python-float-object lists — bounding worker accumulation, the
pickle, and the parent's live copy to ~6 KB per 1536-dim chunk instead of
~49 KB, with numerically unchanged stored values.
"""

from __future__ import annotations

import pickle
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from secondbrain.document import processor
from secondbrain.storage.mock import MockVectorStorage
from secondbrain.utils.embedding_cache import EmbeddingCache


def _stub_dtype_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``config()`` at a minimal float32 config for the embed helper."""
    cfg = SimpleNamespace(embedding_dtype="float32", embedding_batch_size=2)
    monkeypatch.setattr("secondbrain.config.config", lambda: cfg)


class _ListEmbedder:
    """Provider stand-in returning float-object lists (today's provider form)."""

    def __init__(self, dimension: int = 4) -> None:
        self._dimension = dimension
        self.batches: list[list[str]] = []

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [
            [0.1 * (len(text) % 3) + 0.01 * i for i in range(self._dimension)]
            for text in texts
        ]


class TestAsEmbeddingRow:
    """_as_embedding_row coercion / zero-copy contract."""

    def test_already_float32_array_returned_as_is_without_copy(self) -> None:
        arr = np.asarray([0.1, 0.2, 0.3], dtype=np.float32)

        row = processor._as_embedding_row(arr, np.dtype("float32"))

        assert row is arr

    def test_float_list_coerced_to_float32_array(self) -> None:
        row = processor._as_embedding_row([0.1, 0.2, 0.3], np.dtype("float32"))

        assert isinstance(row, np.ndarray)
        assert row.dtype == np.float32
        assert np.array_equal(row, np.asarray([0.1, 0.2, 0.3], dtype=np.float32))

    def test_float64_array_coerced_to_new_float32_array(self) -> None:
        src = np.asarray([0.1, 0.2, 0.3], dtype=np.float64)

        row = processor._as_embedding_row(src, np.dtype("float32"))

        assert row is not src
        assert row.dtype == np.float32
        assert np.array_equal(row, np.asarray([0.1, 0.2, 0.3], dtype=np.float32))

    def test_float32_precision_matches_provider_floats(self) -> None:
        """0.1 is not representable exactly: values equal the provider's floats AT float32 precision."""
        provider = [0.1] * 384

        row = processor._as_embedding_row(provider, np.dtype("float32"))

        assert np.array_equal(row, np.asarray(provider, dtype=np.float32))
        # And bit-identically NOT the float64 literal comparison:
        assert not np.array_equal(row, np.asarray(provider, dtype=np.float64))


class TestEmbedUniqueChunksArrayTransport:
    """_embed_unique_chunks returns fixed-width rows of the configured dtype."""

    def test_output_is_float32_arrays_aligned_with_chunks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_dtype_config(monkeypatch)
        embedder = _ListEmbedder(dimension=3)
        chunks = [{"text": f"chunk {n}"} for n in range(5)]

        embeddings = processor._embed_unique_chunks(
            embedder, chunks, embedding_cache=None, batch_size=2
        )

        assert len(embeddings) == len(chunks)
        provider_rows = embedder.generate_batch([c["text"] for c in chunks])
        for embedding, provider_row in zip(embeddings, provider_rows, strict=True):
            assert isinstance(embedding, np.ndarray)
            assert embedding.dtype == np.float32
            assert np.array_equal(embedding, np.asarray(provider_row, dtype=np.float32))

    def test_cache_hits_coerced_to_the_same_float32_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_dtype_config(monkeypatch)
        cache = EmbeddingCache(max_size=10)
        cache.set("known", [0.9, 0.9, 0.9, 0.9])
        chunks = [{"text": "known"}, {"text": "fresh"}]

        embeddings = processor._embed_unique_chunks(
            _ListEmbedder(), chunks, embedding_cache=cache, batch_size=8
        )

        assert np.array_equal(embeddings[0], np.asarray([0.9] * 4, dtype=np.float32))
        assert embeddings[0].dtype == np.float32


class TestPickleSizeRegression:
    """The worker→parent pickle carries arrays, not float-object lists."""

    def test_array_pickle_is_compact_at_1536_dims(self) -> None:
        """~6 KB/chunk at 1536 dims (spec), far below the list form's pickle."""
        dimension = 1536
        provider_row = [0.001 * i + 0.01 for i in range(dimension)]
        array_form = processor._as_embedding_row(provider_row, np.dtype("float32"))
        list_form = list(provider_row)

        array_bytes = pickle.dumps(array_form, protocol=pickle.HIGHEST_PROTOCOL)
        list_bytes = pickle.dumps(list_form, protocol=pickle.HIGHEST_PROTOCOL)

        # Fixed width: 1536 x float32 = 6144 payload bytes (~6 KiB contract).
        assert array_form.nbytes == dimension * 4
        assert len(array_bytes) < 8192
        assert len(list_bytes) > 2 * len(array_bytes)

    def test_full_worker_result_pickles_arrays_not_lists(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """A worker result document dict pickles with the compact row inside."""
        _stub_dtype_config(monkeypatch)
        embedder = _ListEmbedder(dimension=1536)
        chunks = [{"text": "one unique chunk text", "page": 1}]

        embeddings = processor._embed_unique_chunks(
            embedder, chunks, embedding_cache=None, batch_size=8
        )
        document = {
            "chunk_id": "c1",
            "source_file": "manual.pdf",
            "page_number": 1,
            "chunk_text": chunks[0]["text"],
            "embedding": embeddings[0],
        }
        legacy_document = {**document, "embedding": list(embeddings[0])}

        compact = pickle.dumps(document, protocol=pickle.HIGHEST_PROTOCOL)
        legacy = pickle.dumps(legacy_document, protocol=pickle.HIGHEST_PROTOCOL)

        assert len(compact) < len(legacy) / 2


class TestStoreBoundaryAcceptsArrays:
    """The parent-side store path accepts array vectors unchanged."""

    def test_store_batch_round_trips_array_vectors(self) -> None:
        """The store boundary hands vectors to storage as-is.

        qdrant-client 1.19 accepts ndarrays; MockVectorStorage stands in for
        the storage protocol, so arrays must flow through the boundary
        unchanged (no per-chunk list copies at the boundary).
        """
        storage = MockVectorStorage()
        storage.initialize()
        array = np.asarray([0.1] * 384, dtype=np.float32)

        storage.store_batch(
            [
                {
                    "chunk_id": "c1",
                    "source_file": "manual.pdf",
                    "page_number": 1,
                    "chunk_text": "body text",
                    "embedding": array,
                }
            ]
        )

        stored = next(iter(storage.list_chunks()))
        assert isinstance(stored["embedding"], np.ndarray)
        assert np.array_equal(stored["embedding"], array)

    def test_embedding_cache_stores_raw_provider_items(self) -> None:
        """Cache keys/values stay unchanged: the raw provider item is stored."""
        cache = EmbeddingCache(max_size=10)
        raw_item = [0.9, 0.9, 0.9, 0.9]

        cache.set("known", raw_item)

        cached = cache.get("known")
        assert cached == raw_item
        row = processor._as_embedding_row(cached, np.dtype("float32"))
        assert np.array_equal(row, np.asarray(raw_item, dtype=np.float32))
