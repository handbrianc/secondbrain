"""Tests for the shared docling converter factory ``docling_factory``.

Covers the behavioral contract of :func:`get_shared_converter`:

- lazy import (docling must NOT be imported at module import time)
- singleton identity (same object on repeated calls)
- race-safe construction across threads
- an optional parity check against the pre-refactor inline options
  (skipped when real docling is unavailable, e.g. stubbed out by the
  ``tests/test_document/conftest.py`` session fixture).
"""

import importlib.util
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import secondbrain.document.docling_factory as docling_factory
from secondbrain.document.docling_factory import (
    close_shared_converter,
    get_shared_converter,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> Iterator[None]:
    """Reset the module singleton before and after each test."""
    close_shared_converter()
    yield
    close_shared_converter()


def _docling_is_stubbed() -> bool:
    """True when the conftest stub replaced the real docling package."""
    import docling

    return isinstance(docling, MagicMock)


def _real_docling_available() -> bool:
    """True when a REAL (non-stubbed) docling install is importable."""
    return not _docling_is_stubbed() and importlib.util.find_spec("docling") is not None


# ---------------------------------------------------------------------------
# Lazy import (non-XL gate, runs even without docling installed)
# ---------------------------------------------------------------------------


def test_modules_do_not_import_docling_at_import_time() -> None:
    """Importing factory/ingestor/processor must not import docling."""
    code = (
        "import sys\n"
        "import secondbrain.document.docling_factory\n"
        "import secondbrain.document.ingestor._sync\n"
        "import secondbrain.document.processor\n"
        "assert 'docling' not in sys.modules\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"lazy-import violated:\n{proc.stdout}\n{proc.stderr}"


# ---------------------------------------------------------------------------
# Singleton identity
# ---------------------------------------------------------------------------


def test_get_shared_converter_returns_same_object() -> None:
    """Identity contract holds with or without real docling (stub-safe)."""
    a = get_shared_converter()
    b = get_shared_converter()
    assert a is b


def test_close_shared_converter_forces_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close_shared_converter resets so the next call rebuilds the converter."""
    calls = {"builds": 0}
    real_build = docling_factory._build_converter

    def counting_build() -> object:
        calls["builds"] += 1
        return real_build()

    monkeypatch.setattr(docling_factory, "_build_converter", counting_build)

    get_shared_converter()
    get_shared_converter()
    assert calls["builds"] == 1

    close_shared_converter()
    get_shared_converter()
    assert calls["builds"] == 2


# ---------------------------------------------------------------------------
# Concurrency: no double-build / deadlock
# ---------------------------------------------------------------------------


def test_concurrent_callers_get_same_object() -> None:
    n_threads = 8
    results: list[Any] = [None] * n_threads
    errors: list[BaseException] = []
    barrier = threading.Barrier(n_threads)

    def worker(idx: int) -> None:
        try:
            barrier.wait(timeout=30)
            results[idx] = get_shared_converter()
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"threads raised: {errors}"
    assert all(r is results[0] for r in results), "converter was double-built"


# ---------------------------------------------------------------------------
# Parity: shared factory == pre-refactor inline options (best-effort)
# ---------------------------------------------------------------------------


def _segments(converter: Any, pdf_path: Path) -> list[dict]:
    result = converter.convert(pdf_path)
    content = result.document
    segments: list[dict] = []
    if hasattr(content, "texts") and content.texts:
        for item in content.texts:
            text = getattr(item, "text", "")
            if not text:
                continue
            segments.append({"text": text})
    return segments


def test_shared_converter_matches_inline_options(tmp_path: Path) -> None:
    """Shared factory output equals the pre-refactor inline converter output."""
    if not _real_docling_available():
        pytest.skip("real docling not available in this test session (stubbed)")
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("fpdf not installed for PDF creation")

    pdf_path = tmp_path / "sample.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(
        0,
        10,
        "SecondBrain test document\n\n"
        "This is sample content for PDF extraction covering machine learning.",
    )
    pdf.output(str(pdf_path))

    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    old_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(
                    do_ocr=True,
                    do_table_structure=True,
                    ocr_options=RapidOcrOptions(
                        backend="torch",
                        rapidocr_params={"EngineConfig.torch.use_mps": True},
                    ),
                    accelerator_options=AcceleratorOptions(
                        device=AcceleratorDevice.AUTO, num_threads=4
                    ),
                )
            )
        }
    )

    old_segments = _segments(old_converter, pdf_path)
    new_segments = _segments(get_shared_converter(), pdf_path)

    assert new_segments == old_segments
