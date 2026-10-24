"""Unit tests for structure capture wiring in the ingest workers (lane 1a).

Covers the three contract points of design §6:

* the processor worker captures the tree during parsing and attaches it to
  ``result["structure"]`` on EVERY outcome (success / all-skipped /
  treeless / fast-path / failure),
* the sync ingestor persists the worker's tree exactly once per file,
* the async ingestor self-captures (it never consumes worker payloads) and
  persists through the same store.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from secondbrain.config import config
from secondbrain.document import processor
from secondbrain.document.ingestor._async import AsyncDocumentIngestor
from secondbrain.document.ingestor._sync import DocumentIngestor
from secondbrain.storage.structure_sqlite import (
    AudioSegment,
    DocumentStructure,
    StructureNode,
    StructureStore,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def doc_item(
    text: str,
    label: str = "section_header",
    level: int = 1,
    page: int | None = None,
) -> Any:
    """A docling-shaped text item (string label, prov page list)."""
    prov = [SimpleNamespace(page_no=page)] if page is not None else []
    return SimpleNamespace(text=text, label=label, level=level, prov=prov)


class FakeConverter:
    """Stands in for the shared docling converter."""

    def __init__(self, document: Any) -> None:
        self._document = document

    def convert(self, file_path: Path, page_range: Any = None) -> Any:
        return SimpleNamespace(
            document=self._document,
            input=SimpleNamespace(_backend=None),
        )


class FakeEmbeddingModel:
    """Dense-enough embeddings without any model download."""

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


def heading_document() -> Any:
    """A fabricated docling document with two section headers."""
    return SimpleNamespace(
        texts=[
            doc_item("Body paragraph about installing", label="text", level=0, page=1),
            doc_item("Chapter 1 — Installing", level=1, page=2),
            doc_item("1.2 Setup", level=2, page=4),
        ]
    )


def narrative_document() -> Any:
    """A fabricated docling document with no section headers (treeless)."""
    return SimpleNamespace(
        texts=[doc_item("Just prose, no headers", label="text", level=0, page=1)]
    )


def asr_item(
    text: str,
    start: float | None = None,
    end: float | None = None,
) -> Any:
    """A docling-shaped ASR segment: TextItem + TrackSource timestamps.

    Same shape :mod:`secondbrain.document.structure_capture`'s audio branch
    reads (``text`` plus numeric ``start_time``/``end_time`` on ``source``);
    items without timestamps degrade like the real untimed ASR output.
    """
    source = (
        [SimpleNamespace(start_time=start, end_time=end)]
        if start is not None and end is not None
        else []
    )
    return SimpleNamespace(text=text, label="TEXT", source=source, prov=[])


def asr_document(*items: Any) -> Any:
    """A fabricated ASR docling document (transcript with timestamps)."""
    return SimpleNamespace(texts=list(items))


class UnloadingConverter(FakeConverter):
    """FakeConverter whose backend.unload() frees the ASR document.

    Simulates the worker's release pattern: after ``unload()`` the
    document's ``texts`` are gone (dead memory). Anything that extracts the
    capture input AFTER the release would see no texts, so a correct tree
    proves the extraction happened before the release.
    """

    def __init__(self, document: Any) -> None:
        super().__init__(document)
        self.unload_calls = 0

    def convert(self, file_path: Path, page_range: Any = None) -> Any:
        converter = self

        class _Backend:
            def unload(self) -> None:
                converter.unload_calls += 1
                converter._document.texts = None

        return SimpleNamespace(
            document=self._document,
            input=SimpleNamespace(_backend=_Backend()),
        )


def run_worker(
    file_path: Path,
    document: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    skip_existing: bool = False,
    fast_segments: list[dict[str, Any]] | None = None,
    converter: Any | None = None,
) -> dict[str, Any]:
    """Run the real worker with docling/embedding boundaries faked."""
    monkeypatch.setattr(
        "secondbrain.document.fast_text.try_fast_pdf_extraction",
        (lambda *a, **k: fast_segments) if fast_segments else (lambda *a, **k: None),
    )
    if fast_segments is None:
        monkeypatch.setattr(
            "secondbrain.document.docling_factory.get_converter_for_path",
            lambda path: (
                converter if converter is not None else FakeConverter(document)
            ),
        )
    else:

        def _docling_must_not_run(path: Path) -> Any:
            raise AssertionError("docling must not run on the fast path")

        monkeypatch.setattr(
            "secondbrain.document.docling_factory.get_converter_for_path",
            _docling_must_not_run,
        )
    from secondbrain.embedding import EmbeddingProviderFactory

    monkeypatch.setattr(
        EmbeddingProviderFactory,
        "create_from_config",
        staticmethod(lambda cfg: FakeEmbeddingModel()),
    )
    return processor._extract_chunk_and_embed_file(
        str(file_path), 100, 10, None, "test-model", None, skip_existing, False
    )


def chapter_tree(source_file: str) -> DocumentStructure:
    """A one-node tree for the persist tests."""
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


# ---------------------------------------------------------------------------
# Worker attach (sync pool worker)
# ---------------------------------------------------------------------------


class TestWorkerAttachesStructure:
    """_extract_chunk_and_embed_file result payloads carry "structure"."""

    def test_success_payload_carries_captured_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "book.epub"
        file_path.write_bytes(b"epub-bytes")
        result = run_worker(file_path, heading_document(), monkeypatch)

        assert result["success"] is True
        structure = result["structure"]
        assert structure is not None
        assert structure.source_file == str(file_path)
        ids = [n.node_id for n in structure.nodes]
        assert ids == ["ch01", "sec01.02"]
        section = structure.nodes[1]
        assert section.parent_id == "ch01"
        assert result["documents"], "documents must still be produced"
        assert result["documents"][0]["file_type"] == "unknown"

    @pytest.mark.parametrize("skip_count", [0, 1, 2])
    def test_transcript_and_time_bounds_survive_embedding_dedup(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        skip_count: int,
    ) -> None:
        import hashlib

        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        texts = ["welcome everyone to the show", "today we discuss rockets"]
        monkeypatch.setattr(processor, "chunk_segments", lambda segments, *a: segments)
        monkeypatch.setattr(
            processor,
            "_existing_text_hashes",
            lambda hashes: {
                hashlib.sha256(text.encode()).hexdigest() for text in texts[:skip_count]
            },
        )
        result = run_worker(
            file_path,
            asr_document(
                asr_item(texts[0], 0.0, 30.0),
                asr_item(texts[1], 30.0, 60.0),
            ),
            monkeypatch,
            skip_existing=True,
        )

        assert result["success"] is True
        assert result["audio_transcript"] == texts
        assert len(result["documents"]) == 2 - skip_count
        for index, document in enumerate(result["documents"], start=skip_count):
            assert document["t_start"] == index * 30.0
            assert document["t_end"] == (index + 1) * 30.0
            assert document["node_id"] == f"seg{index + 1:02}"
            assert document["chapter_id"] == document["node_id"]

    def test_all_skipped_payload_still_carries_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "book.epub"
        file_path.write_bytes(b"epub-bytes")
        monkeypatch.setattr(
            processor, "_existing_text_hashes", lambda hashes: set(hashes)
        )
        result = run_worker(
            file_path, heading_document(), monkeypatch, skip_existing=True
        )

        # The early-skip return (processor.py) must NOT drop the tree:
        # re-ingesting an already-stored document still records its structure.
        assert result["skipped"] is True
        assert result["documents"] == []
        assert result["structure"] is not None
        assert [n.node_id for n in result["structure"].nodes] == ["ch01", "sec01.02"]

    def test_treeless_document_yields_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "flat.epub"
        file_path.write_bytes(b"epub-bytes")
        result = run_worker(file_path, narrative_document(), monkeypatch)

        assert result["success"] is True
        assert result["structure"] is None

    def test_fast_pdf_path_has_no_docling_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "fast.pdf"
        file_path.write_bytes(b"not really a pdf")
        result = run_worker(
            file_path,
            heading_document(),
            monkeypatch,
            fast_segments=[{"text": "hello world", "page": 1}],
        )

        assert result["success"] is True
        # Garbage PDF bytes: outline + label capture fail → empty merge → None.
        assert result["structure"] is None

    def test_exception_payload_still_carries_partial_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "book.epub"
        file_path.write_bytes(b"epub-bytes")
        monkeypatch.setattr(
            "secondbrain.document.fast_text.try_fast_pdf_extraction",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "secondbrain.document.docling_factory.get_converter_for_path",
            lambda path: FakeConverter(heading_document()),
        )
        from secondbrain.embedding import EmbeddingProviderFactory

        def explode(cfg: Any) -> Any:
            raise RuntimeError("no embeddings today")

        monkeypatch.setattr(
            EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(explode),
        )
        result = processor._extract_chunk_and_embed_file(
            str(file_path), 100, 10, None, "test-model", None, False, False
        )

        # The capture already happened before the embedding failure; the
        # exception payload must still carry it so the ingestor can persist.
        assert result["success"] is False
        assert result["structure"] is not None
        assert result["structure"].source_file == str(file_path)


# ---------------------------------------------------------------------------
# Sync ingestor persist
# ---------------------------------------------------------------------------


class TestSyncPersist:
    """_process_parallel_with_progress persists each worker tree once."""

    @pytest.fixture
    def ingestor(self) -> DocumentIngestor:
        return DocumentIngestor()

    def _run(
        self,
        ingestor: DocumentIngestor,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        result: dict[str, Any],
    ) -> StructureStore:
        file_path = tmp_path / "book.epub"
        calls: list[tuple[Any, ...]] = []

        def fake_worker(*args: Any) -> dict[str, Any]:
            calls.append(args)
            return result

        monkeypatch.setattr(
            "secondbrain.document.processor._extract_chunk_and_embed_file",
            fake_worker,
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
            assert (successful, failed) == (
                1 if result.get("success") else 0,
                0 if result.get("success") else 1,
            )
            assert len(calls) == 1, "the worker must run exactly once"
        except BaseException:
            store.close()
            raise
        return store

    def test_persists_on_skip_outcome(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.epub"
        tree = chapter_tree(str(file_path))
        store = self._run(
            ingestor,
            tmp_path,
            monkeypatch,
            {
                "success": True,
                "file_path": file_path,
                "documents": [],
                "error": None,
                "skipped": True,
                "extracted_chunks": 3,
                "structure": tree,
            },
        )
        try:
            assert store.has_tree(str(file_path))
            loaded = store.load_tree(str(file_path))
            assert loaded is not None
            assert loaded.nodes == tree.nodes
        finally:
            store.close()

    def test_persists_on_failure_outcome(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.epub"
        tree = chapter_tree(str(file_path))
        store = self._run(
            ingestor,
            tmp_path,
            monkeypatch,
            {
                "success": False,
                "file_path": file_path,
                "documents": [],
                "error": "RuntimeError: boom",
                "structure": tree,
            },
        )
        try:
            assert store.has_tree(str(file_path))
        finally:
            store.close()

    def test_treeless_worker_persists_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.epub"
        store = self._run(
            ingestor,
            tmp_path,
            monkeypatch,
            {
                "success": False,
                "file_path": file_path,
                "documents": [],
                "error": "RuntimeError: boom",
                "structure": None,
            },
        )
        try:
            assert store.has_tree(str(file_path)) is False
        finally:
            store.close()

    def test_broken_store_never_fails_ingest(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.epub"
        monkeypatch.setattr(
            "secondbrain.document.processor._extract_chunk_and_embed_file",
            lambda *args: {
                "success": True,
                "file_path": file_path,
                "documents": [],
                "error": None,
                "skipped": True,
                "structure": chapter_tree(str(file_path)),
            },
        )
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: None)
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


# ---------------------------------------------------------------------------
# Async ingestor self-capture
# ---------------------------------------------------------------------------


class TestAsyncCaptureAndPersist:
    """process_file_async captures + persists via _extract_text's sink."""

    @pytest.fixture
    def ingestor(self) -> AsyncDocumentIngestor:
        return AsyncDocumentIngestor()

    @pytest.fixture
    def structure_store(self, tmp_path: Path) -> StructureStore:
        return StructureStore(db_path=str(tmp_path / "structures.db"))

    def _patch_store(
        self,
        ingestor: AsyncDocumentIngestor,
        monkeypatch: pytest.MonkeyPatch,
        store: StructureStore | None,
    ) -> None:
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)

    @staticmethod
    def _pin_streaming(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
        """Pin cfg.streaming_enabled so tests are environment-independent."""
        from secondbrain.config import config

        monkeypatch.setattr(config(), "streaming_enabled", enabled)

    def _fake_extract(
        self,
        ingestor: AsyncDocumentIngestor,
        monkeypatch: pytest.MonkeyPatch,
        segments: list[dict[str, Any]],
        part: DocumentStructure | None,
    ) -> None:
        def fake_extract(
            file_path: Path, structure_sink: list[DocumentStructure] | None = None
        ) -> list[dict[str, Any]]:
            if part is not None and structure_sink is not None:
                structure_sink.append(part)
            return segments

        monkeypatch.setattr(ingestor, "_extract_text", fake_extract)

    async def test_persists_captured_tree(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
        structure_store: StructureStore,
    ) -> None:
        file_path = tmp_path / "book.epub"
        part = chapter_tree(str(file_path))
        self._fake_extract(
            ingestor, monkeypatch, [{"text": "body text", "page": 1}], part
        )
        self._patch_store(ingestor, monkeypatch, structure_store)
        self._pin_streaming(monkeypatch, True)
        ingestor._stream_process_chunks_async = AsyncMock(return_value=2)  # type: ignore[method-assign]

        ok = await ingestor.process_file_async(
            file_path,
            embedding_gen=None,
            storage=SimpleNamespace(store_batch_async=AsyncMock()),
            skip_existing=False,
        )
        assert ok is True
        ingestor._stream_process_chunks_async.assert_awaited_once()

        tree = structure_store.load_tree(str(file_path))
        assert tree is not None
        assert [n.node_id for n in tree.nodes] == ["ch01"]
        assert tree.sources["heading_hierarchy"] is True

    async def test_treeless_document_saves_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
        structure_store: StructureStore,
    ) -> None:
        file_path = tmp_path / "flat.epub"
        self._fake_extract(
            ingestor, monkeypatch, [{"text": "body text", "page": 1}], None
        )
        self._patch_store(ingestor, monkeypatch, structure_store)
        self._pin_streaming(monkeypatch, True)
        ingestor._stream_process_chunks_async = AsyncMock(return_value=1)  # type: ignore[method-assign]

        ok = await ingestor.process_file_async(
            file_path, embedding_gen=None, storage=None, skip_existing=False
        )
        assert ok is True
        assert structure_store.has_tree(str(file_path)) is False

    async def test_all_skipped_still_persists_tree(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
        structure_store: StructureStore,
    ) -> None:
        file_path = tmp_path / "book.epub"
        part = chapter_tree(str(file_path))
        self._fake_extract(
            ingestor, monkeypatch, [{"text": "body text", "page": 1}], part
        )
        self._patch_store(ingestor, monkeypatch, structure_store)
        monkeypatch.setattr(
            "secondbrain.document.ingestor._async._query_existing_hashes",
            lambda storage, hashes: set(hashes),
        )
        skipped_files: set[str] = set()

        ok = await ingestor.process_file_async(
            file_path,
            embedding_gen=None,
            storage=None,
            skip_existing=True,
            skipped_files=skipped_files,
        )
        # Capture + persist happen BEFORE the skip branch: already-stored
        # documents still gain their tree.
        assert ok is True
        assert str(file_path) in skipped_files
        assert structure_store.has_tree(str(file_path))

    async def test_broken_store_never_fails_ingest(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.epub"
        part = chapter_tree(str(file_path))
        self._fake_extract(
            ingestor, monkeypatch, [{"text": "body text", "page": 1}], part
        )
        self._patch_store(ingestor, monkeypatch, None)
        self._pin_streaming(monkeypatch, True)
        ingestor._stream_process_chunks_async = AsyncMock(return_value=1)  # type: ignore[method-assign]

        ok = await ingestor.process_file_async(
            file_path, embedding_gen=None, storage=None, skip_existing=False
        )
        assert ok is True

    async def test_non_streaming_path_persists_and_stores(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
        structure_store: StructureStore,
    ) -> None:
        from secondbrain.config import config

        cfg = config()
        monkeypatch.setattr(cfg, "streaming_enabled", False)
        file_path = tmp_path / "book.epub"
        part = chapter_tree(str(file_path))
        self._fake_extract(
            ingestor, monkeypatch, [{"text": "body text", "page": 1}], part
        )
        self._patch_store(ingestor, monkeypatch, structure_store)

        embedding_gen = SimpleNamespace(
            generate_batch_async=AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        )
        storage = SimpleNamespace(store_batch_async=AsyncMock(return_value=None))
        ok = await ingestor.process_file_async(
            file_path,
            embedding_gen=embedding_gen,
            storage=storage,
            skip_existing=False,
        )
        assert ok is True
        storage.store_batch_async.assert_awaited_once()
        assert structure_store.has_tree(str(file_path))


# ---------------------------------------------------------------------------
# Audio capture wiring (design §5, task 10): worker + extract sink + async
# ---------------------------------------------------------------------------


class TestWorkerAudioStructureCapture:
    """Audio files capture their ASR tree in the worker (design §5).

    The ASR result document is released (unload + del) inside the conversion
    step, so the timestamp-bearing texts must be extracted into the
    lightweight shape ``capture_audio_structure`` reads BEFORE the release;
    the capture point reads the shape, never the (dead) document.
    """

    def test_timestamped_asr_document_yields_segment_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        result = run_worker(
            file_path,
            asr_document(
                asr_item("today we discuss rockets", 30.0, 60.0),
                asr_item("welcome everyone to the show", 0.0, 30.0),
            ),
            monkeypatch,
        )

        assert result["success"] is True
        structure = result["structure"]
        assert structure is not None
        assert structure.source_file == str(file_path)
        assert structure.sources == {"audio": True}
        # One segment node per timestamped ASR segment, in time order.
        assert [n.node_id for n in structure.nodes] == ["seg01", "seg02"]
        first, second = structure.nodes
        assert first.kind == "segment"
        assert (first.t_start, first.t_end) == (0.0, 30.0)
        assert (second.t_start, second.t_end) == (30.0, 60.0)
        assert first.title == "welcome everyone to the show"
        assert result["documents"], "documents must still be produced"
        assert len(result["documents"]) == 1
        assert (
            result["documents"][0]["t_start"],
            result["documents"][0]["t_end"],
        ) == (0.0, 60.0)
        assert result["documents"][0]["node_id"] == "seg01"

    def test_capture_extracts_before_document_release(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        document = asr_document(
            asr_item("welcome everyone to the show", 0.0, 30.0),
            asr_item("today we discuss rockets", 30.0, 60.0),
        )
        converter = UnloadingConverter(document)
        result = run_worker(file_path, document, monkeypatch, converter=converter)

        # The document was released exactly once (worker convention), yet the
        # tree was still captured: had the shape been extracted after the
        # release, the poisoned (texts=None) document would degrade to None.
        assert converter.unload_calls == 1
        structure = result["structure"]
        assert structure is not None
        assert [n.node_id for n in structure.nodes] == ["seg01", "seg02"]
        assert (structure.nodes[0].t_start, structure.nodes[0].t_end) == (0.0, 30.0)

    def test_no_timestamps_degrades_to_whole_document_segment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        result = run_worker(
            file_path,
            asr_document(
                asr_item("first words without any timestamps"),
                asr_item("more words"),
            ),
            monkeypatch,
        )

        assert result["success"] is True
        structure = result["structure"]
        assert structure is not None
        assert [n.node_id for n in structure.nodes] == ["seg01"]
        only = structure.nodes[0]
        assert (only.t_start, only.t_end) == (0.0, None)
        assert only.title == "first words without any timestamps"

    def test_empty_transcript_yields_no_tree_and_fails_loudly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        result = run_worker(file_path, asr_document(), monkeypatch)

        # An empty ASR transcript raises the audio-specific extraction error
        # (existing behavior) and the document has no tree.
        assert result["success"] is False
        assert result["structure"] is None


class TestAudioTopicReingest:
    @staticmethod
    def _tree(source_file: str) -> DocumentStructure:
        from secondbrain.document.structure_capture import capture_audio_structure

        tree = capture_audio_structure(
            asr_document(asr_item("full extracted transcript", 0.0, 30.0)),
            Path(source_file),
        )
        assert tree is not None
        return tree

    @pytest.mark.parametrize("provider_fails", [False, True])
    def test_preserves_compatible_topics_when_segmentation_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        provider_fails: bool,
    ) -> None:
        from secondbrain.rag.providers.factory import LLMProviderFactory

        store = StructureStore(db_path=str(tmp_path / "topics.db"))
        source = str(tmp_path / "talk.m4a")
        previous = self._tree(source)
        previous.audio_segments = [
            AudioSegment(seg_id=1, t_start=0.0, t_end=30.0, title="Existing topic")
        ]
        store.save_structure(previous)
        ingestor = DocumentIngestor()
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        monkeypatch.setattr(
            config(), "audio_topic_segmentation_enabled", provider_fails
        )

        def unavailable(cfg: Any) -> Any:
            raise RuntimeError("offline")

        monkeypatch.setattr(LLMProviderFactory, "create_from_config", unavailable)
        result = {
            "structure": self._tree(source),
            "documents": [],
            "audio_transcript": ["full extracted transcript"],
        }
        ingestor._persist_worker_structure(result)
        ingestor._segment_audio_topics(result)

        loaded = store.load_tree(source)
        assert loaded is not None
        assert loaded.audio_segments == previous.audio_segments

    def test_does_not_preserve_topics_for_changed_capture(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "topics.db"))
        source = str(tmp_path / "talk.m4a")
        previous = self._tree(source)
        previous.audio_segments = [
            AudioSegment(seg_id=1, t_start=0.0, t_end=30.0, title="Old topic")
        ]
        store.save_structure(previous)
        fresh = self._tree(source)
        fresh.nodes[0].t_end = 60.0
        ingestor = DocumentIngestor()
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)

        ingestor._persist_worker_structure({"structure": fresh})

        loaded = store.load_tree(source)
        assert loaded is not None
        assert loaded.audio_segments == []

    @pytest.mark.parametrize("documents", [[], [{"chunk_text": "remaining only"}]])
    def test_segmentation_uses_full_transcript(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        documents: list[dict[str, str]],
    ) -> None:
        from secondbrain.rag.providers.factory import LLMProviderFactory

        store = StructureStore(db_path=str(tmp_path / "topics.db"))
        source = str(tmp_path / "talk.m4a")
        ingestor = DocumentIngestor()
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        monkeypatch.setattr(config(), "audio_topic_segmentation_enabled", True)
        monkeypatch.setattr(
            LLMProviderFactory, "create_from_config", lambda cfg: object()
        )
        seen: list[list[str]] = []

        def segment(tree: Any, texts: list[str], **kwargs: Any) -> list[AudioSegment]:
            seen.append(texts)
            return [AudioSegment(seg_id=1, t_start=0.0, t_end=30.0, title="Full topic")]

        monkeypatch.setattr(
            "secondbrain.document.structure_capture.audio_topic_segments", segment
        )
        result = {
            "structure": self._tree(source),
            "documents": documents,
            "audio_transcript": ["already stored words", "remaining only"],
        }
        ingestor._persist_worker_structure(result)
        ingestor._segment_audio_topics(result)

        assert seen == [["already stored words", "remaining only"]]
        loaded = store.load_tree(source)
        assert loaded is not None
        assert loaded.audio_segments[0].title == "Full topic"

    @pytest.mark.asyncio
    async def test_async_capture_preserves_compatible_topics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = tmp_path / "talk.m4a"
        store = StructureStore(db_path=str(tmp_path / "topics.db"))
        previous = self._tree(str(source))
        previous.audio_segments = [
            AudioSegment(seg_id=1, t_start=0.0, t_end=30.0, title="Existing topic")
        ]
        store.save_structure(previous)
        ingestor = AsyncDocumentIngestor()
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)

        captured = await ingestor._capture_and_persist_structure_async(
            source, [asr_document(asr_item("full extracted transcript", 0.0, 30.0))]
        )

        assert captured is not None
        assert captured.audio_segments == previous.audio_segments
        loaded = store.load_tree(str(source))
        assert loaded is not None
        assert loaded.audio_segments == previous.audio_segments

    @pytest.mark.parametrize("streaming", [False, True])
    def test_sync_builders_preserve_time_bounds(
        self, tmp_path: Path, streaming: bool
    ) -> None:
        source = tmp_path / "talk.m4a"
        segments = [
            {
                "text": "full extracted transcript",
                "page": 1,
                "t_start": 10.0,
                "t_end": 30.0,
            }
        ]
        ingestor = DocumentIngestor()
        documents: list[dict[str, Any]] = []

        def store_batch(batch: list[dict[str, Any]]) -> int:
            documents.extend(batch)
            return len(batch)

        if streaming:
            assert (
                ingestor._stream_process_chunks(
                    source,
                    segments,
                    FakeEmbeddingModel(),
                    SimpleNamespace(store_batch=store_batch),
                )
                == 1
            )
        else:
            documents = ingestor._build_documents_with_embeddings(
                source, segments, FakeEmbeddingModel()
            )
        assert len(documents) == 1
        assert (documents[0]["t_start"], documents[0]["t_end"]) == (10.0, 30.0)

    def test_failed_topic_window_retains_previous_title(self) -> None:
        tree = self._tree("/recordings/talk.m4a")
        tree.audio_segments = [
            AudioSegment(seg_id=1, t_start=0.0, t_end=30.0, title="Existing topic")
        ]

        DocumentIngestor._replace_audio_topics(
            tree, [AudioSegment(seg_id=1, t_start=0.0, t_end=30.0)]
        )

        assert tree.audio_segments[0].title == "Existing topic"

    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.asyncio
    async def test_async_ingestion_stores_time_bounds_and_structural_ids(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        streaming: bool,
    ) -> None:
        from qdrant_client import QdrantClient

        from secondbrain.storage.qdrant import QdrantVectorStorage

        source = tmp_path / "talk.m4a"
        source.write_bytes(b"audio-bytes")
        document = asr_document(asr_item("full extracted transcript", 10.0, 30.0))
        TestExtractTextAudioSink._wire_docling(document, monkeypatch)
        store = StructureStore(db_path=str(tmp_path / "topics.db"))
        ingestor = AsyncDocumentIngestor()
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: store)
        monkeypatch.setattr(config(), "streaming_enabled", streaming)
        monkeypatch.setattr(config(), "audio_topic_segmentation_enabled", False)
        storage = QdrantVectorStorage(collection_name="audio")
        storage._client = QdrantClient(":memory:")
        storage._dimensions = 3
        embeddings = SimpleNamespace(
            generate_batch_async=AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        )
        try:
            assert await ingestor.process_file_async(
                source, embeddings, storage, skip_existing=False
            )
            chunks = storage.get_source_chunks(str(source))
            assert len(chunks) == 1
            assert chunks[0]["node_id"] == "seg01"
            assert chunks[0]["chapter_id"] == "seg01"
            assert (chunks[0]["t_start"], chunks[0]["t_end"]) == (10.0, 30.0)
        finally:
            storage.close()


class TestExtractTextAudioSink:
    """_extract_text collects the ASR capture shape for audio files.

    The structure_sink is the single capture-input channel: heading parts
    for parseable documents, the extracted ASR shape for audio (design §5).
    """

    @pytest.fixture
    def ingestor(self) -> DocumentIngestor:
        return DocumentIngestor()

    @staticmethod
    def _wire_docling(document: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "secondbrain.document.fast_text.try_fast_pdf_extraction",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "secondbrain.document.docling_factory.get_converter_for_path",
            lambda path: FakeConverter(document),
        )

    def test_audio_file_fills_sink_with_asr_shape(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        document = asr_document(asr_item("hello world", 0.0, 3.5))
        self._wire_docling(document, monkeypatch)
        sink: list[Any] = []

        segments = ingestor._extract_text(file_path, sink)

        assert [s["text"] for s in segments] == ["hello world"]
        assert segments[0]["t_start"] == 0.0
        assert segments[0]["t_end"] == 3.5
        # ASR documents carry no headings; the extracted shape is collected
        # instead — not the live document itself.
        assert len(sink) == 1
        shape = sink[0]
        assert shape is not document
        [item] = shape.texts
        assert item.text == "hello world"
        assert [(s.start_time, s.end_time) for s in item.source] == [(0.0, 3.5)]

    def test_shape_survives_document_release(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        from secondbrain.document.structure_capture import capture_structure

        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        document = asr_document(asr_item("hello world", 0.0, 3.5))
        self._wire_docling(document, monkeypatch)
        sink: list[Any] = []
        ingestor._extract_text(file_path, sink)

        # The real path releases the document when extraction returns; the
        # extracted shape alone must still capture the tree (dispatcher).
        document.texts = None
        tree = capture_structure(file_path, sink[0], file_type="audio")
        assert tree is not None
        assert [n.node_id for n in tree.nodes] == ["seg01"]
        assert (tree.nodes[0].t_start, tree.nodes[0].t_end) == (0.0, 3.5)

    def test_non_audio_files_still_collect_heading_parts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: DocumentIngestor,
    ) -> None:
        file_path = tmp_path / "book.epub"
        file_path.write_bytes(b"epub-bytes")
        self._wire_docling(heading_document(), monkeypatch)
        sink: list[Any] = []

        segments = ingestor._extract_text(file_path, sink)

        assert segments
        # Regression guard: the heading lane is untouched by the audio sink.
        assert len(sink) == 1
        assert [n.node_id for n in sink[0].nodes] == ["ch01", "sec01.02"]


class TestAsyncAudioCaptureAndPersist:
    """process_file_async captures + persists the audio tree end to end.

    Unlike the faked-sink tests above, these run the real ``_extract_text``
    so the ASR shape actually flows through the sink into the dispatcher.
    """

    @pytest.fixture
    def ingestor(self) -> AsyncDocumentIngestor:
        return AsyncDocumentIngestor()

    @pytest.fixture
    def structure_store(self, tmp_path: Path) -> StructureStore:
        return StructureStore(db_path=str(tmp_path / "structures.db"))

    def _wire_audio(
        self,
        ingestor: AsyncDocumentIngestor,
        document: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "secondbrain.document.fast_text.try_fast_pdf_extraction",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "secondbrain.document.docling_factory.get_converter_for_path",
            lambda path: FakeConverter(document),
        )
        # Topic segmentation (segment titles) is a separate lane; keep the
        # LLM provider factory out of these capture tests.
        monkeypatch.setattr(config(), "audio_topic_segmentation_enabled", False)

    async def test_audio_tree_persisted_through_real_extract(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
        structure_store: StructureStore,
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        self._wire_audio(
            ingestor,
            asr_document(
                asr_item("today we discuss rockets", 30.0, 60.0),
                asr_item("welcome everyone to the show", 0.0, 30.0),
            ),
            monkeypatch,
        )
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: structure_store)
        monkeypatch.setattr(config(), "streaming_enabled", True)
        ingestor._stream_process_chunks_async = AsyncMock(return_value=2)  # type: ignore[method-assign]

        ok = await ingestor.process_file_async(
            file_path,
            embedding_gen=None,
            storage=SimpleNamespace(store_batch_async=AsyncMock()),
            skip_existing=False,
        )

        assert ok is True
        tree = structure_store.load_tree(str(file_path))
        assert tree is not None
        assert tree.source_file == str(file_path)
        assert tree.sources == {"audio": True}
        assert [n.node_id for n in tree.nodes] == ["seg01", "seg02"]
        assert (tree.nodes[0].t_start, tree.nodes[0].t_end) == (0.0, 30.0)

    async def test_no_timestamps_persists_degraded_tree(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        ingestor: AsyncDocumentIngestor,
        structure_store: StructureStore,
    ) -> None:
        file_path = tmp_path / "talk.m4a"
        file_path.write_bytes(b"audio-bytes")
        self._wire_audio(
            ingestor,
            asr_document(
                asr_item("first words without any timestamps"),
                asr_item("more words"),
            ),
            monkeypatch,
        )
        monkeypatch.setattr(ingestor, "_get_structure_store", lambda: structure_store)
        monkeypatch.setattr(config(), "streaming_enabled", True)
        ingestor._stream_process_chunks_async = AsyncMock(return_value=1)  # type: ignore[method-assign]

        ok = await ingestor.process_file_async(
            file_path,
            embedding_gen=None,
            storage=SimpleNamespace(store_batch_async=AsyncMock()),
            skip_existing=False,
        )

        assert ok is True
        tree = structure_store.load_tree(str(file_path))
        assert tree is not None
        # Graceful degrade: one whole-document segment, open end.
        assert [n.node_id for n in tree.nodes] == ["seg01"]
        only = tree.nodes[0]
        assert (only.t_start, only.t_end) == (0.0, None)
