"""Tests for the shared docling converter factory ``docling_factory``.

Covers the behavioral contract of :func:`get_shared_converter`:

- lazy import (docling must NOT be imported at module import time)
- singleton identity (same object on repeated calls)
- race-safe construction across threads
- a real-docling smoke test run in a subprocess (keeps the conftest stubs
  intact in this process) verifying the cached OCR converter config.
"""

import subprocess
import sys
import threading
from collections.abc import Iterator
from typing import Any

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


# ---------------------------------------------------------------------------
# Lazy import (non-XL gate, runs even without docling installed)
# ---------------------------------------------------------------------------


@pytest.mark.slow
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


@pytest.mark.slow
def test_shared_converter_builds_real_cached_ocr_converter() -> None:
    """Real docling builds a cached OCR converter, verified in a subprocess.

    Running in a subprocess keeps the real docling import and the unmasking of
    the session's docling stubs out of this process, so later tests in a
    single-process run never observe half-stub/half-real docling state.
    """
    code = (
        "import sys\n"
        "from unittest.mock import MagicMock\n"
        "for name in list(sys.modules):\n"
        "    if name.startswith('docling') and isinstance(sys.modules[name], MagicMock):\n"
        "        del sys.modules[name]\n"
        "from secondbrain.document.docling_factory import (\n"
        "    close_shared_converter,\n"
        "    get_shared_converter,\n"
        ")\n"
        "assert get_shared_converter() is get_shared_converter()\n"
        "from docling.datamodel.base_models import InputFormat\n"
        "pipeline_options = (\n"
        "    get_shared_converter().format_to_options[InputFormat.PDF].pipeline_options\n"
        ")\n"
        "assert pipeline_options is not None\n"
        "assert pipeline_options.model_dump().get('do_ocr') is True\n"
        "close_shared_converter()\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"real-converter check failed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "OK" in proc.stdout
