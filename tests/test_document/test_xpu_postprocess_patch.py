"""Tests for the XPU RT-DETR post-process patch in ``docling_factory``.

On torch 2.14 XPU builds for Xe2-class Intel GPUs, boolean-mask indexing
(``tensor[mask]``) inside transformers' ``RTDetrImageProcessor.post_process_
object_detection`` corrupts the output size (pytorch/pytorch#199157,
pytorch/pytorch#172934). ``_patch_rt_detr_postprocess_for_xpu`` reroutes that
stage to CPU whenever docling's layout model resolves to XPU.

The device gating is exercised with ``torch.xpu.is_available`` monkeypatched
so the suite passes on hosts with or without an Intel GPU; tensor routing is
unit-tested via a tiny ``Tensor`` subclass that reports an XPU device. The
original processor method is captured and restored around each test because
the patch mutates the class globally. A final integration test runs the real
docling converter on a real Intel GPU when one is present (skipped
elsewhere).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
import torch

import secondbrain.document.docling_factory as docling_factory
from secondbrain.document.docling_factory import (
    _move_detection_outputs_to_cpu,
    _patch_rt_detr_postprocess_for_xpu,
    _xpu_postprocess_needed,
)

_PROC_PATH = "transformers.models.rt_detr.image_processing_rt_detr"


class FakeXpuTensor(torch.Tensor):
    """CPU tensor that reports itself as XPU and records ``to()`` targets."""

    moved_to: ClassVar[list[str]] = []

    @property
    def device(self) -> torch.device:  # type: ignore[override]
        return torch.device("xpu")

    def to(self, *args: Any, **kwargs: Any) -> torch.Tensor:
        FakeXpuTensor.moved_to.append(str(args[0] if args else kwargs.get("device")))
        plain = self.clone().as_subclass(torch.Tensor)
        return plain


def _fake_xpu(values: list[list[float]]) -> FakeXpuTensor:
    t = torch.tensor(values)
    return t.as_subclass(FakeXpuTensor)


@pytest.fixture(autouse=True)
def _restore_processor_method(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Reset the patch flag and restore the original class method per test."""
    from secondbrain.config import get_config

    get_config.cache_clear()
    monkeypatch.setattr(docling_factory, "_xpu_postprocess_patched", False)
    processor_module = pytest.importorskip(_PROC_PATH, reason="transformers missing")
    processor_class = processor_module.RTDetrImageProcessor
    monkeypatch.setattr(
        processor_class,
        "post_process_object_detection",
        processor_class.post_process_object_detection,
    )
    FakeXpuTensor.moved_to = []
    yield
    get_config.cache_clear()


def _set_device_env(monkeypatch: pytest.MonkeyPatch, device: str) -> None:
    monkeypatch.setenv("SECONDBRAIN_PDF_ACCELERATOR_DEVICE", device)
    from secondbrain.config import get_config

    get_config.cache_clear()


def _set_xpu_available(monkeypatch: pytest.MonkeyPatch, available: bool) -> None:
    monkeypatch.setattr(torch.xpu, "is_available", lambda: available)


class TestXpuPostprocessNeeded:
    """Device-resolution gate for the patch."""

    def test_true_when_pinned_xpu_and_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_device_env(monkeypatch, "xpu")
        _set_xpu_available(monkeypatch, True)
        assert _xpu_postprocess_needed() is True

    def test_true_when_auto_resolves_to_xpu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_device_env(monkeypatch, "auto")
        _set_xpu_available(monkeypatch, True)
        assert _xpu_postprocess_needed() is True

    def test_false_when_pinned_cpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_device_env(monkeypatch, "cpu")
        _set_xpu_available(monkeypatch, True)
        assert _xpu_postprocess_needed() is False

    def test_false_when_xpu_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_device_env(monkeypatch, "xpu")
        _set_xpu_available(monkeypatch, False)
        assert _xpu_postprocess_needed() is False

    def test_false_when_torch_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_device_env(monkeypatch, "xpu")
        monkeypatch.setitem(sys.modules, "torch", None)
        assert _xpu_postprocess_needed() is False


class TestMoveDetectionOutputsToCpu:
    """Tensor-routing helper behavior."""

    def test_moves_xpu_logits_boxes_and_targets(self) -> None:
        outputs = {
            "logits": _fake_xpu([[0.1, 0.2]]),
            "pred_boxes": _fake_xpu([[0.5, 0.5, 0.5, 0.5]]),
            "extra": "untouched",
        }
        targets = _fake_xpu([[1754.0, 1240.0]])
        out, ts = _move_detection_outputs_to_cpu(outputs, targets)
        assert out["extra"] == "untouched"
        assert isinstance(out["logits"], torch.Tensor)
        assert out["logits"].device.type == "cpu"
        assert out["pred_boxes"].device.type == "cpu"
        assert ts is not None and ts.device.type == "cpu"
        assert FakeXpuTensor.moved_to == ["cpu", "cpu", "cpu"]

    def test_passes_through_non_xpu_outputs(self) -> None:
        logits = torch.randn(1, 300, 17)
        boxes = torch.randn(1, 300, 4)
        outputs = {"logits": logits, "pred_boxes": boxes}
        targets = torch.tensor([[100.0, 200.0]])
        out, ts = _move_detection_outputs_to_cpu(outputs, targets)
        assert out["logits"] is logits
        assert out["pred_boxes"] is boxes
        assert ts is targets
        assert FakeXpuTensor.moved_to == []

    def test_passes_through_non_dict_outputs(self) -> None:
        outputs = object()
        targets = None
        out, ts = _move_detection_outputs_to_cpu(outputs, targets)
        assert out is outputs
        assert ts is targets

    def test_passes_through_when_boxes_missing(self) -> None:
        logits = _fake_xpu([[0.1]])
        outputs: dict[str, Any] = {"logits": logits}
        out, ts = _move_detection_outputs_to_cpu(outputs, None)
        assert out["logits"] is logits  # not moved: missing pred_boxes
        assert ts is None
        assert FakeXpuTensor.moved_to == []


class TestPatchInstall:
    """Install gating and wrapper wiring."""

    def test_installs_wrapper_and_moves_xpu_tensors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from transformers.models.rt_detr.image_processing_rt_detr import (
            RTDetrImageProcessor,
        )

        _set_device_env(monkeypatch, "xpu")
        _set_xpu_available(monkeypatch, True)

        captured: dict[str, Any] = {}

        def sentinel(self: Any, outputs: Any, **kwargs: Any) -> list[dict[str, Any]]:
            captured["logits_device"] = outputs["logits"].device.type
            captured["boxes_device"] = outputs["pred_boxes"].device.type
            captured["target_device"] = (
                kwargs["target_sizes"].device.type
                if isinstance(kwargs["target_sizes"], torch.Tensor)
                else None
            )
            return [{"scores": torch.tensor([1.0])}]

        monkeypatch.setattr(
            RTDetrImageProcessor, "post_process_object_detection", sentinel
        )
        _patch_rt_detr_postprocess_for_xpu()

        wrapper = RTDetrImageProcessor.post_process_object_detection
        assert wrapper is not sentinel
        assert getattr(wrapper, "_secondbrain_xpu_cpu_postprocess", False) is True

        outputs = {
            "logits": _fake_xpu([[0.1] * 17]),
            "pred_boxes": _fake_xpu([[0.5, 0.5, 0.5, 0.5]]),
        }
        targets: Any = _fake_xpu([[1754.0, 1240.0]])
        result = wrapper(RTDetrImageProcessor(), outputs, target_sizes=targets)

        assert captured == {
            "logits_device": "cpu",
            "boxes_device": "cpu",
            "target_device": "cpu",
        }
        assert result == [{"scores": torch.tensor([1.0])}]

    def test_wrapper_passes_cpu_outputs_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from transformers.models.rt_detr.image_processing_rt_detr import (
            RTDetrImageProcessor,
        )

        _set_device_env(monkeypatch, "xpu")
        _set_xpu_available(monkeypatch, True)

        seen: dict[str, Any] = {}

        def sentinel(self: Any, outputs: Any, **kwargs: Any) -> list[dict[str, Any]]:
            seen["logits"] = outputs["logits"]
            return []

        monkeypatch.setattr(
            RTDetrImageProcessor, "post_process_object_detection", sentinel
        )
        _patch_rt_detr_postprocess_for_xpu()
        wrapper = RTDetrImageProcessor.post_process_object_detection

        logits = torch.randn(1, 300, 17)
        boxes = torch.randn(1, 300, 4)
        wrapper(RTDetrImageProcessor(), {"logits": logits, "pred_boxes": boxes})
        assert seen["logits"] is logits

    def test_skips_install_when_device_is_cpu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from transformers.models.rt_detr.image_processing_rt_detr import (
            RTDetrImageProcessor,
        )

        _set_device_env(monkeypatch, "cpu")
        _set_xpu_available(monkeypatch, True)
        before = RTDetrImageProcessor.post_process_object_detection
        _patch_rt_detr_postprocess_for_xpu()
        assert RTDetrImageProcessor.post_process_object_detection is before
        assert docling_factory._xpu_postprocess_patched is False

    def test_skips_install_when_xpu_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from transformers.models.rt_detr.image_processing_rt_detr import (
            RTDetrImageProcessor,
        )

        _set_device_env(monkeypatch, "xpu")
        _set_xpu_available(monkeypatch, False)
        before = RTDetrImageProcessor.post_process_object_detection
        _patch_rt_detr_postprocess_for_xpu()
        assert RTDetrImageProcessor.post_process_object_detection is before

    def test_skips_install_when_transformers_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_device_env(monkeypatch, "xpu")
        _set_xpu_available(monkeypatch, True)
        # from-import of a None module entry raises ImportError -> no-op.
        monkeypatch.setitem(sys.modules, _PROC_PATH, None)
        _patch_rt_detr_postprocess_for_xpu()
        assert docling_factory._xpu_postprocess_patched is False

    def test_idempotent_second_call_is_noop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from transformers.models.rt_detr.image_processing_rt_detr import (
            RTDetrImageProcessor,
        )

        _set_device_env(monkeypatch, "xpu")
        _set_xpu_available(monkeypatch, True)

        def sentinel(self: Any, outputs: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            RTDetrImageProcessor, "post_process_object_detection", sentinel
        )
        _patch_rt_detr_postprocess_for_xpu()
        wrapper = RTDetrImageProcessor.post_process_object_detection
        assert wrapper is not sentinel

        # A second install must not re-wrap (no double indirection).
        def boom() -> bool:
            raise AssertionError("device gate must not run again")

        monkeypatch.setattr(docling_factory, "_xpu_postprocess_needed", boom)
        _patch_rt_detr_postprocess_for_xpu()
        assert RTDetrImageProcessor.post_process_object_detection is wrapper


class TestXpuConverterIntegration:
    """End-to-end on a real Intel GPU; skipped on hosts without XPU.

    Marked ``integration`` so the fast suite (``pytest -m "not integration"``)
    skips the full model download + conversion. The session conftest stubs the
    docling modules for speed; this fixture swaps in the real modules for the
    duration of the test and restores the stubs afterward.
    """

    @pytest.fixture
    def _real_xpu_and_docling(self) -> Iterator[None]:
        if not (hasattr(torch, "xpu") and torch.xpu.is_available()):
            pytest.skip("No Intel XPU device available on this host")
        from secondbrain.config import get_config

        get_config.cache_clear()
        saved = {
            name: mod
            for name, mod in sys.modules.items()
            if name == "docling" or name.startswith("docling.")
        }
        for name in saved:
            sys.modules.pop(name)
        try:
            yield
        finally:
            for name in list(sys.modules):
                if name == "docling" or name.startswith("docling."):
                    sys.modules.pop(name)
            for name, mod in saved.items():
                sys.modules[name] = mod
            get_config.cache_clear()

    @pytest.mark.integration
    def test_docling_pdf_conversion_on_xpu(
        self, _real_xpu_and_docling: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full docling conversion must succeed with layout models on XPU.

        Regression: torch 2.14 XPU masked-select corruption crashed the
        layout stage before the post-process was moved to CPU.
        """
        from PIL import Image, ImageDraw, ImageFont

        try:
            font: Any = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26
            )
        except OSError:
            font = ImageFont.load_default(size=26)

        img = Image.new("RGB", (1240, 1754), "white")
        d = ImageDraw.Draw(img)
        d.text((100, 80), "Quarterly Infrastructure Report", font=font, fill="black")
        paragraph = (
            "Growth across all regions remained steady this quarter. "
            "Compute capacity expanded while latency stayed within "
            "budget. Storage utilization climbed modestly as ingestion "
            "volume increased through the period."
        )
        for i in range(4):
            d.text(
                (100, 200 + i * 44),
                paragraph[i * 42 : (i + 1) * 42],
                font=font,
                fill="black",
            )
        d.text(
            (100, 950),
            "Conclusions and next steps are summarized below.",
            font=font,
            fill="black",
        )
        pdf_path = "/tmp/opencode/xpu_docling_integration.pdf"
        img.save(pdf_path, "PDF", resolution=150)

        # Ensure the config singleton reflects the xpu pin for this process.
        monkeypatch.setenv("SECONDBRAIN_PDF_ACCELERATOR_DEVICE", "xpu")
        from secondbrain.config import get_config

        get_config.cache_clear()
        assert get_config().pdf_accelerator_device == "xpu"

        from secondbrain.document.docling_factory import _build_docling_converter

        converter = _build_docling_converter(do_ocr=True, do_table_structure=False)
        result = converter.convert(pdf_path)
        texts = [t.text for t in (result.document.texts or [])]
        joined = " ".join(texts).replace("\n", " ")
        # docling may merge the title into a neighboring segment without a
        # space ("...InfrastructureReport"), so assert on words, not phrases.
        assert "Quarterly" in joined
        assert "Infrastructure" in joined
        assert "Conclusions" in joined
        assert len(texts) >= 3
        assert torch.xpu.memory_allocated() > 0
