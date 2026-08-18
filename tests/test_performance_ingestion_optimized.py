"""End-to-end performance regression tests for the re-ingest skip feature.

Complements the Todo-1 baseline harness (:mod:`tests.test_performance_ingestion`)
by asserting the *end-to-end* gains introduced by the ingestion-performance plan
(re-ingest skip via persisted ``text_hash``, shared embedding cache, batched
embeddings). These are the deterministic gate for the optimization: after a
first ingest of a corpus, a second ingest of the **same unchanged files** must
perform **zero** embedding calls and **zero** storage writes, because every
``text_hash`` already exists in the vector store
(``skip_existing_on_reingest=True`` by default).

Wall-clock timing is intentionally only a **lenient secondary gate**
(``optimized_ms <= max(baseline_ms * 1.5, 5000)``). The fast-suite corpus is a
few milliseconds, embeddings are mocked, and shared-CI wall-clock variance makes
any tight bound flaky; the strong, non-flaky evidence is the zero-embed-call
assertion in :func:`test_reingest_skip_reduces_embedding_and_storage_work`.

Pool note: these tests force ``pool="thread"``. The embed/storage call counters
are monkeypatches on class methods, which only a same-process (thread) pool can
observe — a process pool re-imports the modules in child workers and loses both
the mock embedding factory and the counters. ``pool="thread"`` is also the only
mode in which the Todo-1 baseline's monkeypatched mock propagates, so it matches
the deterministic test harness.

This is a **test-only** harness: it never imports, patches, or modifies any
production code under ``src/``. It requires a live MongoDB (gated by a ping
pre-check that raises ``pytest.skip`` so the tests never fail in the fast
``-m "not integration"`` suite). To keep the pipeline deterministic the
:class:`EmbeddingProviderFactory` is swapped for the repo's built-in
:class:`MockEmbeddingProvider` for the duration of each test.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from secondbrain.config import get_config
from secondbrain.document import DocumentIngestor
from secondbrain.document.ingestor._constants import is_supported
from secondbrain.embedding import EmbeddingProviderFactory
from secondbrain.embedding.mock import MockEmbeddingProvider
from secondbrain.storage import VectorStorage

pytestmark = [pytest.mark.integration]

# Matches the test-compose stack from docker-compose.test.yml (auth'd root user,
# port 27018). Override with SECONDBRAIN_MONGO_URI when running elsewhere.
_DEFAULT_MONGO_URI = (
    "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin"
)
_TEST_DB = "secondbrain_perf_optimized_test"
_TEST_COLLECTION = "embeddings_perf_optimized"
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


def _drop_collection(uri: str, db: str, collection: str) -> None:
    """Drop the test collection so the first ingest always starts cold.

    Args:
        uri: MongoDB connection URI.
        db: Database name to target.
        collection: Collection name to drop.
    """
    from pymongo import MongoClient

    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        client[db][collection].drop()
    finally:
        client.close()


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


def _configure_storage(uri: str) -> None:
    """Point Config/Storage at the isolated perf DB+collection and drop leftovers.

    Flushes the cached Config so the ingest path picks up the isolated DB and
    collection from environment variables.

    Args:
        uri: MongoDB connection URI to use.
    """
    os.environ["SECONDBRAIN_MONGO_URI"] = uri
    os.environ["SECONDBRAIN_MONGO_DB"] = _TEST_DB
    os.environ["SECONDBRAIN_MONGO_COLLECTION"] = _TEST_COLLECTION
    get_config.cache_clear()
    _drop_collection(uri, _TEST_DB, _TEST_COLLECTION)


def _patch_mock_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the embedding factory for a deterministic mock.

    Worker threads resolve the class method lazily, so patching the class
    attribute propagates to every provider the workers create.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """

    def _mock_factory(_cfg: Any) -> MockEmbeddingProvider:
        return MockEmbeddingProvider(model_name="mock-384", dimension=_EMBED_DIM)

    monkeypatch.setattr(
        EmbeddingProviderFactory,
        "create_from_config",
        staticmethod(_mock_factory),  # type: ignore[arg-type]
    )


def _patch_generate_batch_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Wrap ``MockEmbeddingProvider.generate_batch`` and count invocations.

    The returned single-element list accumulates the running call count for the
    lifetime of the test; snapshot it between runs to derive per-run counts.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns
    -------
        A mutable ``[count]`` list incremented on every ``generate_batch`` call.
    """
    calls: list[int] = [0]
    original = MockEmbeddingProvider.generate_batch

    def _counting(self, texts: list[str]) -> list[list[float]]:
        calls[0] += 1
        return original(self, texts)

    monkeypatch.setattr(MockEmbeddingProvider, "generate_batch", _counting)
    return calls


def _patch_store_batch_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Wrap ``VectorStorage.store_batch`` and count invocations.

    ``store_batch`` runs on the ingestion owner thread, so it is observable for
    both thread and process pools; here it backs up the embed counter.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns
    -------
        A mutable ``[count]`` list incremented on every ``store_batch`` call.
    """
    calls: list[int] = [0]
    original = VectorStorage.store_batch

    def _counting(self, documents: list[dict[str, Any]]) -> int:
        calls[0] += 1
        return original(self, documents)

    monkeypatch.setattr(VectorStorage, "store_batch", _counting)
    return calls


def _ingest(
    dir_path: Path, skip_existing: bool | None = None
) -> tuple[dict[str, Any], float]:
    """Ingest ``dir_path`` with a fresh ingestor and return (result, wall_ms).

    A fresh :class:`DocumentIngestor` is created on every call so the in-memory
    embedding cache starts empty — otherwise a reused cache would mask the
    skip feature (the second run would hit the cache even without the feature).

    Args:
        dir_path: Directory to ingest (recursive=False).
        skip_existing: Passed straight through to ``ingest``; ``None`` falls
            back to ``config().skip_existing_on_reingest`` (True by default).
            When True unchanged ``text_hash`` values skip embedding and storage.

    Returns
    -------
        Tuple of the ingest result dict and the wall-clock duration in ms.
    """
    ingestor = DocumentIngestor(verbose=False)
    start = time.perf_counter()
    result = ingestor.ingest(
        str(dir_path),
        recursive=False,
        batch_size=2,
        cores=2,
        pool="thread",
        skip_existing=skip_existing,
    )
    total_ms = (time.perf_counter() - start) * 1000
    return result, total_ms


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Run the shared Mongo/config/embedding setup and write the corpus.

    Skips cleanly when MongoDB is unreachable. Returns the number of supported
    source files written.

    Args:
        tmp_path: Pytest tmp_path fixture for the fresh corpus directory.
        monkeypatch: Pytest monkeypatch fixture.

    Returns
    -------
        The expected number of supported source files in the corpus.
    """
    uri = os.environ.get("SECONDBRAIN_MONGO_URI") or _DEFAULT_MONGO_URI
    if not _mongo_reachable(uri):
        pytest.skip(
            "MongoDB unreachable - optimized ingestion regression skipped. "
            f"Start the test stack via docker-compose -f docker-compose.test.yml "
            f"up -d, then rerun with SECONDBRAIN_MONGO_URI={uri}"
        )

    _configure_storage(uri)
    _patch_mock_embeddings(monkeypatch)

    files = _write_corpus(tmp_path)
    expected_files = sum(1 for p in files if is_supported(p))
    assert expected_files == len(files)  # all fixtures are supported
    assert expected_files > 0
    return expected_files


def test_reingest_skip_reduces_embedding_and_storage_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-ingesting unchanged files performs zero embed + zero storage work.

    This is the primary, deterministic gate for the re-ingest skip feature. The
    first ingest (cold collection) must embed and store. A second ingest of the
    same files **relying on the default ``skip_existing_on_reingest=True``** must
    report every file as a success and perform **zero** ``generate_batch`` calls
    and **zero** ``store_batch`` calls, because every ``text_hash`` already
    exists in the vector store. (Passing ``skip_existing=None`` here means the
    test exercises the config default, so forcing the flag off in the
    environment makes this test fail — the red half of the red/green control.)
    """
    expected_files = _setup(tmp_path, monkeypatch)
    embed_calls = _patch_generate_batch_counter(monkeypatch)
    store_calls = _patch_store_batch_counter(monkeypatch)

    # Run 1 (cold): fresh collection, nothing to skip -> full ingest.
    result1, _ = _ingest(tmp_path, skip_existing=None)
    first_embed = embed_calls[0]
    first_store = store_calls[0]

    assert result1["success"] == expected_files, (
        f"cold ingest should succeed for all {expected_files} files; "
        f"got {result1['success']}, failures={result1['failures']}"
    )
    assert result1["failed"] == 0
    assert first_embed > 0, "cold ingest must embed at least one batch"
    assert first_store > 0, "cold ingest must store at least one batch"

    # Run 2 (re-ingest unchanged files, relying on the default skip flag): fresh
    # ingestor with an empty in-memory embedding cache, so only the
    # persisted-hash skip can stop the embedding/storage work.
    result2, _ = _ingest(tmp_path, skip_existing=None)
    second_embed = embed_calls[0] - first_embed
    second_store = store_calls[0] - first_store

    assert result2["success"] == expected_files, (
        f"re-ingest should report all {expected_files} files as success; "
        f"got {result2['success']}, failures={result2['failures']}"
    )
    assert result2["failed"] == 0
    assert second_embed == 0, (
        f"re-ingest performed {second_embed} embed calls on unchanged files; "
        "re-ingest skip feature is not reducing embedding work"
    )
    assert second_store == 0, (
        f"re-ingest performed {second_store} store_batch calls on unchanged "
        "files; re-ingest skip feature is not reducing storage work"
    )


def test_reingest_without_skip_reembeds_and_restores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Red control: disabling skip re-does all the embedding/storage work.

    Run 2 with ``skip_existing=False`` must re-embed and re-store every chunk —
    proving it is the skip feature itself (not e.g. coincidence or storage
    dedup) that drives the call counters to zero in
    :func:`test_reingest_skip_reduces_embedding_and_storage_work`.
    """
    expected_files = _setup(tmp_path, monkeypatch)
    embed_calls = _patch_generate_batch_counter(monkeypatch)
    store_calls = _patch_store_batch_counter(monkeypatch)

    result1, _ = _ingest(tmp_path, skip_existing=True)
    first_embed = embed_calls[0]
    first_store = store_calls[0]
    assert result1["success"] == expected_files
    assert first_embed > 0 and first_store > 0

    # Run 2 with skip disabled -> identical work is repeated.
    result2, _ = _ingest(tmp_path, skip_existing=False)
    second_embed = embed_calls[0] - first_embed
    second_store = store_calls[0] - first_store

    assert result2["success"] == expected_files
    assert result2["failed"] == 0
    assert second_embed > 0, (
        "expected re-embedding with skip disabled, but no embed calls occurred"
    )
    assert second_store > 0, (
        "expected re-storing with skip disabled, but no store_batch calls occurred"
    )


@pytest.mark.slow
def test_optimized_ingest_timing_no_catastrophic_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lenient timing gate: re-ingest must not be catastrophically slower.

    Because the fast-suite corpus is tiny and embeddings are mocked, a tight
    timing bound would be flaky under shared-CI variance. Instead this is a
    deliberately generous secondary gate: the second (skip) ingest wall-time
    must be at most ``baseline_ms * 1.5`` or 5s, whichever is larger — i.e. it
    only fails on a catastrophic regression (e.g. the skip feature adding a slow
    path). The strong evidence for the speedup remains the deterministic
    zero-work assertions above.
    """
    _ = _setup(tmp_path, monkeypatch)

    _, baseline_ms = _ingest(tmp_path, skip_existing=True)
    _, optimized_ms = _ingest(tmp_path, skip_existing=True)

    bound = max(baseline_ms * 1.5, 5000.0)
    assert optimized_ms <= bound, (
        f"optimized re-ingest took {optimized_ms:.0f}ms vs baseline "
        f"{baseline_ms:.0f}ms (bound={bound:.0f}ms); \
catastrophic timing regression"
    )
