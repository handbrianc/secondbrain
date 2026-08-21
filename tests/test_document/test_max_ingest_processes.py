"""Tests for the ``max_ingest_processes`` AUTO-detect worker cap.

``_resolve_core_count`` resolves the process-pool worker count. When the caller
passes no explicit ``cores`` and no ``max_workers`` is configured, the count is
auto-detected from the CPU count and may be capped by ``max_ingest_processes``
(0 = unlimited). An explicit ``cores`` argument or a configured ``max_workers``
is NEVER capped.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from secondbrain.document.ingestor._sync import DocumentIngestor


def _ingestor_with_cpu(count: int | None) -> DocumentIngestor:
    """Build an ingestor whose CPU-count probe returns ``count``."""
    ingestor = DocumentIngestor()
    ingestor._cpu_count_fn = lambda: count
    return ingestor


def _resolve(
    ingestor: DocumentIngestor,
    *,
    cores: int | None,
    max_workers: int | None,
    max_ingest_processes: int,
) -> int:
    """Call ``_resolve_core_count`` with a stubbed config."""
    cfg = SimpleNamespace(
        max_workers=max_workers, max_ingest_processes=max_ingest_processes
    )
    with patch("secondbrain.document.ingestor._sync.config", return_value=cfg):
        return ingestor._resolve_core_count(cores)


def test_auto_detect_capped_by_max_ingest_processes() -> None:
    """8 detected cores + cap of 4 -> 4 workers."""
    ingestor = _ingestor_with_cpu(8)
    assert _resolve(ingestor, cores=None, max_workers=None, max_ingest_processes=4) == 4


def test_auto_detect_uncapped_when_zero() -> None:
    """max_ingest_processes=0 leaves the auto-detected count uncapped -> 8."""
    ingestor = _ingestor_with_cpu(8)
    assert _resolve(ingestor, cores=None, max_workers=None, max_ingest_processes=0) == 8


def test_explicit_cores_not_capped() -> None:
    """An explicit cores arg is never capped by max_ingest_processes."""
    ingestor = _ingestor_with_cpu(8)
    assert _resolve(ingestor, cores=8, max_workers=None, max_ingest_processes=4) == 8


def test_configured_max_workers_not_capped() -> None:
    """A configured max_workers is never capped by max_ingest_processes."""
    ingestor = _ingestor_with_cpu(8)
    assert _resolve(ingestor, cores=None, max_workers=8, max_ingest_processes=4) == 8


def test_auto_detect_falls_back_to_one_when_cpu_unknown() -> None:
    """A missing CPU count resolves to 1 and is unaffected by the cap."""
    ingestor = _ingestor_with_cpu(None)
    assert _resolve(ingestor, cores=None, max_workers=None, max_ingest_processes=2) == 1


def test_explicit_cores_positive_validation_preserved() -> None:
    """The existing non-positive explicit-cores guard still holds."""
    ingestor = _ingestor_with_cpu(8)
    with patch(
        "secondbrain.document.ingestor._sync.config",
        return_value=SimpleNamespace(max_workers=None, max_ingest_processes=4),
    ):
        with pytest.raises(ValueError, match="cores must be positive"):
            ingestor._resolve_core_count(0)
