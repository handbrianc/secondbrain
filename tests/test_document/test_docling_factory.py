"""Tests for the shared docling converter factory ``docling_factory``.

Covers the behavioral contract of :func:`get_shared_converter`:

- lazy import (docling must NOT be imported at module import time)
- singleton identity (same object on repeated calls)
- race-safe construction across threads
- a real-docling smoke test run in a subprocess (keeps the conftest stubs
  intact in this process) verifying the cached OCR converter config.
"""

import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
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


_repo_src = str(Path(__file__).resolve().parents[2] / "src")


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get("SECONDBRAIN_RUN_DOCLING_TESTS"),
    reason="real docling subprocess test (set SECONDBRAIN_RUN_DOCLING_TESTS=1)",
)
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


def test_converter_build_defers_torch_and_transformers_to_pipeline_init() -> None:
    """Building a converter must not import torch/transformers (subprocess).

    Verifies the deferred RT-DETR patch hooks installed by
    ``_install_pdf_conversion_hooks``: converter construction imports neither
    torch nor transformers and does not apply the MPS patch; the first
    ``_get_pipeline`` call applies it exactly once. Docling is stubbed so the
    subprocess stays fast and the session's stubs are untouched.
    """
    code = (
        "import sys\n"
        "from unittest.mock import MagicMock\n"
        "for name in (\n"
        "    'docling', 'docling.datamodel', 'docling.datamodel.settings',\n"
        "    'docling.datamodel.accelerator_options',\n"
        "    'docling.datamodel.base_models',\n"
        "    'docling.datamodel.pipeline_options',\n"
        "    'docling.document_converter',\n"
        "    'docling.utils', 'docling.utils.accelerator_utils',\n"
        "):\n"
        "    sys.modules.setdefault(name, MagicMock())\n"
        "import secondbrain.utils.mps_patch as mps_patch\n"
        "calls: list[int] = []\n"
        "mps_patch.patch_transformers_for_mps = lambda: calls.append(1)\n"
        "from secondbrain.document.docling_factory import _build_docling_converter\n"
        "conv = _build_docling_converter(do_ocr=True, do_table_structure=True)\n"
        "assert 'torch' not in sys.modules, 'torch imported at converter build'\n"
        "assert 'transformers' not in sys.modules, 'transformers imported at build'\n"
        "assert calls == [], 'patch applied at converter build time'\n"
        "conv._get_pipeline()\n"
        "assert len(calls) == 1, f'patch hook fired {len(calls)} times, expected 1'\n"
        "conv._get_pipeline()\n"
        "assert len(calls) == 1, 'patch re-applied on second pipeline init'\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": str(_repo_src)},
    )
    assert proc.returncode == 0, (
        f"deferred-patch check failed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "OK" in proc.stdout


# ---------------------------------------------------------------------------
# Bounded-memory PDF settings: backend mapping, queue bound, SYCL cache,
# and the accelerator preflight (tasks 5.2 of add-pdf-ingest-memory-bounds)
# ---------------------------------------------------------------------------

_SYCL_ENV_VARS = ("SYCL_CACHE_PERSISTENT", "SYCL_CACHE_DIR")


@pytest.fixture
def clean_sycl_env() -> Iterator[None]:
    """Run with no SYCL_CACHE_* env vars, restoring anything the code sets.

    ``_persist_sycl_jit_cache_on_xpu`` mutates ``os.environ`` via setdefault;
    snapshot/restore here keeps the process env unchanged across tests.
    """
    saved = {name: os.environ.get(name) for name in _SYCL_ENV_VARS}
    for name in _SYCL_ENV_VARS:
        os.environ.pop(name, None)
    yield
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _pdf_cfg(**overrides: Any) -> Any:
    """Minimal config stand-in exposing the fields the factory reads."""

    class _FakeCfg:
        pdf_backend = "pypdfium"
        pdf_accelerator_device = "cpu"
        pdf_num_threads = 4
        pdf_threaded_pipeline = False
        pdf_layout_batch_size = 4
        pdf_pipeline_queue_max_size = 16
        pdf_generate_page_images = False
        pdf_generate_picture_images = False
        pdf_images_scale = 1.0
        pdf_table_structure_enabled = False
        pdf_table_fast_mode = True
        pdf_table_cell_matching = False
        accelerator_min_free_ram_mib = 2048

    cfg = _FakeCfg()
    for name, value in overrides.items():
        setattr(cfg, name, value)
    return cfg


def _stub_pdf_cfg(monkeypatch: pytest.MonkeyPatch, cfg: Any) -> None:
    """Point the factory's lazy ``config()`` lookups at *cfg*."""
    monkeypatch.setattr("secondbrain.config.config", lambda: cfg)


def _fresh_option_mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the auto-created docling option classes with inspectable mocks.

    The session's docling stubs are one shared MagicMock module object, so a
    fresh attribute set on any of its module names is visible to every
    ``from docling... import`` the factory performs; monkeypatch restores the
    previous (auto-created) child mocks afterwards.
    """
    mocks = {
        "PdfFormatOption": MagicMock(name="PdfFormatOption"),
        "PdfPipelineOptions": MagicMock(name="PdfPipelineOptions"),
        "RapidOcrOptions": MagicMock(name="RapidOcrOptions"),
        "AcceleratorDevice": MagicMock(name="AcceleratorDevice"),
        "AcceleratorOptions": MagicMock(name="AcceleratorOptions"),
    }
    monkeypatch.setattr(
        sys.modules["docling.document_converter"],
        "PdfFormatOption",
        mocks["PdfFormatOption"],
    )
    monkeypatch.setattr(
        sys.modules["docling.datamodel.pipeline_options"],
        "PdfPipelineOptions",
        mocks["PdfPipelineOptions"],
    )
    monkeypatch.setattr(
        sys.modules["docling.datamodel.pipeline_options"],
        "RapidOcrOptions",
        mocks["RapidOcrOptions"],
    )
    monkeypatch.setattr(
        sys.modules["docling.datamodel.accelerator_options"],
        "AcceleratorDevice",
        mocks["AcceleratorDevice"],
    )
    monkeypatch.setattr(
        sys.modules["docling.datamodel.accelerator_options"],
        "AcceleratorOptions",
        mocks["AcceleratorOptions"],
    )
    return mocks


class TestPdfBackendSelection:
    """Backend mapping and queue_max_size passthrough of _build_pdf_format_option."""

    def test_queue_max_size_default_16_passed_to_pipeline_options(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The config default (16) reaches the pipeline options unconditionally."""
        mocks = _fresh_option_mocks(monkeypatch)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg())

        docling_factory._build_pdf_format_option(do_ocr=True, do_table_structure=False)

        pipe_call = mocks["PdfPipelineOptions"].call_args
        assert pipe_call.kwargs["queue_max_size"] == 16
        format_call = mocks["PdfFormatOption"].call_args
        assert (
            format_call.kwargs["pipeline_options"]
            is mocks["PdfPipelineOptions"].return_value
        )

    def test_queue_max_size_config_override_reaches_pipeline_options(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A lowered queue bound (e.g. via SECONDBRAIN_PDF_PIPELINE_QUEUE_MAX_SIZE) is passed through."""
        mocks = _fresh_option_mocks(monkeypatch)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(pdf_pipeline_queue_max_size=8))

        docling_factory._build_pdf_format_option(do_ocr=True, do_table_structure=False)

        assert mocks["PdfPipelineOptions"].call_args.kwargs["queue_max_size"] == 8

    def test_queue_max_size_passed_even_for_default_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The bound rides on PdfPipelineOptions itself, not only the threaded one."""
        mocks = _fresh_option_mocks(monkeypatch)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(pdf_threaded_pipeline=False))

        docling_factory._build_pdf_format_option(do_ocr=True, do_table_structure=False)

        pipe_call = mocks["PdfPipelineOptions"].call_args
        assert "queue_max_size" in pipe_call.kwargs
        # Threaded-only kwargs stay absent for the default pipeline class.
        assert "layout_batch_size" not in pipe_call.kwargs

    def test_pypdfium_backend_maps_to_pypdfium_backend_class(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pdf_backend='pypdfium' passes the pypdfium2 backend class through."""

        class _FakePyPdfiumBackend:
            """Sentinel standing in for PyPdfiumDocumentBackend."""

        monkeypatch.setitem(
            sys.modules,
            "docling.backend.pypdfium2_backend",
            SimpleNamespace(PyPdfiumDocumentBackend=_FakePyPdfiumBackend),
        )
        mocks = _fresh_option_mocks(monkeypatch)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(pdf_backend="pypdfium"))

        docling_factory._build_pdf_format_option(do_ocr=True, do_table_structure=False)

        assert (
            mocks["PdfFormatOption"].call_args.kwargs["backend"] is _FakePyPdfiumBackend
        )

    def test_docling_parse_backend_keeps_docling_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pdf_backend='docling-parse' passes no backend: docling's default IS docling-parse."""
        monkeypatch.setitem(
            sys.modules,
            "docling.backend.pypdfium2_backend",
            SimpleNamespace(PyPdfiumDocumentBackend=object),
        )
        mocks = _fresh_option_mocks(monkeypatch)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(pdf_backend="docling-parse"))

        docling_factory._build_pdf_format_option(do_ocr=True, do_table_structure=False)

        assert "backend" not in mocks["PdfFormatOption"].call_args.kwargs

    def test_pypdfium_backend_falls_back_when_backend_module_missing(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Under docling stubs the pypdfium module is absent: keep docling's default."""
        monkeypatch.delitem(
            sys.modules, "docling.backend.pypdfium2_backend", raising=False
        )
        mocks = _fresh_option_mocks(monkeypatch)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(pdf_backend="pypdfium"))

        with caplog.at_level("DEBUG", logger="secondbrain.document.docling_factory"):
            docling_factory._build_pdf_format_option(
                do_ocr=True, do_table_structure=False
            )

        assert "backend" not in mocks["PdfFormatOption"].call_args.kwargs
        assert any(
            "pypdfium2_backend unavailable" in record.message
            for record in caplog.records
        )

    def test_both_backends_share_identical_pipeline_options(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backend choice only swaps the parsing layer: every pipeline kwarg matches."""

        class _FakePyPdfiumBackend:
            pass

        monkeypatch.setitem(
            sys.modules,
            "docling.backend.pypdfium2_backend",
            SimpleNamespace(PyPdfiumDocumentBackend=_FakePyPdfiumBackend),
        )
        # One fresh mock set for both builds: instance-valued kwargs are the
        # mock's shared return_value, so recorded kwargs compare by identity.
        mocks = _fresh_option_mocks(monkeypatch)

        def _build(backend: str) -> None:
            _stub_pdf_cfg(monkeypatch, _pdf_cfg(pdf_backend=backend))
            docling_factory._build_pdf_format_option(
                do_ocr=True, do_table_structure=False
            )

        _build("pypdfium")
        _build("docling-parse")

        pipe_calls = mocks["PdfPipelineOptions"].call_args_list
        assert len(pipe_calls) == 2
        assert pipe_calls[0].kwargs == pipe_calls[1].kwargs
        assert pipe_calls[0].kwargs["queue_max_size"] == 16

        format_calls = mocks["PdfFormatOption"].call_args_list
        assert len(format_calls) == 2
        pypdfium_kwargs = dict(format_calls[0].kwargs)
        docling_parse_kwargs = dict(format_calls[1].kwargs)
        assert pypdfium_kwargs.pop("backend") is _FakePyPdfiumBackend
        assert "backend" not in docling_parse_kwargs
        assert pypdfium_kwargs == docling_parse_kwargs


class TestSyclJitCacheEnv:
    """_persist_sycl_jit_cache_on_xpu sets both env vars only for XPU."""

    @pytest.mark.parametrize(
        ("resolved_device", "sets_env"),
        [("xpu", True), ("cpu", False), ("cuda:0", False), (None, False)],
    )
    def test_env_vars_set_only_for_xpu(
        self, clean_sycl_env: None, resolved_device: Any, sets_env: bool
    ) -> None:
        docling_factory._persist_sycl_jit_cache_on_xpu(resolved_device)

        if sets_env:
            assert os.environ["SYCL_CACHE_PERSISTENT"] == "1"
            assert os.environ["SYCL_CACHE_DIR"] == str(
                docling_factory._CACHE_ROOT / "sycl-jit-cache"
            )
        else:
            assert "SYCL_CACHE_PERSISTENT" not in os.environ
            assert "SYCL_CACHE_DIR" not in os.environ

    def test_setdefault_preserves_user_override(self, clean_sycl_env: None) -> None:
        """A user's explicit SYCL_CACHE_* values win over the defaults."""
        os.environ["SYCL_CACHE_PERSISTENT"] = "0"
        os.environ["SYCL_CACHE_DIR"] = "/custom/jit-cache"

        docling_factory._persist_sycl_jit_cache_on_xpu("xpu")

        assert os.environ["SYCL_CACHE_PERSISTENT"] == "0"
        assert os.environ["SYCL_CACHE_DIR"] == "/custom/jit-cache"


class TestLowXpuHeadroomWarning:
    """_warn_on_low_xpu_headroom warns below the threshold, silently otherwise."""

    def _stub_config_threshold(self, monkeypatch: pytest.MonkeyPatch, mib: int) -> None:
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(accelerator_min_free_ram_mib=mib))

    def test_warns_when_xpu_free_ram_below_threshold(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: 512)
        self._stub_config_threshold(monkeypatch, 2048)

        with caplog.at_level("WARNING"):
            docling_factory._warn_on_low_xpu_headroom("xpu")

        warnings = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "'xpu'" in message
        assert "512 MiB" in message
        assert "2048 MiB" in message
        assert "SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu" in message

    def test_silent_when_free_ram_meets_threshold(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: 4096)
        self._stub_config_threshold(monkeypatch, 2048)

        with caplog.at_level("WARNING"):
            docling_factory._warn_on_low_xpu_headroom("xpu")

        assert not caplog.records

    def test_silent_for_non_xpu_device(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: 512)
        self._stub_config_threshold(monkeypatch, 2048)

        with caplog.at_level("WARNING"):
            docling_factory._warn_on_low_xpu_headroom("cpu")

        assert not caplog.records

    def test_silent_when_measurement_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No /proc/meminfo-equivalent (None): skip the warning, never raise."""
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: None)
        self._stub_config_threshold(monkeypatch, 2048)

        with caplog.at_level("WARNING"):
            docling_factory._warn_on_low_xpu_headroom("xpu")

        assert not caplog.records

    def test_never_raises_when_config_or_threshold_vary(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Threshold 0 disables the warning entirely (free >= 0 always)."""
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: 0)
        self._stub_config_threshold(monkeypatch, 0)

        with caplog.at_level("WARNING"):
            docling_factory._warn_on_low_xpu_headroom("xpu")

        assert not caplog.records


class TestPreflightAcceleratorDevice:
    """_preflight_accelerator_device resolves, warns, and fails fast."""

    def test_returns_resolved_device_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(
            sys.modules,
            "docling.utils.accelerator_utils",
            SimpleNamespace(decide_device=lambda name: "xpu"),
        )
        # High headroom so the (xpu) headroom check stays silent.
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: 8192)

        resolved = docling_factory._preflight_accelerator_device("auto")

        assert resolved == "xpu"

    def test_resolved_cpu_does_not_trigger_headroom_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setitem(
            sys.modules,
            "docling.utils.accelerator_utils",
            SimpleNamespace(decide_device=lambda name: "cpu"),
        )
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: 128)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(accelerator_min_free_ram_mib=2048))

        with caplog.at_level("WARNING"):
            resolved = docling_factory._preflight_accelerator_device("cpu")

        assert resolved == "cpu"
        assert not caplog.records

    def test_returns_none_when_docling_resolver_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No docling accelerator_utils (e.g. under test stubs): None, no raise."""
        monkeypatch.setitem(sys.modules, "docling.utils.accelerator_utils", None)

        assert docling_factory._preflight_accelerator_device("auto") is None

    def test_unavailable_pin_raises_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_name: str) -> str:
            raise RuntimeError("no xpu build")

        monkeypatch.setitem(
            sys.modules,
            "docling.utils.accelerator_utils",
            SimpleNamespace(decide_device=_boom),
        )

        with pytest.raises(
            docling_factory.AcceleratorDeviceUnavailableError,
            match="SECONDBRAIN_PDF_ACCELERATOR_DEVICE='cuda'",
        ):
            docling_factory._preflight_accelerator_device("cuda")

    def test_warns_on_low_headroom_for_resolved_xpu(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Resolution to xpu + low free RAM emits the preflight warning."""
        monkeypatch.setitem(
            sys.modules,
            "docling.utils.accelerator_utils",
            SimpleNamespace(decide_device=lambda name: "xpu"),
        )
        monkeypatch.setattr(docling_factory, "_available_ram_mib", lambda: 512)
        _stub_pdf_cfg(monkeypatch, _pdf_cfg(accelerator_min_free_ram_mib=2048))

        with caplog.at_level("WARNING"):
            resolved = docling_factory._preflight_accelerator_device("auto")

        assert resolved == "xpu"
        assert any(
            "SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu" in r.message
            for r in caplog.records
        )
