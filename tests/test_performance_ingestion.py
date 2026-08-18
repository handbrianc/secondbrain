"""Performance baseline harness for the parallel document ingestion pipeline.

Records a wall-time baseline for ``DocumentIngestor.ingest`` over a small
corpus of plain-text fixtures (``.txt`` / ``.md``) and reports the storage
timing captured by the global :class:`PerfMetrics` singleton.

This is a **test-only** harness — it never imports, patches, or modifies any
production code under ``src/``. It requires a live MongoDB (gated by a
lightweight connection pre-check that raises ``pytest.skip`` so the test never
fails in the fast ``-m "not integration"`` suite). To keep the pipeline
deterministic and runnable without an external OpenAI-compatible embedding
service, the :class:`EmbeddingProviderFactory` is swapped for the repo's
built-in :class:`MockEmbeddingProvider` for the duration of the test only
(worker threads re-create the provider from config, so patching the factory
class method is what makes this propagate).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from secondbrain.config import get_config
from secondbrain.document import DocumentIngestor
from secondbrain.embedding import EmbeddingProviderFactory
from secondbrain.embedding.mock import MockEmbeddingProvider
from secondbrain.utils.perf_monitor import metrics

pytestmark = [pytest.mark.integration]

# Matches the project default in src/secondbrain/config/mongo.py. Override with
# SECONDBRAIN_MONGO_URI (e.g. mongodb://localhost:27018 for the test compose
# stack from docker-compose.test.yml).
_DEFAULT_MONGO_URI = (
    "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin"
)
_TEST_DB = "secondbrain_perf_baseline_test"
_TEST_COLLECTION = "embeddings_perf_baseline"
# Embedding dimension must be >0 and consistent across provider + storage.
_EMBED_DIM = 384


def _mongo_reachable(uri: str) -> bool:
    """Return True if MongoDB answers a ``ping`` at ``uri``.

    Args:
        uri: MongoDB connection URI to probe.

    Returns
    -------
        True when a server is reachable, False otherwise.
    """
    from pymongo import MongoClient

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


def _write_corpus(dir_path: Path) -> list[Path]:
    """Write the small plain-text corpus into ``dir_path``.

    Three supported files (two ``.txt``, one ``.md``), each several hundred
    words long so chunking produces multiple chunks. Returns the written paths.

    Args:
        dir_path: Directory to write the fixture files into.

    Returns
    -------
        List of paths to the created fixture files.
    """
    paragraph = (
        "Experiments with neural information retrieval show that dense "
        "semantic retrieval reliably outperforms lexical term matching for "
        "open-domain question answering. Modern retrieval systems embed both "
        "queries and documents into a shared, high-dimensional vector space "
        "where cosine similarity approximates the semantic relatedness of the "
        "underlying text. This approach underpins retrieval-augmented "
        "generation, a strategy that first recalls the most relevant passages "
        "from a large corpus and then passes them to a generative language "
        "model to compose the final answer. The quality of the retrieved "
        "evidence is usually the strongest predictor of the quality of the "
        "generated response."
    )
    bodies = {
        "document_a.txt": (paragraph + " " + paragraph).rstrip(),
        "document_b.txt": (paragraph * 3).rstrip(),
        "notes.md": "# Retrieval Notes\n\n" + (paragraph * 2).rstrip(),
    }
    paths: list[Path] = []
    for name, content in bodies.items():
        path = dir_path / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


def _print_baseline(
    *,
    n_files: int,
    total_ms: float,
    storage_store_stats: dict[str, Any] | None,
    storage_batch_stats: dict[str, Any] | None,
) -> None:
    """Print the ingestion baseline block to stdout.

    Args:
        n_files: Number of supported source files ingested.
        total_ms: Wall-clock duration of the ``ingest`` call in ms.
        storage_store_stats: Stats for the ``storage_store`` metric or None.
        storage_batch_stats: Stats for the ``storage_store_batch`` metric or None.
    """
    print(
        f"BASELINE: files={n_files} total_ms={total_ms:.0f} "
        f"extract_chunk_embed_total_ms={total_ms:.0f}"
    )
    if storage_batch_stats is not None:
        print(
            "BASELINE storage_store_batch(ms): total="
            f"{storage_batch_stats['total_seconds'] * 1000:.1f} "
            f"count={storage_batch_stats['count']} "
            f"p50={storage_batch_stats['p50_seconds'] * 1000:.1f}"
        )
    if storage_store_stats is not None:
        print(
            "BASELINE storage_store(ms): total="
            f"{storage_store_stats['total_seconds'] * 1000:.1f} "
            f"count={storage_store_stats['count']}"
        )


def test_ingestion_baseline_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingest a small text corpus and record the wall-time + storage baseline.

    Asserts the happy path (``success == expected_files``) and that the
    measured wall-time is positive. Skips cleanly if MongoDB is unreachable.
    """
    from secondbrain.document.ingestor._constants import is_supported

    uri = os.environ.get("SECONDBRAIN_MONGO_URI") or _DEFAULT_MONGO_URI
    if not _mongo_reachable(uri):
        pytest.skip(
            "MongoDB unreachable - ingestion baseline skipped. "
            f"Start it via: docker-compose -f docker-compose.test.yml up -d "
            f"(or `secondbrain start --wait`), then rerun with "
            f"SECONDBRAIN_MONGO_URI={uri}"
        )

    # Point Storage/Config at the live Mongo and an isolated test DB, then
    # flush the cached Config so the ingest path picks these up.
    os.environ["SECONDBRAIN_MONGO_URI"] = uri
    os.environ["SECONDBRAIN_MONGO_DB"] = _TEST_DB
    os.environ["SECONDBRAIN_MONGO_COLLECTION"] = _TEST_COLLECTION
    get_config.cache_clear()

    # Deterministic embeddings: swap the factory method (worker threads resolve
    # the class method lazily, so patching the class attribute propagates).
    def _mock_factory(_cfg: Any) -> MockEmbeddingProvider:
        return MockEmbeddingProvider(model_name="mock-384", dimension=_EMBED_DIM)

    monkeypatch.setattr(
        EmbeddingProviderFactory,
        "create_from_config",
        staticmethod(_mock_factory),  # type: ignore[arg-type]
    )

    files = _write_corpus(tmp_path)
    expected_files = sum(1 for p in files if is_supported(p))
    assert expected_files == len(files)  # all fixtures are supported
    assert expected_files > 0

    metrics.reset()

    ingestor = DocumentIngestor(verbose=False)
    start = time.perf_counter()
    result = ingestor.ingest(
        str(tmp_path), recursive=False, batch_size=2, cores=2, pool="thread"
    )
    total_ms = (time.perf_counter() - start) * 1000

    _print_baseline(
        n_files=expected_files,
        total_ms=total_ms,
        storage_store_stats=metrics.get_stats("storage_store"),
        storage_batch_stats=metrics.get_stats("storage_store_batch"),
    )

    assert total_ms > 0, "measured ingest wall-time must be positive"
    assert result["success"] == expected_files, (
        f"expected {expected_files} successful files, got "
        f"{result['success']}; failures={result['failures']}"
    )
    assert result["failed"] == 0
