"""Tests for the table-structure speed-tune config surface.

Covers the three config knobs introduced for the safe docling speed-tune:

- ``pdf_table_structure_enabled`` (now OFF by default)
- ``pdf_table_fast_mode`` (TableFormer FAST vs ACCURATE mode)
- ``pdf_table_cell_matching`` (docling table cell post-processing)

and how :func:`_build_pdf_format_option` translates them into docling's
``TableStructureOptions`` (``mode`` + ``do_cell_matching``) only when table
structure is enabled.

The docling pipeline classes are mocked so the wiring assertions hold whether
or not real docling is installed (the ``tests/test_document/conftest.py``
session fixture stubs docling under ``sys.modules``). The config layer is
driven through the ``SECONDBRAIN_PDF_TABLE_*`` environment variables plus a
``get_config.cache_clear()`` so the knobs vary in a self-contained way.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.document import docling_factory

# Sentinels stand in for the docling ``TableFormerMode`` enum values so the
# wiring assertions are readable and independent of the (possibly stubbed) enum.
FAST_MODE = object()
ACCURATE_MODE = object()


@pytest.fixture(autouse=True)
def _clear_config_cache() -> Iterator[None]:
    """Rebuild the cached Config before and after each test so env picks up."""
    from secondbrain.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _set_table_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    structure: str = "false",
    fast: str = "true",
    cell: str = "false",
) -> None:
    """Set the SECONDBRAIN_PDF_TABLE_* env vars and rebuild the config cache."""
    from secondbrain.config import get_config

    monkeypatch.setenv("SECONDBRAIN_PDF_TABLE_STRUCTURE_ENABLED", structure)
    monkeypatch.setenv("SECONDBRAIN_PDF_TABLE_FAST_MODE", fast)
    monkeypatch.setenv("SECONDBRAIN_PDF_TABLE_CELL_MATCHING", cell)
    get_config.cache_clear()


def _capture_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock]:
    """Replace the docling modules the factory imports with capture mocks.

    ``docling_factory._build_pdf_format_option`` imports docling submodules
    lazily from ``sys.modules``. The conftest's MagicMock stubs get cloned by
    the import machinery, so here we swap in real :class:`ModuleType` objects
    carrying capture mocks, which the factory reliably sees.

    Returns
    -------
        (pdf_options_mock, table_structure_mock): ``PdfPipelineOptions`` and
        ``TableStructureOptions`` capture mocks. ``PdfFormatOption`` is patched
        to echo the ``pipeline_options`` it was built with.
    """
    import docling.datamodel.pipeline_options as po_import

    po: Any = po_import
    pdf_options_mock = MagicMock()
    table_structure_mock = MagicMock()

    po.PdfPipelineOptions = pdf_options_mock
    po.TableStructureOptions = table_structure_mock
    po.RapidOcrOptions = MagicMock()
    po.TableFormerMode = SimpleNamespace(FAST=FAST_MODE, ACCURATE=ACCURATE_MODE)

    ao: Any = ModuleType("docling.datamodel.accelerator_options")
    ao.AcceleratorDevice = MagicMock()
    ao.AcceleratorOptions = MagicMock()

    dc: Any = ModuleType("docling.document_converter")

    def _fake_format_option(
        pipeline_options: object = None, **kwargs: object
    ) -> MagicMock:
        obj = MagicMock()
        obj.pipeline_options = pipeline_options
        return obj

    dc.PdfFormatOption = _fake_format_option

    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", po)
    monkeypatch.setitem(sys.modules, "docling.datamodel.accelerator_options", ao)
    monkeypatch.setitem(sys.modules, "docling.document_converter", dc)

    return pdf_options_mock, table_structure_mock


# ---------------------------------------------------------------------------
# Config defaults (real config layer)
# ---------------------------------------------------------------------------


def test_config_table_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Table structure is OFF by default; fast mode ON; cell matching OFF."""
    for var in (
        "SECONDBRAIN_PDF_TABLE_STRUCTURE_ENABLED",
        "SECONDBRAIN_PDF_TABLE_FAST_MODE",
        "SECONDBRAIN_PDF_TABLE_CELL_MATCHING",
    ):
        monkeypatch.delenv(var, raising=False)

    from secondbrain.config import config

    c = config()
    assert c.pdf_table_structure_enabled is False
    assert c.pdf_table_fast_mode is True
    assert c.pdf_table_cell_matching is False


def test_config_reads_env_toggles(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SECONDBRAIN_PDF_TABLE_* env vars drive the config fields."""
    _set_table_env(monkeypatch, structure="true", fast="false", cell="true")

    from secondbrain.config import config

    c = config()
    assert c.pdf_table_structure_enabled is True
    assert c.pdf_table_fast_mode is False
    assert c.pdf_table_cell_matching is True


# ---------------------------------------------------------------------------
# Factory wiring (stub-robust: asserts exact kwargs passed to docling classes)
# ---------------------------------------------------------------------------


def test_table_structure_disabled_does_not_set_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """do_table_structure=False leaves table_structure_options unset."""
    _set_table_env(monkeypatch, structure="false")
    pdf_options_mock, table_structure_mock = _capture_pipeline(monkeypatch)

    option = docling_factory._build_pdf_format_option(
        do_ocr=False, do_table_structure=False
    )

    pdf_kwargs = pdf_options_mock.call_args.kwargs
    assert pdf_kwargs["do_table_structure"] is False
    assert "table_structure_options" not in pdf_kwargs
    table_structure_mock.assert_not_called()
    # PdfFormatOption carries the pipeline we built.
    assert option.pipeline_options is pdf_options_mock.return_value


def test_table_structure_enabled_fast_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast mode + cell matching off (defaults) map onto TableStructureOptions."""
    import docling.datamodel.pipeline_options as po

    _set_table_env(monkeypatch, structure="true", fast="true", cell="false")
    pdf_options_mock, table_structure_mock = _capture_pipeline(monkeypatch)

    docling_factory._build_pdf_format_option(do_ocr=False, do_table_structure=True)

    assert table_structure_mock.call_args.kwargs == {
        "mode": po.TableFormerMode.FAST,
        "do_cell_matching": False,
    }
    assert (
        pdf_options_mock.call_args.kwargs["table_structure_options"]
        is table_structure_mock.return_value
    )


def test_table_structure_accurate_and_cell_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast mode off -> ACCURATE; cell matching on -> True."""
    import docling.datamodel.pipeline_options as po

    _set_table_env(monkeypatch, structure="true", fast="false", cell="true")
    pdf_options_mock, table_structure_mock = _capture_pipeline(monkeypatch)

    docling_factory._build_pdf_format_option(do_ocr=False, do_table_structure=True)

    assert table_structure_mock.call_args.kwargs == {
        "mode": po.TableFormerMode.ACCURATE,
        "do_cell_matching": True,
    }
    assert (
        pdf_options_mock.call_args.kwargs["table_structure_options"]
        is table_structure_mock.return_value
    )


def test_build_converter_honors_table_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The OCR/shared converter reads table structure from config (not hardcoded)."""
    captured: dict[str, bool] = {}

    def capture(*, do_ocr: bool, do_table_structure: bool) -> MagicMock:
        captured["do_ocr"] = do_ocr
        captured["do_table_structure"] = do_table_structure
        return MagicMock()

    monkeypatch.setattr(docling_factory, "_build_docling_converter", capture)

    _set_table_env(monkeypatch, structure="false")
    docling_factory._build_converter()
    assert captured["do_ocr"] is True
    assert captured["do_table_structure"] is False

    _set_table_env(monkeypatch, structure="true")
    docling_factory._build_converter()
    assert captured["do_ocr"] is True
    assert captured["do_table_structure"] is True


def test_text_converter_honors_table_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The text-only converter keeps reading table structure from config."""
    captured: dict[str, bool] = {}

    def capture(*, do_ocr: bool, do_table_structure: bool) -> MagicMock:
        captured["do_ocr"] = do_ocr
        captured["do_table_structure"] = do_table_structure
        return MagicMock()

    monkeypatch.setattr(docling_factory, "_build_docling_converter", capture)

    _set_table_env(monkeypatch, structure="false")
    docling_factory._build_text_converter()
    assert captured["do_ocr"] is False
    assert captured["do_table_structure"] is False

    _set_table_env(monkeypatch, structure="true")
    docling_factory._build_text_converter()
    assert captured["do_ocr"] is False
    assert captured["do_table_structure"] is True
