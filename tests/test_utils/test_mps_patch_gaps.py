"""Gap tests for the transformers MPS position-embedding patch module.

Targets the uncovered branches reported by coverage for
``secondbrain/utils/mps_patch.py``:

- ``_clear_lru_cache_on_static_method`` no-op paths (missing method, missing
  ``cache_clear``) and the actual cache-clearing path;
- ``patch_transformers_for_mps`` ImportError branches (torch absent via
  ``sys.modules["torch"] = None``, rt_detr_v2 module absent);
- the generic-Exception branch (attribute access on the target module
  explodes) which must log a warning, not raise;
- the success path installing the float32 implementation on the real
  ``transformers.models.rt_detr_v2`` module (torch and transformers are
  installed in this environment) and its numerical contract;
- idempotency via the module-level ``_patch_applied`` flag.

The real module patch is by design global and idempotent, and
``secondbrain.document.processor`` already applies it at import time, so
re-applying it here leaves the process in its normal post-import state.
"""

from __future__ import annotations

import functools
import logging
import sys
import types
from typing import Any

import pytest

import secondbrain.utils.mps_patch as mps_patch
from secondbrain.utils.mps_patch import (
    _clear_lru_cache_on_static_method,
    patch_transformers_for_mps,
)


class TestClearLruCacheHelper:
    """_clear_lru_cache_on_static_method edge branches."""

    def test_missing_method_is_noop(self) -> None:
        class _Holder:
            pass

        # Must not raise even though the method does not exist.
        _clear_lru_cache_on_static_method(_Holder, "_cached_nothing")

    def test_method_without_cache_clear_is_noop(self) -> None:
        class _Holder:
            @staticmethod
            def _cached_thing() -> int:
                return 1

        _clear_lru_cache_on_static_method(_Holder, "_cached_thing")

    def test_lru_cached_static_method_cleared(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class _Holder:
            @staticmethod
            @functools.lru_cache(maxsize=8)
            def _cached_thing(x: int) -> int:
                return x * 2

        _Holder._cached_thing(1)
        assert _Holder._cached_thing.cache_info().currsize == 1

        with caplog.at_level(logging.DEBUG, logger="secondbrain.utils.mps_patch"):
            _clear_lru_cache_on_static_method(_Holder, "_cached_thing")

        assert _Holder._cached_thing.cache_info().currsize == 0
        assert any(
            "Cleared LRU cache for _Holder._cached_thing" in r.message
            for r in caplog.records
        )


class TestPatchImportErrorBranches:
    """Torch-absent and rt_detr_v2-absent branches log debug, never raise."""

    def test_torch_absent_skips_patch(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(mps_patch, "_patch_applied", False)
        monkeypatch.setitem(sys.modules, "torch", None)  # import torch -> ImportError

        with caplog.at_level(logging.DEBUG, logger="secondbrain.utils.mps_patch"):
            patch_transformers_for_mps()

        assert any(
            "RT-DETR model not available, skipping patch" in r.message
            for r in caplog.records
        )
        assert mps_patch._patch_applied is True

    def test_rt_detr_module_absent_skips_patch(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(mps_patch, "_patch_applied", False)
        monkeypatch.setitem(
            sys.modules, "transformers.models.rt_detr_v2", None
        )  # from-import -> ImportError

        with caplog.at_level(logging.DEBUG, logger="secondbrain.utils.mps_patch"):
            patch_transformers_for_mps()

        assert any(
            "RT-DETR model not available, skipping patch" in r.message
            for r in caplog.records
        )


class TestPatchExceptionBranch:
    """Non-ImportError failures degrade to a warning log."""

    def test_attribute_exploding_module_logs_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(mps_patch, "_patch_applied", False)

        class _Exploding:
            def __getattr__(self, name: str) -> Any:
                raise RuntimeError("attribute access exploded")

        fake_parent = types.ModuleType("fake_rt_detr_v2_parent")
        fake_parent.modeling_rt_detr_v2 = _Exploding()  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "transformers.models.rt_detr_v2", fake_parent)

        with caplog.at_level(logging.WARNING, logger="secondbrain.utils.mps_patch"):
            patch_transformers_for_mps()

        assert any(
            "Failed to apply transformers float32 patch" in r.message
            and "attribute access exploded" in r.message
            for r in caplog.records
        )


class _RealModelingGuard:
    """Snapshot/restore the real modeling module around a test."""

    def __init__(self) -> None:
        from transformers.models.rt_detr_v2 import modeling_rt_detr_v2

        self.module = modeling_rt_detr_v2
        self._original = modeling_rt_detr_v2.build_2d_sinusoidal_position_embedding

    def restore(self) -> None:
        self.module.build_2d_sinusoidal_position_embedding = self._original


@pytest.fixture
def real_modeling() -> Any:
    guard = _RealModelingGuard()
    yield guard.module
    guard.restore()


class TestPatchSuccessPath:
    """Success path installs a float32 implementation with a numeric contract."""

    def test_patch_installs_function_with_contract(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        real_modeling: Any,
    ) -> None:
        import torch

        monkeypatch.setattr(mps_patch, "_patch_applied", False)

        with caplog.at_level(logging.INFO, logger="secondbrain.utils.mps_patch"):
            patch_transformers_for_mps()

        installed = real_modeling.build_2d_sinusoidal_position_embedding
        assert installed is not None

        # embed_dim must be divisible by 4
        with pytest.raises(ValueError, match="divisible by 4"):
            installed(height=2, width=3, embed_dim=6)

        out = installed(height=2, width=3, embed_dim=8)
        assert out.shape == (6, 8)
        assert out.dtype == torch.float32

        with_cls = installed(height=2, width=3, embed_dim=8, cls_token=True)
        assert with_cls.shape == (7, 8)
        assert torch.all(with_cls[0] == 0), "CLS row must be zeros"

        as_f64 = installed(height=2, width=3, embed_dim=8, dtype=torch.float64)
        assert as_f64.dtype == torch.float64

        assert any(
            "Applied float32 patch to transformers RT-DETR position embeddings"
            in r.message
            for r in caplog.records
        )

    def test_patch_is_idempotent_when_flag_already_set(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(mps_patch, "_patch_applied", True)

        with caplog.at_level(logging.INFO, logger="secondbrain.utils.mps_patch"):
            patch_transformers_for_mps()

        assert not [
            r for r in caplog.records if "Applied float32 patch" in r.message
        ], "second call must short-circuit"

    def test_patched_values_are_finite(
        self, monkeypatch: pytest.MonkeyPatch, real_modeling: Any
    ) -> None:
        import math

        import torch

        monkeypatch.setattr(mps_patch, "_patch_applied", False)
        patch_transformers_for_mps()

        installed = real_modeling.build_2d_sinusoidal_position_embedding
        out = installed(height=3, width=2, embed_dim=8)

        assert out.dtype == torch.float32
        assert torch.isfinite(out).all()
        assert all(math.isfinite(v) for v in out.flatten().tolist())
        assert float(out.abs().max()) <= 1.0
