"""On-demand OCR tests for the per-document converter resolver.

These tests exercise the on-demand OCR contract introduced in the ingestion
performance plan:

- default: a digital PDF (embedded text layer) is extracted with a text-only
  converter (``do_ocr=False``) — the fast path;
- scanned PDF (no text layer) still runs OCR (parity preserved);
- ``pdf_ocr_enabled=True`` forces OCR regardless of the text layer;
- non-PDF formats are unaffected and always use the OCR converter.

Real docling is stubbed by the ``tests/test_document/conftest.py`` session
fixture (it replaces docling submodules with mock objects in ``sys.modules``).
Under that stub the pypdfium2 backend is un-importable, so :func:`pdf_has_text_layer`
conservatively returns False. To get deterministic routing the tests either
monkeypatch ``docling_factory.pdf_has_text_layer`` (resolver tests) or the
probe's backend-opening seam ``docling_factory._open_pdf_backend`` (probe unit
tests), and drive the config flags through a monkeypatched ``secondbrain.config.config``.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from secondbrain.document import docling_factory
from secondbrain.document.docling_factory import (
    close_shared_converter,
    get_converter_for_path,
    get_shared_converter,
    get_text_converter,
    pdf_has_text_layer,
)


@pytest.fixture(autouse=True)
def _reset_singletons() -> Iterator[None]:
    """Reset the shared converter singletons before and after each test."""
    close_shared_converter()
    yield
    close_shared_converter()


class _FakeCfg:
    """Minimal stand-in for the Config object's PDF fields."""

    def __init__(
        self,
        ocr: bool = False,
        table: bool = True,
        fast: bool = True,
        cell_matching: bool = False,
    ) -> None:
        self.pdf_ocr_enabled = ocr
        self.pdf_table_structure_enabled = table
        self.pdf_table_fast_mode = fast
        self.pdf_table_cell_matching = cell_matching
        # Docling speed levers — defaults preserve current behavior (False / auto).
        self.pdf_accelerator_device = "auto"
        self.pdf_num_threads = 4
        self.pdf_threaded_pipeline = False
        self.pdf_layout_batch_size = 4
        self.pdf_generate_page_images = False
        self.pdf_generate_picture_images = False
        self.pdf_images_scale = 1.0


@pytest.fixture
def fake_config(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch the resolved config to control PDF OCR flags."""

    def _set(*, ocr: bool = False, table: bool = True) -> _FakeCfg:
        cfg = _FakeCfg(ocr=ocr, table=table)
        monkeypatch.setattr("secondbrain.config.config", lambda: cfg)
        return cfg

    return _set


# ---------------------------------------------------------------------------
# BASELINE CHARACTERIZATION: default digital -> OCR off; forced -> OCR on.
# Before this todo the shared factory returned a single fixed converter with
# ``do_ocr=True``. The new contract routes a digital PDF to the text-only
# converter by default, while ``pdf_ocr_enabled=True`` still uses the OCR
# converter (``do_ocr=True``), preserving the scanned/forced behavior.
# ---------------------------------------------------------------------------


def test_baseline_default_digital_skips_ocr_and_force_on_runs_ocr(
    fake_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_config(ocr=False)
    monkeypatch.setattr(docling_factory, "pdf_has_text_layer", lambda p: True)
    assert get_converter_for_path("baseline.pdf") is get_text_converter()

    fake_config(ocr=True)
    assert get_converter_for_path("baseline.pdf") is get_shared_converter()


# ---------------------------------------------------------------------------
# Resolver routing (stub-driven)
# ---------------------------------------------------------------------------


def test_default_digital_pdf_uses_text_only_path(
    fake_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pdf_ocr_enabled=False + text layer present -> text-only converter."""
    fake_config(ocr=False)
    monkeypatch.setattr(docling_factory, "pdf_has_text_layer", lambda p: True)
    assert get_converter_for_path("digital.pdf") is get_text_converter()


def test_scanned_pdf_uses_ocr_path(
    fake_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No embedded text layer -> OCR converter (parity for scanned PDFs)."""
    fake_config(ocr=False)
    monkeypatch.setattr(docling_factory, "pdf_has_text_layer", lambda p: False)
    assert get_converter_for_path("scanned.pdf") is get_shared_converter()


def test_force_ocr_enabled_causes_ocr_path(
    fake_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pdf_ocr_enabled=True -> OCR converter even when a text layer exists."""
    probe_calls: list[str] = []

    def probe(p: str) -> bool:
        probe_calls.append(p)
        return True

    fake_config(ocr=True)
    monkeypatch.setattr(docling_factory, "pdf_has_text_layer", probe)
    assert get_converter_for_path("forced.pdf") is get_shared_converter()
    # Forced OCR short-circuits before probing the text layer.
    assert probe_calls == []


def test_image_format_still_uses_ocr_converter(
    fake_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-PDF formats route to the OCR converter, untouched by the probe."""
    probe_calls: list[str] = []

    def probe(p: str) -> bool:
        probe_calls.append(p)
        return True

    fake_config(ocr=False)
    monkeypatch.setattr(docling_factory, "pdf_has_text_layer", probe)
    assert get_converter_for_path("scan.png") is get_shared_converter()
    assert get_converter_for_path("photo.jpg") is get_shared_converter()
    assert probe_calls == []


# ---------------------------------------------------------------------------
# Probe helper unit tests (via the backend-open seam)
# ---------------------------------------------------------------------------


def _fake_page_with_text(texts: list[str]) -> MagicMock:
    page = MagicMock()
    cells = []
    for t in texts:
        cell = MagicMock()
        cell.text = t
        cells.append(cell)
    page.get_text_cells.return_value = cells
    return page


def _backend_with_pages(page_texts: list[list[str]]) -> MagicMock:
    backend = MagicMock()
    backend.iter_pages.return_value = [_fake_page_with_text(t) for t in page_texts]
    return backend


def test_pdf_has_text_layer_detects_digital(monkeypatch: pytest.MonkeyPatch) -> None:
    """At least one page with non-empty text -> digital (True)."""
    backend = _backend_with_pages([["", ""], ["  ", "Some real text"]])

    def fake_open(path: object) -> MagicMock:
        return backend

    monkeypatch.setattr(docling_factory, "_open_pdf_backend", fake_open)
    assert pdf_has_text_layer("digital.pdf") is True


def test_pdf_has_text_layer_empty_pages_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No non-empty text on any page -> scanned (False)."""
    backend = _backend_with_pages([["", ""], ["   ", ""]])

    def fake_open(path: object) -> MagicMock:
        return backend

    monkeypatch.setattr(docling_factory, "_open_pdf_backend", fake_open)
    assert pdf_has_text_layer("scanned.pdf") is False


def test_pdf_has_text_layer_falls_back_on_backend_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend unavailable -> conservatively returns False (needs OCR)."""

    def boom(path: object) -> MagicMock:
        raise RuntimeError("backend unavailable")

    monkeypatch.setattr(docling_factory, "_open_pdf_backend", boom)
    assert pdf_has_text_layer("broken.pdf") is False
