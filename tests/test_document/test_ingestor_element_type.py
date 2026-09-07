"""Element-type label propagation through DocumentIngestor chunking paths."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.document.ingestor import AsyncDocumentIngestor, DocumentIngestor

HEADING_TEXT = "1 Principles of IoT and AI"
BODY_TEXT = (
    "The Internet of Things connects physical devices to cloud platforms, "
    "enabling telemetry collection at scale across fleets of heterogeneous "
    "sensors and gateways that report telemetry continuously."
)
FOOTER_TEXT = "12"


def _labeled_segments() -> list[dict[str, Any]]:
    return [
        {"text": HEADING_TEXT, "page": 1, "label": "section_header"},
        {"text": BODY_TEXT, "page": 1, "label": "text"},
        {"text": FOOTER_TEXT, "page": 1, "label": "page_footer"},
    ]


def _unlabeled_segments() -> list[dict[str, Any]]:
    return [
        {"text": HEADING_TEXT, "page": 1},
        {"text": BODY_TEXT, "page": 1},
        {"text": FOOTER_TEXT, "page": 1},
    ]


class TestSyncStreamingElementTypes:
    def test_labels_drive_roles(self) -> None:
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)
        embedding_gen = MagicMock()
        embedding_gen.generate_batch.return_value = [[0.1] * 4 for _ in range(3)]
        storage = MagicMock()

        docs_stored = ingestor._stream_process_chunks(
            Path("book.pdf"), _labeled_segments(), embedding_gen, storage
        )

        assert docs_stored == 3
        stored = storage.store_batch.call_args[0][0]
        roles = {(d["chunk_role"], d["element_type"]) for d in stored}
        assert ("heading", "heading") in roles
        assert ("navigation", "navigation") in roles
        assert ("body", "body") in roles

    def test_unlabeled_keeps_dual_keys_consistent(self) -> None:
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)
        embedding_gen = MagicMock()
        embedding_gen.generate_batch.return_value = [[0.1] * 4 for _ in range(3)]
        storage = MagicMock()

        docs_stored = ingestor._stream_process_chunks(
            Path("book.pdf"), _unlabeled_segments(), embedding_gen, storage
        )

        assert docs_stored == 3
        stored = storage.store_batch.call_args[0][0]
        assert all(d["element_type"] == d["chunk_role"] for d in stored)


class TestBatchElementTypes:
    def test_deduplicate_carries_label_roles(self) -> None:
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        chunks = ingestor._deduplicate_and_chunk_segments(
            Path("book.pdf"), _labeled_segments()
        )

        assert [c["chunk_role"] for c in chunks] == ["heading", "body", "navigation"]
        assert [c["element_type"] for c in chunks] == [
            "heading",
            "body",
            "navigation",
        ]

    def test_deduplicate_unlabeled_defaults_to_body(self) -> None:
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)

        chunks = ingestor._deduplicate_and_chunk_segments(
            Path("book.pdf"), _unlabeled_segments()
        )

        assert all(c["chunk_role"] == "body" for c in chunks)
        assert all(c["element_type"] == "body" for c in chunks)

    def test_build_documents_with_embeddings_writes_element_type(self) -> None:
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)
        embedding_gen = MagicMock()
        embedding_gen.generate_batch.return_value = [[0.1] * 4 for _ in range(3)]

        docs = ingestor._build_documents_with_embeddings(
            Path("book.pdf"), _labeled_segments(), embedding_gen
        )

        roles = {(d["chunk_role"], d["element_type"]) for d in docs}
        assert ("heading", "heading") in roles
        assert ("navigation", "navigation") in roles


class TestExtractTextLabels:
    def test_docling_fallback_emits_labels(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        items = [
            SimpleNamespace(
                text=HEADING_TEXT,
                prov=[SimpleNamespace(page_no=1)],
                label=SimpleNamespace(value="section_header"),
            ),
            SimpleNamespace(text=BODY_TEXT, prov=[SimpleNamespace(page_no=1)]),
        ]
        converter = SimpleNamespace(
            convert=lambda p: SimpleNamespace(document=SimpleNamespace(texts=items))
        )
        monkeypatch.setattr(
            "secondbrain.document.fast_text.try_fast_pdf_extraction",
            lambda p: None,
        )
        monkeypatch.setattr(
            "secondbrain.document.docling_factory.get_converter_for_path",
            lambda p: converter,
        )
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        ingestor = DocumentIngestor()
        segments = ingestor._extract_text(pdf)

        assert segments[0] == {
            "text": HEADING_TEXT,
            "page": 1,
            "label": "section_header",
        }
        assert segments[1] == {"text": BODY_TEXT, "page": 1}


class TestAsyncStreamingElementTypes:
    @pytest.mark.asyncio
    async def test_labels_drive_roles(self) -> None:
        ingestor = AsyncDocumentIngestor()
        embedding_gen = MagicMock()
        embedding_gen.generate_batch_async = AsyncMock(
            return_value=[[0.1] * 4 for _ in range(3)]
        )
        storage = MagicMock()
        storage.store_batch_async = AsyncMock()

        docs_stored = await ingestor._stream_process_chunks_async(
            Path("book.pdf"), _labeled_segments(), embedding_gen, storage
        )

        assert docs_stored == 3
        stored = storage.store_batch_async.call_args[0][0]
        roles = {(d["chunk_role"], d["element_type"]) for d in stored}
        assert ("heading", "heading") in roles
        assert ("navigation", "navigation") in roles
        assert ("body", "body") in roles
