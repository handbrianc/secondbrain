"""Unit tests for the payload-refresh + audio-topic ingestor wiring (tasks 9/10).

Covers design §6.4 (both ingest paths call ``refresh_structural_payload``
after store / on skip) and design §5's parent-side audio topic
segmentation hook, at helper level and through the real sync/async paths
with faked worker boundaries.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from secondbrain.config import config
from secondbrain.document.ingestor import _async as async_ingestor_module
from secondbrain.document.ingestor._async import AsyncDocumentIngestor
from secondbrain.document.ingestor._sync import DocumentIngestor
from secondbrain.rag.providers.factory import LLMProviderFactory
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    StructureNode,
    StructureStore,
)

pytestmark = pytest.mark.unit


def segment_tree(source_file: str) -> DocumentStructure:
    """A two-segment audio tree."""
    return DocumentStructure(
        source_file=source_file,
        nodes=[
            StructureNode(
                node_id="seg01",
                kind="segment",
                level=1,
                title="welcome everyone",
                t_start=0.0,
                t_end=30.0,
                heading_path="Segment 01",
            ),
            StructureNode(
                node_id="seg02",
                kind="segment",
                level=1,
                title="rockets discussion",
                t_start=30.0,
                t_end=60.0,
                heading_path="Segment 02",
            ),
        ],
        sources={"audio": True},
    )


def chapter_tree(source_file: str) -> DocumentStructure:
    return DocumentStructure(
        source_file=source_file,
        nodes=[
            StructureNode(
                node_id="ch01",
                kind="chapter",
                level=1,
                number="1",
                title="Installing",
                page_start=1,
                page_end=9,
                heading_path="Chapter 1 — Installing",
            )
        ],
        sources={"heading_hierarchy": True},
    )


class RecordingStorage:
    """Stands in for vector storage; records refresh/store calls."""

    def __init__(self) -> None:
        self.refresh_calls: list[tuple[str, DocumentStructure]] = []
        self.stored_batches: list[list[dict[str, Any]]] = []
        self.refresh_error: Exception | None = None

    def store_batch(self, documents: list[dict[str, Any]]) -> int:
        self.stored_batches.append(documents)
        return len(documents)

    async def store_batch_async(self, documents: list[dict[str, Any]]) -> int:
        self.stored_batches.append(documents)
        return len(documents)

    def refresh_structural_payload(
        self, source_file: str, structure: DocumentStructure
    ) -> int:
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refresh_calls.append((source_file, structure))
        return 3


class FakeLLM:
    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        return "Space Rockets"


class FailingLLM:
    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        raise RuntimeError("llm down")


def pin_llm_factory(monkeypatch: pytest.MonkeyPatch, llm: Any) -> list[Any]:
    """Pin LLMProviderFactory.create_from_config; returns the created list."""
    created: list[Any] = []

    def fake_factory(cfg: Any) -> Any:
        created.append(cfg)
        return llm

    monkeypatch.setattr(
        LLMProviderFactory, "create_from_config", staticmethod(fake_factory)
    )
    return created


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------


class TestSyncRefreshHelper:
    @pytest.fixture
    def ingestor(self) -> DocumentIngestor:
        return DocumentIngestor()

    def test_calls_refresh_with_source_and_structure(
        self, tmp_path: Path, ingestor: DocumentIngestor
    ) -> None:
        tree = chapter_tree(str(tmp_path / "book.epub"))
        storage = RecordingStorage()
        ingestor._refresh_structural_payload({"structure": tree}, storage)
        assert storage.refresh_calls == [(tree.source_file, tree)]

    def test_no_structure_is_a_no_op(self, ingestor: DocumentIngestor) -> None:
        storage = RecordingStorage()
        ingestor._refresh_structural_payload({"structure": None}, storage)
        assert storage.refresh_calls == []

    def test_storage_without_capability_is_a_no_op(
        self, tmp_path: Path, ingestor: DocumentIngestor
    ) -> None:
        tree = chapter_tree(str(tmp_path / "book.epub"))
        ingestor._refresh_structural_payload({"structure": tree}, None)
        ingestor._refresh_structural_payload({"structure": tree}, object())

    def test_refresh_failure_never_raises(
        self, tmp_path: Path, ingestor: DocumentIngestor
    ) -> None:
        tree = chapter_tree(str(tmp_path / "book.epub"))
        storage = RecordingStorage()
        storage.refresh_error = RuntimeError("qdrant down")
        ingestor._refresh_structural_payload({"structure": tree}, storage)


class TestSyncAudioTopicHook:
    @pytest.fixture
    def ingestor(self) -> DocumentIngestor:
        return DocumentIngestor()

    @pytest.fixture
    def store(self, tmp_path: Path) -> StructureStore:
        return StructureStore(db_path=str(tmp_path / "structures.db"))

    def _result(self, file_path: Path, tree: DocumentStructure) -> dict[str, Any]:
        return {
            "success": True,
            "file_path": file_path,
            "documents": [
                {"chunk_text": "transcript text about engines"},
                {"chunk_text": "more transcript text"},
            ],
            "structure": tree,
        }

    def test_fills_audio_segments_and_re_saves(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
        store: StructureStore,
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        tree = segment_tree(str(file_path))
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        created = pin_llm_factory(monkeypatch, FakeLLM())
        try:
            ingestor._segment_audio_topics(self._result(file_path, tree))
            loaded = store.load_tree(str(file_path))
            assert loaded is not None
            assert [row.title for row in loaded.audio_segments] == [
                "Space Rockets",
                "Space Rockets",
            ]
            assert created, "the LLM provider must be built once"
        finally:
            store.close()

    def test_flag_off_skips_segmentation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        monkeypatch.setattr(config(), "audio_topic_segmentation_enabled", False)
        created = pin_llm_factory(monkeypatch, FakeLLM())
        ingestor._segment_audio_topics(
            self._result(tmp_path / "talk.m4a", segment_tree(str(tmp_path)))
        )
        assert created == []

    def test_non_audio_tree_never_reaches_the_llm(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        created = pin_llm_factory(monkeypatch, FakeLLM())
        ingestor._segment_audio_topics(
            self._result(tmp_path / "book.pdf", chapter_tree(str(tmp_path)))
        )
        assert created == []

    def test_llm_failure_leaves_tree_untitled(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
        store: StructureStore,
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        tree = segment_tree(str(file_path))
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        pin_llm_factory(monkeypatch, FailingLLM())
        try:
            # Real flow: _persist_worker_structure saves the tree before the
            # topic hook runs; a failed LLM must leave those rows empty.
            store.save_structure(tree)
            ingestor._segment_audio_topics(self._result(file_path, tree))
            loaded = store.load_tree(str(file_path))
            assert loaded is not None
            assert loaded.audio_segments == []
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Sync path wiring (real _process_parallel_with_progress)
# ---------------------------------------------------------------------------


class TestSyncPathWiring:
    def test_refresh_and_topic_hook_run_per_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ingestor = DocumentIngestor()
        file_path = tmp_path / "talk.m4a"
        tree = segment_tree(str(file_path))
        result = {
            "success": True,
            "file_path": file_path,
            "documents": [{"chunk_text": "transcript text"}],
            "error": None,
            "skipped": False,
            "structure": tree,
        }
        monkeypatch.setattr(
            "secondbrain.document.processor._extract_chunk_and_embed_file",
            lambda *args: result,
        )
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        storage = RecordingStorage()
        pin_llm_factory(monkeypatch, FakeLLM())
        try:
            successful, failed, _reasons, _skipped = (
                ingestor._process_parallel_with_progress(
                    [file_path],
                    embedding_gen=None,
                    storage=storage,
                    max_workers=1,
                    pool="thread",
                )
            )
            assert (successful, failed) == (1, 0)
            assert storage.refresh_calls == [(str(file_path), tree)]
            loaded = store.load_tree(str(file_path))
            assert loaded is not None
            # One AudioSegment row per timestamped segment node (2 nodes,
            # each its own window here), all titled from the one LLM reply.
            assert [row.title for row in loaded.audio_segments] == [
                "Space Rockets",
                "Space Rockets",
            ]
        finally:
            store.close()

    def test_refresh_runs_on_skip_outcome_with_storage_none(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """storage=None (tests/mocks) must not break the skip path."""
        ingestor = DocumentIngestor()
        file_path = tmp_path / "book.epub"
        monkeypatch.setattr(
            "secondbrain.document.processor._extract_chunk_and_embed_file",
            lambda *args: {
                "success": True,
                "file_path": file_path,
                "documents": [],
                "error": None,
                "skipped": True,
                "extracted_chunks": 2,
                "structure": chapter_tree(str(file_path)),
            },
        )
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        try:
            successful, failed, _reasons, _skipped = (
                ingestor._process_parallel_with_progress(
                    [file_path],
                    embedding_gen=None,
                    storage=None,
                    max_workers=1,
                    pool="thread",
                )
            )
            assert (successful, failed) == (1, 0)
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Async helpers + path wiring
# ---------------------------------------------------------------------------


class TestAsyncCaptureReturnsStructure:
    @pytest.fixture
    def ingestor(self) -> AsyncDocumentIngestor:
        return AsyncDocumentIngestor()

    async def test_capture_returns_persisted_tree(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.epub"
        tree = chapter_tree(str(file_path))
        monkeypatch.setattr(
            async_ingestor_module, "capture_structure", lambda *a, **k: tree
        )
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        try:
            returned = await ingestor._capture_and_persist_structure_async(
                file_path, []
            )
            assert returned is tree
            assert store.has_tree(str(file_path))
        finally:
            store.close()

    async def test_capture_without_tree_returns_none(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        monkeypatch.setattr(
            async_ingestor_module, "capture_structure", lambda *a, **k: None
        )
        returned = await ingestor._capture_and_persist_structure_async(
            tmp_path / "flat.epub", []
        )
        assert returned is None

    async def test_audio_hands_the_asr_shape_to_the_dispatcher(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        shape = SimpleNamespace(texts=[])
        received: list[tuple[Any, str]] = []

        def fake_capture(
            path: Path, docling_doc: Any = None, file_type: str = ""
        ) -> None:
            received.append((docling_doc, file_type))
            return None

        monkeypatch.setattr(async_ingestor_module, "capture_structure", fake_capture)

        returned = await ingestor._capture_and_persist_structure_async(
            file_path, [shape]
        )

        # Audio (design §5): the dispatcher gets the extracted ASR capture
        # shape carried by the sink — the ASR document itself is already
        # released — with the audio file-type hint; nothing was captured, so
        # nothing is persisted.
        assert received == [(shape, "audio")]
        assert returned is None

    async def test_non_audio_still_hands_the_heading_sink_to_the_dispatcher(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.pdf"
        tree = chapter_tree(str(file_path))
        received: list[tuple[Any, str]] = []

        def fake_capture(
            path: Path, docling_doc: Any = None, file_type: str = ""
        ) -> None:
            received.append((docling_doc, file_type))
            return None

        monkeypatch.setattr(async_ingestor_module, "capture_structure", fake_capture)

        returned = await ingestor._capture_and_persist_structure_async(
            file_path, [tree]
        )

        # Regression guard: a heading part keeps the list-shaped docling
        # input the dispatcher merges (design §6).
        assert received == [([tree], "pdf")]
        assert returned is None


class TestAsyncRefreshAndTopicHelpers:
    @pytest.fixture
    def ingestor(self) -> AsyncDocumentIngestor:
        return AsyncDocumentIngestor()

    async def test_refresh_helper_records_and_tolerates_failures(
        self, tmp_path: Path, ingestor: AsyncDocumentIngestor
    ) -> None:
        tree = chapter_tree(str(tmp_path / "book.epub"))
        storage = RecordingStorage()
        await ingestor._refresh_structure_payload_async(tree, storage)
        assert storage.refresh_calls == [(tree.source_file, tree)]

        storage.refresh_error = RuntimeError("down")
        await ingestor._refresh_structure_payload_async(tree, storage)  # warns only
        await ingestor._refresh_structure_payload_async(None, storage)
        await ingestor._refresh_structure_payload_async(tree, None)

    async def test_topic_helper_fills_segments(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        tree = segment_tree(str(file_path))
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        pin_llm_factory(monkeypatch, FakeLLM())
        try:
            await ingestor._segment_audio_topics_async(
                file_path,
                tree,
                [{"text": "transcript text", "page": 1}],
            )
            loaded = store.load_tree(str(file_path))
            assert loaded is not None
            assert [row.title for row in loaded.audio_segments] == [
                "Space Rockets",
                "Space Rockets",
            ]
        finally:
            store.close()

    async def test_topic_helper_flag_off_is_a_no_op(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        monkeypatch.setattr(config(), "audio_topic_segmentation_enabled", False)
        created = pin_llm_factory(monkeypatch, FakeLLM())
        await ingestor._segment_audio_topics_async(
            tmp_path / "talk.m4a",
            segment_tree(str(tmp_path)),
            [{"text": "transcript text", "page": 1}],
        )
        assert created == []


class TestAsyncPathWiring:
    """process_file_async refreshes after store and on the full-skip return."""

    @pytest.fixture
    def ingestor(self) -> AsyncDocumentIngestor:
        return AsyncDocumentIngestor()

    def _wire(
        self,
        ingestor: AsyncDocumentIngestor,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[Path, StructureStore, DocumentStructure]:
        file_path = tmp_path / "book.epub"
        tree = chapter_tree(str(file_path))

        def fake_extract(
            path: Path, structure_sink: list[DocumentStructure] | None = None
        ) -> list[dict[str, Any]]:
            return [{"text": "body text", "page": 1}]

        monkeypatch.setattr(ingestor, "_extract_text", fake_extract)
        monkeypatch.setattr(
            async_ingestor_module, "capture_structure", lambda *a, **k: tree
        )
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        monkeypatch.setattr(config(), "streaming_enabled", True)
        ingestor._stream_process_chunks_async = AsyncMock(return_value=2)  # type: ignore[method-assign]
        return file_path, store, tree

    async def test_streaming_store_triggers_refresh(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        storage = RecordingStorage()
        file_path, store, tree = self._wire(ingestor, tmp_path, monkeypatch)
        try:
            ok = await ingestor.process_file_async(
                file_path,
                embedding_gen=None,
                storage=storage,
                skip_existing=False,
            )
            assert ok is True
            assert storage.refresh_calls == [(str(file_path), tree)]
        finally:
            store.close()

    async def test_batch_store_triggers_refresh(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        storage = RecordingStorage()
        file_path, store, tree = self._wire(ingestor, tmp_path, monkeypatch)
        monkeypatch.setattr(config(), "streaming_enabled", False)
        monkeypatch.setattr(
            ingestor,
            "_build_documents_with_embeddings_async",
            AsyncMock(return_value=[{"chunk_id": "c1"}]),
        )
        try:
            ok = await ingestor.process_file_async(
                file_path,
                embedding_gen=None,
                storage=storage,
                skip_existing=False,
            )
            assert ok is True
            assert storage.refresh_calls == [(str(file_path), tree)]
        finally:
            store.close()

    async def test_full_skip_triggers_refresh(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        storage = RecordingStorage()
        file_path, store, tree = self._wire(ingestor, tmp_path, monkeypatch)
        monkeypatch.setattr(
            "secondbrain.document.ingestor._async._query_existing_hashes",
            lambda s, hashes: set(hashes),
        )
        try:
            ok = await ingestor.process_file_async(
                file_path,
                embedding_gen=None,
                storage=storage,
                skip_existing=True,
            )
            assert ok is True
            assert storage.refresh_calls == [(str(file_path), tree)]
        finally:
            store.close()
