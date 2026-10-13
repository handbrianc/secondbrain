"""Tests for performance monitoring utilities."""

import logging
import time

import numpy as np
import pytest

from secondbrain.utils.perf_monitor import PerfMetrics, metrics, timing

pytestmark = pytest.mark.performance


class TestPercentileTracking:
    """Test p50/p95/p99 latency percentile assertions."""

    def test_percentile_thresholds_enforced(self):
        """Multiple recordings produce stable percentiles; assert threshold bounds."""
        test_metrics = PerfMetrics()

        for i in range(20):
            test_metrics.record("batch_op", 0.095 + (hash(i) % 40) * 0.001)

        stats = test_metrics.get_stats("batch_op")
        assert stats is not None

        assert stats["p95_seconds"] < 0.5, f"p95={stats['p95_seconds']} exceeds 500ms"
        assert stats["p99_seconds"] < 0.5, f"p99={stats['p99_seconds']} exceeds 500ms"
        assert stats["p50_seconds"] < 0.3, f"p50={stats['p50_seconds']} exceeds 300ms"
        assert stats["p50_seconds"] <= stats["p95_seconds"]
        assert stats["p95_seconds"] <= stats["p99_seconds"]

    def test_percentiles_ordering_with_variance(self):
        """With outliers present, p99 must exceed p50 to confirm distribution tails are tracked."""
        test_metrics = PerfMetrics()

        test_metrics.record("tail_test", 0.01)
        test_metrics.record("tail_test", 0.02)
        test_metrics.record("tail_test", 0.03)
        test_metrics.record("tail_test", 0.10)
        test_metrics.record("tail_test", 0.50)

        stats = test_metrics.get_stats("tail_test")
        assert stats is not None

        assert stats["p50_seconds"] <= stats["p95_seconds"]
        assert stats["p95_seconds"] <= stats["p99_seconds"]
        assert stats["p99_seconds"] > stats["p50_seconds"]


class TestPerfMetrics:
    """Test PerfMetrics collection and statistics."""

    def test_record_duration(self):
        test_metrics = PerfMetrics()

        test_metrics.record("query", 0.045)
        test_metrics.record("query", 0.055)

        stats = test_metrics.get_stats("query")

        assert stats is not None
        assert stats["count"] == 2
        assert 0.090 <= stats["total_seconds"] <= 0.110  # 10% tolerance range
        assert 0.045 <= stats["avg_seconds"] <= 0.055  # 20% tolerance range
        assert 0.040 <= stats["min_seconds"] <= 0.050  # Tolerance for min
        assert 0.050 <= stats["max_seconds"] <= 0.060  # Tolerance for max
        # Percentiles available and are floats
        assert isinstance(stats["p50_seconds"], (float, np.floating))
        assert isinstance(stats["p95_seconds"], (float, np.floating))
        assert isinstance(stats["p99_seconds"], (float, np.floating))

    def test_multiple_metrics(self):
        test_metrics = PerfMetrics()

        test_metrics.record("ingest", 0.5)
        test_metrics.record("search", 0.05)
        test_metrics.record("ingest", 0.6)

        ingest_stats = test_metrics.get_stats("ingest")
        search_stats = test_metrics.get_stats("search")

        assert ingest_stats is not None
        assert search_stats is not None
        assert ingest_stats["count"] == 2
        assert search_stats["count"] == 1
        assert (
            0.50 <= ingest_stats["avg_seconds"] <= 0.60
        )  # 20% tolerance for system variance
        assert (
            0.040 <= search_stats["avg_seconds"] <= 0.060
        )  # 20% tolerance for system variance
        # Verify percentile tracking is present alongside existing stats
        for stat_name, stats in [("ingest", ingest_stats), ("search", search_stats)]:
            assert "p50_seconds" in stats, f"{stat_name}: missing p50_seconds"
            assert "p95_seconds" in stats, f"{stat_name}: missing p95_seconds"
            assert "p99_seconds" in stats, f"{stat_name}: missing p99_seconds"
            assert stats["p50_seconds"] <= stats["p95_seconds"]
            assert stats["p95_seconds"] <= stats["p99_seconds"]

    def test_reset_metric(self):
        test_metrics = PerfMetrics()

        test_metrics.record("query", 0.05)
        test_metrics.reset("query")

        assert test_metrics.get_stats("query") is None

    def test_reset_all(self):
        test_metrics = PerfMetrics()

        test_metrics.record("query", 0.05)
        test_metrics.record("ingest", 0.5)
        test_metrics.reset()

        assert test_metrics.get_stats("query") is None
        assert test_metrics.get_stats("ingest") is None

    def test_empty_stats(self):
        test_metrics = PerfMetrics()
        assert test_metrics.get_stats("nonexistent") is None


class TestTimingDecorator:
    """Test @timing decorator for measuring execution time."""

    def test_timing_decorator_records_duration(self, caplog):
        metrics.reset("test_operation")

        @timing("test_operation")
        def slow_function():
            # Real sleep IS the measured work: the assertion checks the
            # recorded duration falls in a band around it (not a poll).
            time.sleep(0.1)
            return "done"

        with caplog.at_level(logging.DEBUG):
            result = slow_function()

        assert result == "done"

        stats = metrics.get_stats("test_operation")
        assert stats is not None
        assert stats["count"] == 1
        assert (
            0.090 <= stats["avg_seconds"] <= 0.150
        )  # 20% tolerance below, 50% above for sleep variance

    def test_timing_decorator_handles_exceptions(self, caplog):
        metrics.reset("failing_operation")

        @timing("failing_operation")
        def failing_function():
            # Measured work (see note in test_timing_decorator_records_duration).
            time.sleep(0.05)
            raise ValueError("Test error")

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ValueError):
                failing_function()

        stats = metrics.get_stats("failing_operation")
        assert stats is not None
        assert stats["count"] == 1
        assert (
            0.040 <= stats["avg_seconds"] <= 0.100
        )  # 20% tolerance below, 100% above for exception overhead


class TestPerformanceLogging:
    """Test that performance metrics are logged correctly."""

    def test_performance_metrics_logged(self, caplog):
        metrics.reset("document.ingest")
        metrics.reset("semantic.search")

        @timing("document.ingest")
        def ingest_document():
            # Measured work (see note in test_timing_decorator_records_duration).
            time.sleep(0.05)
            return {"status": "ingested"}

        @timing("semantic.search")
        def search_documents():
            # Measured work (see note in test_timing_decorator_records_duration).
            time.sleep(0.03)
            return [{"chunk": "result"}]

        with caplog.at_level(logging.DEBUG):
            ingest_result = ingest_document()
            search_result = search_documents()

        assert ingest_result["status"] == "ingested"
        assert len(search_result) == 1

        log_messages = [record.message for record in caplog.records]

        assert any("document.ingest" in msg for msg in log_messages)
        assert any("semantic.search" in msg for msg in log_messages)

        ingest_stats = metrics.get_stats("document.ingest")
        search_stats = metrics.get_stats("semantic.search")

        assert ingest_stats is not None
        assert search_stats is not None
        assert ingest_stats["count"] == 1
        assert search_stats["count"] == 1
        assert (
            0.040 <= ingest_stats["avg_seconds"] <= 0.070
        )  # 20% tolerance below, 40% above for system variance
        assert (
            0.025 <= search_stats["avg_seconds"] <= 0.045
        )  # 20% tolerance below, 50% above for system variance


class TestSearchLatencySLO:
    """Search-path latency benchmark against the archived semantic-search SLO.

    Spec requirement: search "returns results within 1 second for <10k chunks"
    (openspec/changes/archive/2026-03-06-secondbrain/specs/semantic-search/
    spec.md). ~10k chunks are indexed into Qdrant's in-process local mode —
    the same approach as tests/test_storage/test_qdrant_storage.py — and the
    real Searcher path runs end to end (sanitize -> embedding cache ->
    storage query), with only the embedding provider stubbed (deterministic
    seeded vectors, no API calls).
    """

    @pytest.mark.slow
    def test_search_returns_within_one_second_for_10k_chunks(self):
        import zlib
        from unittest.mock import patch

        from qdrant_client import QdrantClient

        from secondbrain.search import Searcher
        from secondbrain.storage.qdrant import QdrantVectorStorage

        # Compact vectors keep the 10k-point index cheap to build; the SLO is
        # about corpus size, not embedding width.
        dim = 64
        storage = QdrantVectorStorage(collection_name="slo_probe")
        storage._client = QdrantClient(":memory:")
        storage._dimensions = dim

        rng = np.random.default_rng(2026)
        docs = []
        for i in range(10_000):
            vec = rng.standard_normal(dim)
            vec /= np.linalg.norm(vec)
            docs.append(
                {
                    "chunk_id": f"slo-{i:05d}",
                    "source_file": f"doc_{i % 10}.pdf",
                    "page_number": (i % 300) + 1,
                    "chunk_text": f"chunk {i} about machine learning and retrieval",
                    "element_type": "paragraph",
                    "chunk_role": "body",
                    "file_type": "pdf",
                    "text_hash": f"hash-{i}",
                    "embedding": vec.tolist(),
                }
            )
        for start in range(0, len(docs), 1000):
            storage.store_batch(docs[start : start + 1000])

        class _StubEmbedder:
            """Deterministic embedding stand-in (seeded from the query text)."""

            dimensions = dim

            def generate(self, text: str) -> list[float]:
                vec = np.random.default_rng(
                    zlib.crc32(text.encode("utf-8"))
                ).standard_normal(dim)
                return (vec / np.linalg.norm(vec)).tolist()

            def close(self) -> None:
                pass

        with (
            patch(
                "secondbrain.search.StorageFactory.create_from_config",
                return_value=storage,
            ),
            patch(
                "secondbrain.search.EmbeddingProviderFactory.create_from_config",
                return_value=_StubEmbedder(),
            ),
        ):
            searcher = Searcher(verbose=False)
            slo_metrics = PerfMetrics()
            for _ in range(5):
                started = time.perf_counter()
                results = searcher.search("machine learning retrieval embeddings")
                elapsed = time.perf_counter() - started
                slo_metrics.record("semantic_search_slo", elapsed)
                assert results, "search returned no results against the 10k index"
                assert (results[0].get("score") or 0) > 0

        stats = slo_metrics.get_stats("semantic_search_slo")
        assert stats is not None
        # Archived semantic-search spec: results within 1 second for <10k chunks.
        assert stats["p50_seconds"] < 1.0, f"p50={stats['p50_seconds']}s exceeds 1s SLO"
        assert stats["p95_seconds"] < 1.0, f"p95={stats['p95_seconds']}s exceeds 1s SLO"
        assert stats["p99_seconds"] < 1.0, f"p99={stats['p99_seconds']}s exceeds 1s SLO"
