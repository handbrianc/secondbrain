"""Windowed PDF conversion in ``_extract_chunk_and_embed_file``.

Unit tests for the page-window loop introduced by
``add-pdf-ingest-memory-bounds``: a PDF larger than
``pdf_max_pages_per_convert`` converts as sequential 1-based page ranges
(``converter.convert(file_path, page_range=(start, end))``), each window's
segments extend in document order with absolute page numbers, and the
conversion artifacts (backend page state) release once per window.

The converter is faked at the exact shape the real code relies on
(``result.document.texts`` items with ``.text``/``.prov[0].page_no`` and
``result.input._backend.unload()``); ``pdf_page_count``, config, the
converter resolver, and the embedding factory are stubbed the same way as
``tests/test_document/test_processor_gaps.py``. Chunking is replaced with a
capturing passthrough so the merged segment stream — the actual contract of
windowing ("segments merge across windows, chunking unchanged") — is asserted
directly.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import secondbrain.document.docling_factory as docling_factory
import secondbrain.document.fast_text as fast_text
import secondbrain.embedding as embedding_module
from secondbrain.document import processor

# Sentinel recorded when the worker calls convert() WITHOUT a page_range
# kwarg (whole-document conversion) — distinguishes "no kwarg" from None.
_NO_PAGE_RANGE = object()


class _FakeTextItem:
    """Docling text item stand-in: .text, .prov[0].page_no, optional .label."""

    def __init__(self, text: str, page_no: int, label: str | None = None) -> None:
        self.text = text
        self.prov = [SimpleNamespace(page_no=page_no)]
        if label is not None:
            self.label = label


class _ScrapeRecorder:
    """Captures the on_page_batch callback the worker hands to the scraper."""

    def __init__(self) -> None:
        self.on_tick: Callable[[int, int], None] | None = None


class _FakeWindowConverter:
    """Fake docling converter producing per-window documents.

    Records ``(file_path, page_range)`` for every ``convert()`` call — the
    sentinel distinguishes a whole-document call (no ``page_range`` kwarg)
    from a windowed one. Text items are served for exactly the requested
    pages, reporting ABSOLUTE 1-based page numbers as real docling does under
    ``page_range`` windowing. ``result.input._backend`` is the converter
    itself, whose ``unload()`` counts calls.
    """

    def __init__(
        self,
        pages: dict[int, list[_FakeTextItem]],
        scrape_recorder: _ScrapeRecorder | None = None,
    ) -> None:
        self._pages = pages
        self._scrape_recorder = scrape_recorder
        self.calls: list[tuple[Path, Any]] = []
        self.unload_calls = 0

    def convert(self, file_path: Path, page_range: Any = _NO_PAGE_RANGE) -> Any:
        self.calls.append((file_path, page_range))
        window = None if page_range is _NO_PAGE_RANGE else page_range
        if window is not None:
            start, end = window
            wanted = list(range(start, end + 1))
        else:
            wanted = sorted(self._pages)
        self._fire_scrape_ticks(window)
        texts = [item for page in wanted for item in self._pages.get(page, [])]
        return SimpleNamespace(
            document=SimpleNamespace(texts=texts),
            input=SimpleNamespace(_backend=self),
        )

    def _fire_scrape_ticks(self, window: tuple[int, int] | None) -> None:
        """Emulate docling's per-conversion page-batch DEBUG scraper.

        Docling reports (done, total) with counters scoped to ONE convert()
        call: done restarts per window and total is that conversion's page
        count. Ticks fire mid-conversion, while the worker's rebasing
        callback is live.
        """
        if self._scrape_recorder is None or self._scrape_recorder.on_tick is None:
            return
        if window is not None:
            start, end = window
        else:
            start, end = 1, max(sorted(self._pages), default=0)
        for done in range(1, end - start + 2):
            self._scrape_recorder.on_tick(done, end - start + 1)

    def unload(self) -> None:
        self.unload_calls += 1


class _FakeEmbedder:
    """Embedder stand-in recording batch texts; returns stable 4-float rows."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class _CaptureQueue:
    """Stand-in for queue.Queue capturing put_nowait messages."""

    def __init__(self) -> None:
        self.items: list[Any] = []

    def put_nowait(self, item: Any) -> None:
        self.items.append(item)


def _window_cfg(max_pages: int) -> Any:
    """Config stand-in carrying the windowing setting the worker reads."""

    class _FakeCfg:
        pdf_max_pages_per_convert = max_pages
        embedding_batch_size = 8
        embedding_dtype = "float32"
        skip_existing_on_reingest = False

    return _FakeCfg()


def _page_text(page: int) -> str:
    """Unique non-empty text for one absolute page (no page-stamp markers)."""
    return f"Page {page} unique body text about machine learning topic {page}."


def _pages(n: int) -> dict[int, list[_FakeTextItem]]:
    """One text item per absolute page 1..n."""
    return {page: [_FakeTextItem(_page_text(page), page)] for page in range(1, n + 1)}


def _install_worker_stubs(
    monkeypatch: pytest.MonkeyPatch,
    converter: _FakeWindowConverter,
    cfg: Any,
    embedder: _FakeEmbedder,
    *,
    page_count: int | None = None,
) -> None:
    """Stub the seams the worker reaches: fast path, converter, config, embedder."""
    if page_count is None:
        page_count = len(converter._pages)
    monkeypatch.setattr(
        fast_text,
        "try_fast_pdf_extraction",
        lambda _path, page_progress=None: None,
    )
    monkeypatch.setattr(
        docling_factory, "get_converter_for_path", lambda _path: converter
    )
    monkeypatch.setattr(processor, "pdf_page_count", lambda _path: page_count)
    monkeypatch.setattr("secondbrain.config.config", lambda: cfg)
    monkeypatch.setattr(
        embedding_module.EmbeddingProviderFactory,
        "create_from_config",
        staticmethod(lambda _cfg: embedder),
    )


def _capture_segments_via_chunking(
    monkeypatch: pytest.MonkeyPatch,
) -> list[list[dict[str, Any]]]:
    """Replace chunking with a passthrough that records the merged segments.

    One chunk per segment keeps pages 1:1 so documents mirror the segment
    stream exactly — the observable contract of window merging.
    """
    captured: list[list[dict[str, Any]]] = []

    def fake_chunk_segments(
        segments: list[dict[str, Any]], _chunk_size: int, _chunk_overlap: int
    ) -> list[dict[str, Any]]:
        captured.append([dict(s) for s in segments])
        return [
            {
                "text": s["text"],
                "page": s["page"],
                "chunk_role": "body",
                "element_type": "body",
            }
            for s in segments
        ]

    monkeypatch.setattr(processor, "chunk_segments", fake_chunk_segments)
    return captured


def _write_fake_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "manual.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    return pdf


def _run_worker(pdf: Path, **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "chunk_size": 512,
        "chunk_overlap": 50,
        "progress_queue": None,
        "embedding_model_name": "test-model",
        "skip_existing": False,
    }
    kwargs.update(overrides)
    return processor._extract_chunk_and_embed_file(str(pdf), **kwargs)


class TestWindowedConversion:
    """Sequential page-range windows with artifact release per window."""

    def test_multipage_pdf_converts_in_sequential_windows(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """7 pages / window 3 -> ranges (1,3),(4,6),(7,7); absolute pages; 3 unloads."""
        pdf = _write_fake_pdf(tmp_path)
        converter = _FakeWindowConverter(_pages(7))
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(3), embedder)
        captured = _capture_segments_via_chunking(monkeypatch)

        result = _run_worker(pdf)

        assert result["success"] is True
        assert converter.calls == [
            (pdf, (1, 3)),
            (pdf, (4, 6)),
            (pdf, (7, 7)),
        ]
        # All three calls carried an explicit page_range kwarg (never the
        # whole-document sentinel).
        assert all(
            page_range is not _NO_PAGE_RANGE for _, page_range in converter.calls
        )
        # Artifact release: the backend unloaded once per window.
        assert converter.unload_calls == 3
        # Segments merged across windows in document order with the ABSOLUTE
        # 1..7 page numbers the fake converter reports.
        segments = captured[0]
        assert [s["page"] for s in segments] == list(range(1, 8))
        assert [s["text"] for s in segments] == [_page_text(n) for n in range(1, 8)]
        # One unique chunk per segment: page numbers flow through storage.
        documents = result["documents"]
        assert [d["page_number"] for d in documents] == list(range(1, 8))

    def test_window_zero_converts_whole_document_without_page_range(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """pdf_max_pages_per_convert=0 disables windowing: one convert, no kwarg."""
        pdf = _write_fake_pdf(tmp_path)
        converter = _FakeWindowConverter(_pages(7))
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(0), embedder)
        captured = _capture_segments_via_chunking(monkeypatch)

        result = _run_worker(pdf)

        assert result["success"] is True
        assert converter.calls == [(pdf, _NO_PAGE_RANGE)]
        assert converter.unload_calls == 1
        assert [s["page"] for s in captured[0]] == list(range(1, 8))

    @pytest.mark.parametrize(
        ("pages", "window"),
        [(5, 200), (5, 5), (4, 4)],
        ids=["below-window", "pages-eq-window", "window-eq-pages"],
    )
    def test_pages_at_or_below_window_convert_whole_document(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pages: int, window: int
    ) -> None:
        """Page count at/below the window converts whole: exactly today's path."""
        pdf = _write_fake_pdf(tmp_path)
        converter = _FakeWindowConverter(_pages(pages))
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(window), embedder)
        captured = _capture_segments_via_chunking(monkeypatch)

        result = _run_worker(pdf)

        assert result["success"] is True
        assert converter.calls == [(pdf, _NO_PAGE_RANGE)]
        assert converter.unload_calls == 1
        assert [s["page"] for s in captured[0]] == list(range(1, pages + 1))

    def test_pages_one_over_window_split_into_two_windows(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """5 pages / window 4 -> (1,4) then the (5,5) remainder."""
        pdf = _write_fake_pdf(tmp_path)
        converter = _FakeWindowConverter(_pages(5))
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(4), embedder)
        captured = _capture_segments_via_chunking(monkeypatch)

        result = _run_worker(pdf)

        assert result["success"] is True
        assert converter.calls == [(pdf, (1, 4)), (pdf, (5, 5))]
        assert converter.unload_calls == 2
        assert [s["page"] for s in captured[0]] == [1, 2, 3, 4, 5]

    def test_unknown_page_count_falls_back_to_whole_document(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """pdf_page_count -> 0 (unreadable PDF): single whole convert, no raise."""
        pdf = _write_fake_pdf(tmp_path)
        converter = _FakeWindowConverter(_pages(7))
        embedder = _FakeEmbedder()
        _install_worker_stubs(
            monkeypatch, converter, _window_cfg(3), embedder, page_count=0
        )
        captured = _capture_segments_via_chunking(monkeypatch)

        result = _run_worker(pdf)

        assert result["success"] is True
        assert converter.calls == [(pdf, _NO_PAGE_RANGE)]
        assert converter.unload_calls == 1
        assert [s["page"] for s in captured[0]] == list(range(1, 8))

    def test_embeddings_reach_documents_as_float32_rows(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The worker's compact transport carries through to stored documents."""
        pdf = _write_fake_pdf(tmp_path)
        converter = _FakeWindowConverter(_pages(7))
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(3), embedder)
        _capture_segments_via_chunking(monkeypatch)

        result = _run_worker(pdf)

        for document in result["documents"]:
            embedding = document["embedding"]
            assert isinstance(embedding, np.ndarray)
            assert embedding.dtype == np.float32
            assert np.array_equal(
                embedding, np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
            )


class TestSegmentExtension:
    """The per-window segment loop (_extend_segments_from_document)."""

    def test_empty_items_skipped_and_labels_attached(self) -> None:
        """The historical loop shape: skip falsy text, keep order, attach labels.

        Whitespace-only items pass through here (the chunker drops them
        later); only items with no/empty ``.text`` are skipped.
        """
        content = SimpleNamespace(
            texts=[
                _FakeTextItem("Body paragraph.", 1),
                _FakeTextItem("", 1),
                _FakeTextItem("   ", 2),
                _FakeTextItem("A Heading", 3, label="section_header"),
                _FakeTextItem("Trailing body.", 3),
            ]
        )

        segments: list[dict[str, Any]] = []
        processor._extend_segments_from_document(content, segments)

        assert segments == [
            {"text": "Body paragraph.", "page": 1},
            {"text": "   ", "page": 2},
            {"text": "A Heading", "page": 3, "label": "section_header"},
            {"text": "Trailing body.", "page": 3},
        ]

    def test_no_texts_is_a_noop(self) -> None:
        """Empty or missing .texts extend nothing (whole-document fallback)."""
        segments: list[dict[str, Any]] = []

        processor._extend_segments_from_document(SimpleNamespace(texts=[]), segments)
        processor._extend_segments_from_document(SimpleNamespace(), segments)

        assert segments == []

    def test_mixed_items_within_one_window_through_the_worker(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """One window's document with empty/whitespace/labeled items merges as before."""
        pdf = _write_fake_pdf(tmp_path)
        pages = {
            1: [
                _FakeTextItem("Body paragraph.", 1),
                _FakeTextItem("", 1),
                _FakeTextItem("A Heading", 1, label="section_header"),
            ],
            2: [_FakeTextItem("   ", 2), _FakeTextItem("More body.", 2)],
        }
        converter = _FakeWindowConverter(pages)
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(200), embedder)
        captured = _capture_segments_via_chunking(monkeypatch)

        result = _run_worker(pdf)

        assert result["success"] is True
        # The merged segment stream keeps the historical loop shape: only the
        # empty item is skipped; the whitespace item survives here (the real
        # chunker would drop it) and the label attaches.
        assert captured[0] == [
            {"text": "Body paragraph.", "page": 1},
            {"text": "A Heading", "page": 1, "label": "section_header"},
            {"text": "   ", "page": 2},
            {"text": "More body.", "page": 2},
        ]
        # Blank chunks were dropped by the worker's dedup: only real text is
        # embedded and carried into documents.
        texts = [d["chunk_text"] for d in result["documents"]]
        assert texts == ["Body paragraph.", "A Heading", "More body."]
        assert [d["page_number"] for d in result["documents"]] == [1, 1, 2]


class TestScrapedTickRebasing:
    """Docling DEBUG page-batch ticks rebase to continuous absolute progress."""

    def _install_scrape_capture(
        self, monkeypatch: pytest.MonkeyPatch, recorder: _ScrapeRecorder
    ) -> None:
        """Capture the on_page_batch callback the worker registers."""

        @contextmanager
        def fake_scraped_page_progress(on_tick: Callable[[int, int], None]):
            recorder.on_tick = on_tick
            try:
                yield
            finally:
                recorder.on_tick = None

        monkeypatch.setattr(
            processor, "scraped_page_progress", fake_scraped_page_progress
        )

    @staticmethod
    def _extract_events(queue: _CaptureQueue, pdf: Path) -> list[tuple[int, int]]:
        return [
            (item[3], item[4])
            for item in queue.items
            if isinstance(item, tuple)
            and item[:2] == ("phase", str(pdf))
            and item[2] == "extract"
        ]

    def test_ticks_rebase_to_continuous_absolute_progress(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Per-window scraper counters (done, window_total) emit (done+offset, real_total)."""
        pdf = _write_fake_pdf(tmp_path)
        recorder = _ScrapeRecorder()
        converter = _FakeWindowConverter(_pages(7), scrape_recorder=recorder)
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(3), embedder)
        self._install_scrape_capture(monkeypatch, recorder)
        queue = _CaptureQueue()

        result = _run_worker(pdf, progress_queue=queue, scrape_docling_pages=True)

        assert result["success"] is True
        assert converter.calls == [(pdf, (1, 3)), (pdf, (4, 6)), (pdf, (7, 7))]
        # The scraper fired inside each conversion (callback was captured).
        assert recorder.on_tick is None  # released after the run
        # Seeds: indeterminate (0,0) at start and after the fast-path reject,
        # then the scraper seed with the REAL page count; per-window raw ticks
        # (1..3, 3) / (1..3, 3) / (1, 1) rebase to a continuous 1..7 against
        # the real total.
        assert self._extract_events(queue, pdf) == [
            (0, 0),
            (0, 0),
            (0, 7),
            (1, 7),
            (2, 7),
            (3, 7),
            (4, 7),
            (5, 7),
            (6, 7),
            (7, 7),
        ]

    def test_non_windowed_ticks_pass_through_unmodified(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Without windowing the scraper's raw (done, total) is forwarded as-is."""
        pdf = _write_fake_pdf(tmp_path)
        recorder = _ScrapeRecorder()
        converter = _FakeWindowConverter(_pages(7), scrape_recorder=recorder)
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(0), embedder)
        self._install_scrape_capture(monkeypatch, recorder)
        queue = _CaptureQueue()

        result = _run_worker(pdf, progress_queue=queue, scrape_docling_pages=True)

        assert result["success"] is True
        assert converter.calls == [(pdf, _NO_PAGE_RANGE)]
        assert self._extract_events(queue, pdf) == [
            (0, 0),
            (0, 0),
            (0, 7),
            (1, 7),
            (2, 7),
            (3, 7),
            (4, 7),
            (5, 7),
            (6, 7),
            (7, 7),
        ]

    def test_scrape_enabled_without_queue_skips_scraper(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """scrape_docling_pages needs a progress queue; without one, plain loop."""
        pdf = _write_fake_pdf(tmp_path)
        recorder = _ScrapeRecorder()
        converter = _FakeWindowConverter(_pages(7), scrape_recorder=recorder)
        embedder = _FakeEmbedder()
        _install_worker_stubs(monkeypatch, converter, _window_cfg(3), embedder)
        self._install_scrape_capture(monkeypatch, recorder)

        result = _run_worker(pdf, progress_queue=None, scrape_docling_pages=True)

        assert result["success"] is True
        assert converter.calls == [(pdf, (1, 3)), (pdf, (4, 6)), (pdf, (7, 7))]
        assert converter.unload_calls == 3
        # The scraper context manager was never entered: no callback captured.
        assert recorder.on_tick is None
