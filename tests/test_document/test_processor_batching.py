"""Tests for the batching + caching helper in the parallel sync processor.

These tests exercise the module-level ``_embed_unique_chunks`` helper in
``secondbrain.document.processor`` directly -- the seam introduced so the
embedding batching and cache behavior can be unit tested without invoking the
heavy docling extraction pipeline.
"""

from __future__ import annotations

import math

from secondbrain.document.processor import _embed_unique_chunks
from secondbrain.utils.embedding_cache import EmbeddingCache


class CountingEmbedder:
    """Fake embedder that records batch call sizes and returns stable vectors.

    Embeddings are derived deterministically from the text content so the same
    text always yields the same vector (mirrors how a real embedder behaves),
    which lets the cache tests compare reused results reliably.
    """

    def __init__(self) -> None:
        self.batch_calls: list[list[str]] = []
        self.single_calls: list[str] = []

    def _embed(self, text: str) -> list[float]:
        return [float(len(text)), float(sum(ord(c) for c in text) % 100), 1.0]

    def generate(self, text: str) -> list[float]:
        self.single_calls.append(text)
        return self._embed(text)

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [self._embed(t) for t in texts]


def _chunks(texts: list[str]) -> list[dict[str, object]]:
    """Build the chunk-dict shape the worker passes to the helper."""
    return [
        {"text": t, "page": 1, "text_hash": str(i), "chunk_role": "body"}
        for i, t in enumerate(texts)
    ]


class TestEmbedUniqueChunksBatching:
    """Batching behavior of ``_embed_unique_chunks`` (Todo 2)."""

    def test_embeds_in_slices_of_batch_size(self) -> None:
        embedder = CountingEmbedder()
        texts = [f"chunk text number {i}" for i in range(23)]
        chunks = _chunks(texts)

        embeddings = _embed_unique_chunks(
            embedder, chunks, embedding_cache=None, batch_size=5
        )

        expected_calls = math.ceil(len(texts) / 5)
        assert len(embedder.batch_calls) == expected_calls
        assert all(len(call) <= 5 for call in embedder.batch_calls)
        assert len(embeddings) == len(texts)

    def test_exact_multiple_single_slice(self) -> None:
        embedder = CountingEmbedder()
        texts = [f"exact chunk {i}" for i in range(10)]
        chunks = _chunks(texts)

        embeddings = _embed_unique_chunks(
            embedder, chunks, embedding_cache=None, batch_size=10
        )

        assert len(embedder.batch_calls) == 1
        assert len(embeddings) == len(texts)

    def test_order_preserved_across_slices(self) -> None:
        embedder = CountingEmbedder()
        texts = [f"ordered chunk {i}" for i in range(12)]
        chunks = _chunks(texts)

        embeddings = _embed_unique_chunks(
            embedder, chunks, embedding_cache=None, batch_size=5
        )

        assert len(embeddings) == len(texts)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            assert embedding == embedder._embed(chunk["text"])  # type: ignore[arg-type]

    def test_empty_input_returns_no_embeddings(self) -> None:
        embedder = CountingEmbedder()

        embeddings = _embed_unique_chunks(
            embedder, [], embedding_cache=None, batch_size=5
        )

        assert embeddings == []
        assert embedder.batch_calls == []


class TestEmbedUniqueChunksCaching:
    """Cache behavior of ``_embed_unique_chunks`` (Todo 3)."""

    def test_second_pass_uses_cache_with_zero_embedder_calls(self) -> None:
        cache = EmbeddingCache(max_size=1000)
        texts = [f"cached chunk {i}" for i in range(11)]
        chunks = _chunks(texts)

        embedder = CountingEmbedder()
        first = _embed_unique_chunks(
            embedder, chunks, embedding_cache=cache, batch_size=5
        )

        assert len(embedder.batch_calls) == math.ceil(len(texts) / 5)
        first_call_count = len(embedder.batch_calls)

        embedder.batch_calls.clear()
        second = _embed_unique_chunks(
            embedder, chunks, embedding_cache=cache, batch_size=5
        )

        assert len(embedder.batch_calls) == 0
        assert first_call_count > 0
        assert second == first

    def test_mixed_cache_hits_and_misses_only_embeds_misses(self) -> None:
        cache = EmbeddingCache(max_size=1000)
        texts = [f"mixed chunk {i}" for i in range(6)]
        chunks = _chunks(texts)

        first_embedder = CountingEmbedder()
        first = _embed_unique_chunks(
            first_embedder, chunks, embedding_cache=cache, batch_size=10
        )

        # Re-embed only a subset of the same texts -> the cache covers half.
        subset = _chunks(texts[0:3])
        second_embedder = CountingEmbedder()
        second = _embed_unique_chunks(
            second_embedder,
            subset[:2] + subset[2:],
            embedding_cache=cache,
            batch_size=10,
        )
        # subset is 3 items, all cached -> no embedder calls.
        assert len(second_embedder.batch_calls) == 0
        assert second == first[0:3]

    def test_cache_none_always_embeds(self) -> None:
        texts = [f"no cache chunk {i}" for i in range(5)]
        chunks = _chunks(texts)

        embedder = CountingEmbedder()
        first = _embed_unique_chunks(
            embedder, chunks, embedding_cache=None, batch_size=10
        )
        first_call_count = len(embedder.batch_calls)

        embedder.batch_calls.clear()
        second = _embed_unique_chunks(
            embedder, chunks, embedding_cache=None, batch_size=10
        )

        assert first_call_count == 1
        assert len(embedder.batch_calls) == 1
        assert second == first
