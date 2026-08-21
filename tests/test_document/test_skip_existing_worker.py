"""Tests for the persistent re-ingest skip logic in the sync worker.

Covers the pure ``_filter_existing_chunks`` filter and the worker behaviour when
``skip_existing`` is enabled: full-file skip, partial skip, graceful degradation
when the storage lookup fails, and that the embedder is not invoked for chunks
whose text_hash already exists.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import secondbrain.document.processor as processor
import secondbrain.embedding as embedding_module

_SAMPLE_TEXT = (
    "SecondBrain is a local document intelligence CLI for semantic search. "
    "It uses MongoDB vector search and OpenAI-compatible embedding APIs to "
    "ingest, chunk, embed, and retrieve documents from a personal knowledge "
    "base. This sentence supplies enough characters to exercise the chunker "
    "and produce at least one deterministic chunk for the worker pipeline."
) * 4


class _TextItem:
    def __init__(self, text: str, page_no: int = 1) -> None:
        self.text = text
        self.prov = [type("_Prov", (), {"page_no": page_no})()]


class _Content:
    def __init__(self, texts: list[_TextItem]) -> None:
        self.texts = texts


class _Result:
    def __init__(self, document: _Content) -> None:
        self.document = document


class _FakeConverter:
    def __init__(self, texts: list[_TextItem]) -> None:
        self._texts = texts

    def convert(self, file_path):
        return _Result(_Content(self._texts))


class _CountingEmbeddingModel:
    def __init__(self) -> None:
        self.calls = 0
        self.embed_texts: list[str] = []

    def generate_batch(self, texts):
        self.calls += 1
        self.embed_texts.extend(texts)
        return [[0.1] * 4 for _ in texts]


def _setup(monkeypatch, tmp_path: Path) -> tuple[_CountingEmbeddingModel, Path]:
    converter = _FakeConverter(
        [_TextItem(_SAMPLE_TEXT, page_no=1), _TextItem("Introduction.", page_no=2)]
    )
    import secondbrain.document.docling_factory as docling_factory

    monkeypatch.setattr(docling_factory, "get_converter_for_path", lambda _p: converter)
    model = _CountingEmbeddingModel()
    monkeypatch.setattr(
        embedding_module.EmbeddingProviderFactory,
        "create_from_config",
        lambda _cfg: model,
    )

    mock_cfg = MagicMock()
    mock_cfg.embedding_model = "test-model"
    mock_cfg.embedding_batch_size = 100
    mock_cfg.skip_existing_on_reingest = True
    monkeypatch.setattr("secondbrain.config.config", lambda: mock_cfg)

    file_path = tmp_path / "sample.txt"
    file_path.write_text(_SAMPLE_TEXT, encoding="utf-8")
    return model, file_path


def _run(
    monkeypatch, tmp_path: Path, existing_fn
) -> tuple[dict, _CountingEmbeddingModel]:
    model, file_path = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(processor, "_existing_text_hashes", existing_fn)
    result = processor._extract_chunk_and_embed_file(
        str(file_path),
        chunk_size=512,
        chunk_overlap=50,
        progress_queue=None,
        embedding_model_name="test-model",
        skip_existing=True,
    )
    return result, model


class TestFilterExistingChunks:
    def test_returns_only_non_existing_preserving_order(self) -> None:
        chunks = [
            {"text": "a", "text_hash": "h1"},
            {"text": "b", "text_hash": "h2"},
            {"text": "c", "text_hash": "h3"},
        ]
        result = processor._filter_existing_chunks(chunks, {"h2"})
        assert [c["text_hash"] for c in result] == ["h1", "h3"]
        assert result[0] is chunks[0]
        assert result[1] is chunks[2]

    def test_empty_when_all_existing(self) -> None:
        chunks = [{"text": "a", "text_hash": "h1"}, {"text": "b", "text_hash": "h2"}]
        assert processor._filter_existing_chunks(chunks, {"h1", "h2"}) == []

    def test_returns_same_when_none_existing(self) -> None:
        chunks = [{"text": "a", "text_hash": "h1"}]
        assert processor._filter_existing_chunks(chunks, set()) is chunks


class TestWorkerFullSkip:
    def test_fully_existing_file_is_skipped_without_embedding(
        self, monkeypatch, tmp_path
    ) -> None:
        result, model = _run(monkeypatch, tmp_path, lambda hashes: set(hashes))

        assert result["success"] is True
        assert result["documents"] == []
        assert result["skipped"] is True
        assert model.calls == 0
        assert model.embed_texts == []


class TestWorkerPartialSkip:
    def test_only_new_chunks_embedded(self, monkeypatch, tmp_path) -> None:
        captured: dict[str, object] = {}

        def _existing(hashes):
            first = hashes[0]
            captured["existing"] = first
            return {first}

        result, model = _run(monkeypatch, tmp_path, _existing)

        assert result["success"] is True
        assert result["skipped"] is False
        assert result["documents"]
        assert captured["existing"] is not None
        existing = {captured["existing"]}
        for doc in result["documents"]:
            assert doc["text_hash"] not in existing
        assert model.calls == 1
        assert len(result["documents"]) == len(model.embed_texts)


class TestWorkerDegradation:
    def test_storage_lookup_failure_embeds_everything(
        self, monkeypatch, tmp_path
    ) -> None:
        def _boom(hashes):
            raise RuntimeError("db down")

        result, model = _run(monkeypatch, tmp_path, _boom)

        assert result["success"] is True
        assert result["skipped"] is False
        assert result["documents"]
        assert model.calls == 1


class TestWorkerSkipDisabled:
    def test_skip_existing_false_never_queries_storage(
        self, monkeypatch, tmp_path
    ) -> None:
        model, file_path = _setup(monkeypatch, tmp_path)
        calls = {"n": 0}

        def _tracking(hashes):
            calls["n"] += 1
            return set(hashes)

        monkeypatch.setattr(processor, "_existing_text_hashes", _tracking)
        result = processor._extract_chunk_and_embed_file(
            str(file_path),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=False,
        )

        assert result["success"] is True
        assert result["skipped"] is False
        assert result["documents"]
        assert calls["n"] == 0
        assert model.calls == 1
