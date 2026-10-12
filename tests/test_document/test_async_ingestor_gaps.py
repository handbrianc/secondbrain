"""Gap tests for AsyncDocumentIngestor error branches and close paths.

Targets the uncovered branches reported by coverage for
``secondbrain/document/ingestor/_async.py``:

- ``ingest_async`` empty file list (no storage touched) and cleanup of
  embedding generator / storage on every exit path;
- streaming path return contract (``docs_count > 0``);
- non-streaming path when no documents materialize (False) vs stored (True);
- ``process_file_async`` OSError / DocumentExtractionError / unexpected-error
  handling returning False instead of raising, and recording the captured
  failure reason (``"ExceptionType: message"``, the sync worker's format) when
  a ``failure_reasons`` collector is passed;
- ``ingest_async`` failure reasons carrying the real captured cause for
  raised errors (storage/extraction) instead of the generic no-documents
  reason, while cancellation still propagates and is never recorded as a
  document failure;
- streaming chunk loop skipping blank and duplicate segments;
- fallback single-embedding path when batch embedding fails and the
  ``generate_async`` fallback is present;
- batch-embedding TypeError branches when the generator lacks native async
  batch support and has no single fallback either.

Mocking style matches ``tests/test_document/test_async_ingestion.py``:
AsyncMock storage/LLM plus a MagicMock embedding generator.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from secondbrain.document.ingestor import AsyncDocumentIngestor
from secondbrain.exceptions import DocumentExtractionError


def _embedding_gen(
    *,
    batch_async: bool = True,
    single_async: bool = True,
    batch_result: list[list[float]] | Exception | None = None,
    single_result: list[float] | Exception | None = None,
) -> MagicMock:
    """Build a fake embedding generator with configurable async surface."""
    gen = MagicMock(spec=["generate_batch_async", "generate_async", "close"])
    if batch_async:
        if isinstance(batch_result, Exception):
            gen.generate_batch_async = AsyncMock(side_effect=batch_result)
        else:
            gen.generate_batch_async = AsyncMock(return_value=batch_result)
    else:
        gen.generate_batch_async = None
    if single_async:
        if isinstance(single_result, Exception):
            gen.generate_async = AsyncMock(side_effect=single_result)
        else:
            gen.generate_async = AsyncMock(return_value=single_result)
    else:
        gen.generate_async = None
    return gen


def _storage(docs_ok: bool = True) -> MagicMock:
    st = MagicMock(spec=["store_batch_async", "close"])
    st.store_batch_async = AsyncMock(return_value=["id1"] if docs_ok else [])
    st.close = MagicMock()
    return st


def _chunk(text: str, page: int = 1) -> dict[str, Any]:
    import hashlib

    normalized = " ".join(text.lower().split())
    return {
        "file_path": Path("/tmp/sample.pdf"),
        "original_index": page,
        "text": text,
        "page": page,
        "text_hash": hashlib.sha256(normalized.encode()).hexdigest(),
        "chunk_role": "body",
        "element_type": "body",
    }


@pytest.fixture
def no_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the non-streaming branch of process_file_async."""
    cfg = config_obj()
    monkeypatch.setattr(cfg, "streaming_enabled", False, raising=False)


def config_obj() -> Any:
    from secondbrain.config import config

    return config()


class TestIngestAsyncRouting:
    """ingest_async file collection, empty path, and close-on-exit behavior."""

    @pytest.mark.asyncio
    async def test_no_files_returns_zero_and_closes_providers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()

        gen = _embedding_gen(batch_result=[[0.1] * 8])
        st = _storage()
        closed: list[str] = []
        gen.close = MagicMock(side_effect=lambda: closed.append("gen"))
        st.close = MagicMock(side_effect=lambda: closed.append("storage"))

        import secondbrain.embedding as emb_mod
        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            emb_mod.EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(lambda cfg: gen),
        )
        monkeypatch.setattr(
            storage_mod.StorageFactory,
            "create_from_config",
            staticmethod(lambda cfg: st),
        )

        ingestor = AsyncDocumentIngestor()

        def _fail(*_args: Any) -> Any:
            raise AssertionError("process_file_async must not run for 0 files")

        with patch.object(ingestor, "process_file_async", side_effect=_fail):
            result = await ingestor.ingest_async(str(empty))

        assert result == {
            "success": 0,
            "failed": 0,
            "failures": [],
            "skipped": 0,
        }
        assert closed == ["gen", "storage"]

    @pytest.mark.asyncio
    async def test_success_counts_and_close_called(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        good = tmp_path / "good.txt"
        good.write_text("alpha " * 30)
        other = tmp_path / "other.txt"
        other.write_text("beta " * 30)

        gen = _embedding_gen(batch_result=[[0.1] * 8], single_result=[0.2] * 8)
        st = _storage()
        closed: list[str] = []
        gen.close = MagicMock(side_effect=lambda: closed.append("gen"))
        st.close = MagicMock(side_effect=lambda: closed.append("storage"))

        import secondbrain.embedding as emb_mod
        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            emb_mod.EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(lambda cfg: gen),
        )
        monkeypatch.setattr(
            storage_mod.StorageFactory,
            "create_from_config",
            staticmethod(lambda cfg: st),
        )

        ingestor = AsyncDocumentIngestor()

        async def fake_process(
            file_path: Path, e_gen: Any, storage: Any, **_kwargs: Any
        ) -> bool:
            return file_path == good

        with patch.object(ingestor, "process_file_async", side_effect=fake_process):
            result = await ingestor.ingest_async(str(tmp_path))

        assert result == {
            "success": 1,
            "failed": 1,
            "failures": [
                (
                    str(other),
                    "No documents produced (file may be empty, image-only, "
                    "or extraction failed)",
                )
            ],
            "skipped": 0,
        }
        assert sorted(closed) == ["gen", "storage"]

    @pytest.mark.asyncio
    async def test_close_swallows_provider_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A raising close() must not mask the ingest result."""
        (tmp_path / "doc.txt").write_text("content " * 20)

        gen = _embedding_gen(batch_result=[[0.1] * 8])
        st = _storage()
        gen.close = MagicMock(side_effect=RuntimeError("gen close boom"))
        st.close = MagicMock(side_effect=RuntimeError("storage close boom"))

        import secondbrain.embedding as emb_mod
        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            emb_mod.EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(lambda cfg: gen),
        )
        monkeypatch.setattr(
            storage_mod.StorageFactory,
            "create_from_config",
            staticmethod(lambda cfg: st),
        )

        ingestor = AsyncDocumentIngestor()

        async def ok(_file_path: Path, _gen: Any, _st: Any, **_kwargs: Any) -> bool:
            return True

        with patch.object(ingestor, "process_file_async", side_effect=ok):
            result = await ingestor.ingest_async(str(tmp_path))

        assert result == {
            "success": 1,
            "failed": 0,
            "failures": [],
            "skipped": 0,
        }

    @pytest.mark.asyncio
    async def test_invalid_path_counts_as_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Collect raising ValueError and still closing both providers."""
        gen = _embedding_gen()
        st = _storage()

        import secondbrain.embedding as emb_mod
        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            emb_mod.EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(lambda cfg: gen),
        )
        monkeypatch.setattr(
            storage_mod.StorageFactory,
            "create_from_config",
            staticmethod(lambda cfg: st),
        )

        ingestor = AsyncDocumentIngestor()
        missing = tmp_path / "no-such-dir"

        with pytest.raises(ValueError):
            await ingestor.ingest_async(str(missing))

        assert gen.close.call_count == 1
        assert st.close.call_count == 1


class TestIngestAsyncFailureReasons:
    """ingest_async failures carry real captured causes, not just the generic one."""

    def _patch_providers(
        self,
        monkeypatch: pytest.MonkeyPatch,
        gen: Any,
        st: Any,
        closed: list[str],
    ) -> None:
        """Stub the embedding/storage factories and record close() calls."""
        gen.close = MagicMock(side_effect=lambda: closed.append("gen"))
        st.close = MagicMock(side_effect=lambda: closed.append("storage"))

        import secondbrain.embedding as emb_mod
        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            emb_mod.EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(lambda cfg: gen),
        )
        monkeypatch.setattr(
            storage_mod.StorageFactory,
            "create_from_config",
            staticmethod(lambda cfg: st),
        )

    @pytest.mark.asyncio
    async def test_storage_error_captures_real_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A raised storage error surfaces as "ValueError: ..." in failures."""
        good = tmp_path / "good.txt"
        good.write_text("good content")
        bad = tmp_path / "bad.txt"
        bad.write_text("bad content")

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_result=[[0.1] * 8])

        def store_side_effect(docs: list[dict[str, Any]]) -> list[str]:
            if docs and docs[0]["source_file"] == str(bad):
                raise ValueError("qdrant unreachable")
            return ["id1"]

        st = MagicMock(spec=["store_batch_async", "close"])
        st.store_batch_async = AsyncMock(side_effect=store_side_effect)

        closed: list[str] = []
        self._patch_providers(monkeypatch, gen, st, closed)

        def extract_by_name(_p: Path) -> list[dict[str, Any]]:
            return [{"text": "shared body text", "page": 1}]

        monkeypatch.setattr(ingestor, "_extract_text", extract_by_name)

        result = await ingestor.ingest_async(str(tmp_path))

        assert result["success"] == 1
        assert result["failed"] == 1
        assert result["failures"] == [(str(bad), "ValueError: qdrant unreachable")]
        assert result["skipped"] == 0
        assert sorted(closed) == ["gen", "storage"]

    @pytest.mark.asyncio
    async def test_extraction_error_captures_real_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A raised extraction error surfaces as "DocumentExtractionError: ..."."""
        doomed = tmp_path / "doomed.txt"
        doomed.write_text("doomed content")

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_result=[[0.1] * 8])
        st = _storage()

        closed: list[str] = []
        self._patch_providers(monkeypatch, gen, st, closed)

        def boom(_p: Path) -> list[dict[str, Any]]:
            raise DocumentExtractionError("bad pdf")

        monkeypatch.setattr(ingestor, "_extract_text", boom)

        result = await ingestor.ingest_async(str(doomed))

        assert result == {
            "success": 0,
            "failed": 1,
            "failures": [(str(doomed), "DocumentExtractionError: bad pdf")],
            "skipped": 0,
        }
        assert sorted(closed) == ["gen", "storage"]

    @pytest.mark.asyncio
    async def test_no_documents_still_gets_generic_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failing without a raised error keeps the generic no-documents reason."""
        empty = tmp_path / "empty.txt"
        empty.write_text("empty content")

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_result=[[0.1] * 8])
        st = _storage()

        closed: list[str] = []
        self._patch_providers(monkeypatch, gen, st, closed)

        def no_segments(_p: Path) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(ingestor, "_extract_text", no_segments)

        result = await ingestor.ingest_async(str(empty))

        assert result == {
            "success": 0,
            "failed": 1,
            "failures": [
                (
                    str(empty),
                    "No documents produced (file may be empty, image-only, "
                    "or extraction failed)",
                )
            ],
            "skipped": 0,
        }

    @pytest.mark.asyncio
    async def test_ingest_cancellation_propagates_and_records_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cancelling the ingest raises out; no failure is recorded for it."""
        (tmp_path / "doc.txt").write_text("cancellation target")

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_result=[[0.1] * 8])
        st = _storage()

        closed: list[str] = []
        self._patch_providers(monkeypatch, gen, st, closed)

        async def slow_process(*_args: Any, **_kwargs: Any) -> bool:
            await asyncio.sleep(3600)
            return True

        with patch.object(ingestor, "process_file_async", side_effect=slow_process):
            task = asyncio.create_task(ingestor.ingest_async(str(tmp_path)))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert task.cancelled() is True
        assert sorted(closed) == ["gen", "storage"]


class TestProcessFileAsyncBranches:
    """process_file_async success/empty/error contracts."""

    @pytest.mark.asyncio
    async def test_empty_segments_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"
        f.write_text("irrelevant")

        def empty_extract(_p: Path) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(ingestor, "_extract_text", empty_extract)
        assert await ingestor.process_file_async(f, MagicMock(), MagicMock()) is False

    @pytest.mark.asyncio
    async def test_extraction_error_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"
        reasons: dict[str, str] = {}

        def boom(_p: Path) -> list[dict[str, Any]]:
            raise DocumentExtractionError("bad pdf")

        monkeypatch.setattr(ingestor, "_extract_text", boom)
        ok = await ingestor.process_file_async(
            f, MagicMock(), MagicMock(), failure_reasons=reasons
        )
        assert ok is False
        assert reasons == {str(f): "DocumentExtractionError: bad pdf"}

    @pytest.mark.asyncio
    async def test_oserror_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"
        reasons: dict[str, str] = {}

        def boom(_p: Path) -> list[dict[str, Any]]:
            raise OSError("disk unavailable")

        monkeypatch.setattr(ingestor, "_extract_text", boom)
        ok = await ingestor.process_file_async(
            f, MagicMock(), MagicMock(), failure_reasons=reasons
        )
        assert ok is False
        assert reasons == {str(f): "OSError: disk unavailable"}

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"
        reasons: dict[str, str] = {}

        def boom(_p: Path) -> list[dict[str, Any]]:
            raise RuntimeError("something else exploded")

        monkeypatch.setattr(ingestor, "_extract_text", boom)
        ok = await ingestor.process_file_async(
            f, MagicMock(), MagicMock(), failure_reasons=reasons
        )
        assert ok is False
        assert reasons == {str(f): "RuntimeError: something else exploded"}

    @pytest.mark.asyncio
    async def test_nonstreaming_true_when_docs_stored(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_enabled", False, raising=False)
        monkeypatch.setattr(cfg, "embedding_batch_size", 8, raising=False)

        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"
        f.write_text("body " * 40)

        def one_seg(_p: Path) -> list[dict[str, Any]]:
            return [{"text": "body " * 40, "page": 1}]

        monkeypatch.setattr(ingestor, "_extract_text", one_seg)
        gen = _embedding_gen(batch_result=[[0.1] * 8])
        st = _storage()

        with caplog.at_level("ERROR"):
            ok = await ingestor.process_file_async(f, gen, st)

        assert ok is True
        assert st.store_batch_async.await_count == 1
        stored_docs = st.store_batch_async.await_args[0][0]
        assert stored_docs and stored_docs[0]["chunk_text"].startswith("body")
        assert not [r for r in caplog.records if r.levelno >= 30]

    @pytest.mark.asyncio
    async def test_nonstreaming_false_when_no_embeddings(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Batch and single embedding both fail -> no docs -> False."""
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_enabled", False, raising=False)
        monkeypatch.setattr(cfg, "embedding_batch_size", 8, raising=False)

        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"
        f.write_text("body " * 40)

        def one_seg(_p: Path) -> list[dict[str, Any]]:
            return [{"text": "body " * 40, "page": 1}]

        monkeypatch.setattr(ingestor, "_extract_text", one_seg)
        gen = _embedding_gen(
            batch_async=False, single_async=False
        )  # triggers TypeErrors both levels
        st = _storage()

        ok = await ingestor.process_file_async(f, gen, st)
        assert ok is False
        st.store_batch_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_streaming_true_when_docs_streamed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_enabled", True, raising=False)
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 2, raising=False)

        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"

        def segs(_p: Path) -> list[dict[str, Any]]:
            return [{"text": f"segment {n} text", "page": 1} for n in range(3)]

        monkeypatch.setattr(ingestor, "_extract_text", segs)
        gen = _embedding_gen(batch_result=[[0.1] * 8, [0.2] * 8])
        st = _storage()

        ok = await ingestor.process_file_async(f, gen, st)
        assert ok is True
        assert st.store_batch_async.await_count >= 1

    @pytest.mark.asyncio
    async def test_streaming_false_when_all_embeddings_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_enabled", True, raising=False)
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 2, raising=False)

        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"

        def segs(_p: Path) -> list[dict[str, Any]]:
            return [{"text": "only segment", "page": 1}]

        monkeypatch.setattr(ingestor, "_extract_text", segs)
        gen = _embedding_gen(batch_async=False, single_async=False)
        st = _storage()

        ok = await ingestor.process_file_async(f, gen, st)
        assert ok is False
        st.store_batch_async.assert_not_called()


class TestStreamingChunkLoop:
    """_stream_process_chunks_async segment filtering and batch flushing."""

    @pytest.mark.asyncio
    async def test_blank_and_duplicate_segments_skipped(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 10, raising=False)

        ingestor = AsyncDocumentIngestor()
        segments = [
            {"text": "   \n\t", "page": 1},  # blank -> skipped
            {"text": "unique segment alpha", "page": 1},
            {"text": "Unique Segment ALPHA", "page": 1},  # dup after normalize
            {"text": "unique segment beta", "page": 2},
        ]

        captured: list[list[dict[str, Any]]] = []

        async def fake_store(
            _fp: Path, batch: list[dict[str, Any]], _gen: Any, _st: Any
        ) -> int:
            captured.append(list(batch))
            return len(batch)

        monkeypatch.setattr(ingestor, "_store_embedding_batch_async", fake_store)

        docs = await ingestor._stream_process_chunks_async(
            tmp_path / "doc.txt", segments, MagicMock(), MagicMock()
        )

        assert docs == 2
        assert len(captured) == 1
        texts = [c["text"] for c in captured[0]]
        assert texts == ["unique segment alpha", "unique segment beta"]

    @pytest.mark.asyncio
    async def test_batches_flush_at_streaming_batch_size(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 2, raising=False)

        ingestor = AsyncDocumentIngestor()
        segments = [{"text": f"seg {n}", "page": 1} for n in range(5)]

        batch_sizes: list[int] = []

        async def fake_store(
            _fp: Path, batch: list[dict[str, Any]], _gen: Any, _st: Any
        ) -> int:
            batch_sizes.append(len(batch))
            return len(batch)

        monkeypatch.setattr(ingestor, "_store_embedding_batch_async", fake_store)

        docs = await ingestor._stream_process_chunks_async(
            tmp_path / "doc.txt", segments, MagicMock(), MagicMock()
        )

        assert docs == 5
        assert batch_sizes == [2, 2, 1]


class TestEmbeddingFallbacks:
    """Batch->single fallback and no-async-support TypeErrors."""

    @pytest.mark.asyncio
    async def test_batch_failure_falls_back_to_single_async(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 10, raising=False)

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(
            batch_result=RuntimeError("batch exploded"),
            single_result=[0.3] * 8,
        )
        st = _storage()

        result = await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"),
            [_chunk("fallback chunk alpha"), _chunk("fallback chunk beta")],
            gen,
            st,
        )

        assert result == 2
        gen.generate_batch_async.assert_awaited_once()
        assert gen.generate_async.await_count == 2
        stored = st.store_batch_async.await_args[0][0]
        assert {d["chunk_text"] for d in stored} == {
            "fallback chunk alpha",
            "fallback chunk beta",
        }

    @pytest.mark.asyncio
    async def test_batch_failure_single_fails_skips_chunk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 10, raising=False)

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(
            batch_result=RuntimeError("batch exploded"),
            single_result=RuntimeError("single exploded"),
        )
        st = _storage()

        result = await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"),
            [_chunk("doomed chunk")],
            gen,
            st,
        )

        assert result == 0
        st.store_batch_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_batch_async_no_single_typeerror_both_levels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Generator lacking both async methods -> TypeErrors swallowed -> 0 docs."""
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 10, raising=False)

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_async=False, single_async=False)
        st = _storage()

        result = await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"),
            [_chunk("needs async gen")],
            gen,
            st,
        )

        assert result == 0
        st.store_batch_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_embedding_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 10, raising=False)

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_result=[[0.9] * 8])
        st = _storage()

        chunk = _chunk("cache hit chunk")
        await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"), [chunk], gen, st
        )
        first_calls = gen.generate_batch_async.await_count

        # Second call with the same text must hit the in-memory cache.
        await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"), [_chunk("cache hit chunk")], gen, st
        )
        assert gen.generate_batch_async.await_count == first_calls

    @pytest.mark.asyncio
    async def test_nonstreaming_cache_path_reuses_cached_embedding(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """_generate_embeddings_with_cache_async cache-hit branch (line 376)."""
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_enabled", False, raising=False)
        monkeypatch.setattr(cfg, "embedding_batch_size", 8, raising=False)

        ingestor = AsyncDocumentIngestor()
        f = tmp_path / "doc.txt"
        f.write_text("cached body text")

        gen = _embedding_gen(batch_result=[[0.5] * 8])

        def one_seg(_p: Path) -> list[dict[str, Any]]:
            return [{"text": "cached body text", "page": 1}]

        monkeypatch.setattr(ingestor, "_extract_text", one_seg)
        st = _storage()

        first = await ingestor.process_file_async(f, gen, st)
        assert first is True

        # Second ingest of identical text: cache hit path populates the mapping.
        second = await ingestor.process_file_async(f, gen, st)
        assert second is True
        assert gen.generate_batch_async.await_count == 1

    @pytest.mark.asyncio
    async def test_generate_embeddings_cache_async_batch_failure_single_recovers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Batch path fails, per-chunk generate_async saves the day (lines 404-429)."""
        cfg = config_obj()
        monkeypatch.setattr(cfg, "embedding_batch_size", 8, raising=False)

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(
            batch_result=RuntimeError("batch boom"),
            single_result=[0.7] * 8,
        )
        chunks = [_chunk("recover chunk one"), _chunk("recover chunk two")]

        mapping = await ingestor._generate_embeddings_with_cache_async(chunks, gen)

        assert len(mapping) == 2
        assert all(v == [0.7] * 8 for v in mapping.values())
        assert gen.generate_async.await_count == 2


class TestContextManagerAndDuplicates:
    """__aenter__/__aexit__ and dedup-skip inside batch storage."""

    @pytest.mark.asyncio
    async def test_async_context_manager_yields_self(self) -> None:
        ingestor = AsyncDocumentIngestor()
        async with ingestor as entered:
            assert entered is ingestor

    @pytest.mark.asyncio
    async def test_aexit_passes_without_suppressing(self) -> None:
        ingestor = AsyncDocumentIngestor()
        async with ingestor:
            pass  # __aexit__ runs implicitly; no suppression expected

    @pytest.mark.asyncio
    async def test_duplicate_doc_key_stored_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same (file, page, hash) twice in one batch stores a single doc."""
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 10, raising=False)

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_result=[[0.1] * 8])
        st = _storage()

        dup = _chunk("duplicated doc chunk")
        result = await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"), [dup, dict(dup)], gen, st
        )

        assert result == 1
        stored = st.store_batch_async.await_args[0][0]
        assert len(stored) == 1

    @pytest.mark.asyncio
    async def test_pages_occupy_sequential_page_pos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = config_obj()
        monkeypatch.setattr(cfg, "streaming_chunk_batch_size", 10, raising=False)

        ingestor = AsyncDocumentIngestor()
        gen = _embedding_gen(batch_result=[[0.1] * 8, [0.2] * 8, [0.3] * 8])
        st = _storage()

        chunks = [
            _chunk("page one alpha", page=1),
            _chunk("page one beta", page=1),
            _chunk("page two alpha", page=2),
        ]
        await ingestor._store_embedding_batch_async(
            Path("/tmp/sample.pdf"), chunks, gen, st
        )

        stored = st.store_batch_async.await_args[0][0]
        assert [d["page_pos"] for d in stored] == [0, 1, 0]
