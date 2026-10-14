"""Env-gated tests for the REAL (unstubbed) docling converter paths.

The test session stubs docling with MagicMocks (root + test_document
conftest), so the real converter-construction code in ``docling_factory`` —
the audio ASR converter (WhisperS2T preset lookup, device coercion, ASR
pipeline format options) and the pypdfium2 PDF-backend probe — is never
exercised by a normal run (test-suite audit §4.3 item 3).

These tests opt in via ``SECONDBRAIN_RUN_DOCLING_TESTS=1`` and, mirroring
``test_docling_factory``'s real-docling smoke test, run in a subprocess so the
session's docling stubs stay intact in the pytest process. They skip cleanly
unless the env var is set AND docling is genuinely installed (stubbing defeats
``importlib.util.find_spec``, so the distribution metadata is used).
"""

import importlib.metadata
import os
import subprocess
import sys

import pytest


def _docling_installed() -> bool:
    """Whether the real docling distribution is importable in this env.

    Uses package metadata instead of ``find_spec``: the test session injects
    MagicMock stubs into ``sys.modules``, which would otherwise masquerade as
    an installed package.
    """
    try:
        importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


_DOCLING_GATE = (
    bool(os.environ.get("SECONDBRAIN_RUN_DOCLING_TESTS")) and _docling_installed()
)

skipif_no_real_docling = pytest.mark.skipif(
    not _DOCLING_GATE,
    reason="requires real docling package (set SECONDBRAIN_RUN_DOCLING_TESTS=1)",
)


def _run_subprocess(script: str, pdf_path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script, pdf_path],
        capture_output=True,
        text=True,
        timeout=600,
    )


@skipif_no_real_docling
@pytest.mark.slow
def test_real_audio_converter_and_pdf_backend(sample_pdf_path) -> None:
    """Exercise the real docling audio converter and PDF-backend probe.

    Covers ``_build_audio_converter`` (WhisperS2T preset resolution, device
    coercion, AsrPipeline/AudioFormatOption construction, singleton caching)
    and ``_open_pdf_backend`` + page text probing (the pypdfium2 text-layer
    fast-path check) with the genuine docling package.
    """
    code = (
        "import sys\n"
        "from unittest.mock import MagicMock\n"
        "# Defensive: drop any injected docling stubs so the real package is used.\n"
        "for name in list(sys.modules):\n"
        "    if name.startswith('docling') and isinstance(sys.modules[name], MagicMock):\n"
        "        del sys.modules[name]\n"
        "from secondbrain.document import docling_factory\n"
        "audio = docling_factory.get_audio_converter()\n"
        "assert audio is docling_factory.get_audio_converter(), 'singleton broken'\n"
        "from docling.datamodel.base_models import InputFormat\n"
        "from docling.document_converter import DocumentConverter\n"
        "assert isinstance(audio, DocumentConverter)\n"
        "option = audio.format_to_options[InputFormat.AUDIO]\n"
        "assert option.pipeline_options is not None\n"
        "assert option.pipeline_cls is not None\n"
        "pdf_path = sys.argv[1]\n"
        "backend = docling_factory._open_pdf_backend(pdf_path)\n"
        "pages = list(backend.iter_pages())\n"
        "assert pages, 'expected the sample PDF to expose at least one page'\n"
        "has_text = any(\n"
        "    isinstance(cell.text, str) and cell.text.strip()\n"
        "    for page in pages\n"
        "    for cell in page.get_text_cells()\n"
        ")\n"
        "assert has_text, 'sample PDF should expose an embedded text layer'\n"
        "backend.unload()\n"
        "assert docling_factory.pdf_has_text_layer(pdf_path) is True\n"
        "docling_factory.close_shared_converter()\n"
        "print('OK')\n"
    )
    proc = _run_subprocess(code, str(sample_pdf_path))
    assert proc.returncode == 0, (
        f"real-docling converter check failed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "OK" in proc.stdout


@skipif_no_real_docling
@pytest.mark.slow
def test_real_text_layer_probe_matches_real_backend(sample_pdf_path) -> None:
    """``pdf_has_text_layer`` routes the text PDF through the real backend."""
    code = (
        "import sys\n"
        "from secondbrain.document.docling_factory import pdf_has_text_layer\n"
        "assert pdf_has_text_layer(sys.argv[1]) is True\n"
        "assert pdf_has_text_layer(sys.argv[1] + '.does-not-exist') is False\n"
        "print('OK')\n"
    )
    proc = _run_subprocess(code, str(sample_pdf_path))
    assert proc.returncode == 0, (
        f"real-docling text-layer probe failed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "OK" in proc.stdout
