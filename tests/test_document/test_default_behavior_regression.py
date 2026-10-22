"""Regression tests pinning the default ingest behavior surface.

Finding 6 of the 2026-10 async-ingestor audit: nothing pinned the defaults
that the skip-detection and result-shape work must not change. These tests
freeze the declared configuration defaults, the CLI option defaults, the
ingestor constructor and method signature defaults, the empty-directory
result shape for both the sync and the async ingest, and the default
core-count resolution — so a future change to any of them is a deliberate,
reviewed decision instead of a silent regression.

Defaults are pinned at their declaration sites (``Config.model_fields`` and
click parameter defaults) rather than by constructing ``Config()``, because
``Config`` reads ``.env.test`` under pytest and instances are therefore
environment-dependent, while the declared defaults are not.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import click
import pytest
from click.core import UNSET

from secondbrain.cli import ingest as ingest_cli
from secondbrain.config import Config
from secondbrain.document import DocumentIngestor
from secondbrain.document.ingestor import AsyncDocumentIngestor


class TestConfigDefaults:
    """Declared Config defaults the ingest path relies on."""

    @pytest.mark.parametrize(
        ("field_name", "expected"),
        [
            # Pool sizing / multicore ingestion defaults.
            ("max_workers", None),
            ("max_ingest_processes", 0),
            ("ingest_pool", "process"),
            ("pdf_ocr_enabled", False),
            # Re-ingest skip default (drives skip_existing resolution).
            ("skip_existing_on_reingest", True),
            # Chunking defaults.
            ("chunk_size", 4096),
            ("chunk_overlap", 50),
            ("streaming_enabled", True),
            ("streaming_chunk_batch_size", 150),
            # Embedding defaults (provider/model/dimensions/batching).
            ("embedding_provider", "openai"),
            ("embedding_model", "text-embedding-3-small"),
            ("embedding_api_key", None),
            ("embedding_api_base", None),
            ("embedding_dimensions", 1536),
            ("embedding_batch_size", 100),
            ("embedding_timeout", 300),
            ("default_top_k", 50),
        ],
    )
    def test_declared_default(self, field_name: str, expected: Any) -> None:
        field = Config.model_fields[field_name]
        assert field.default == expected


class TestCliDefaults:
    """The ingest CLI's option defaults match the documented behavior."""

    @staticmethod
    def _option(name: str) -> click.Option:
        for param in ingest_cli.ingest.params:
            if isinstance(param, click.Option) and param.name == name:
                return param
        raise AssertionError(f"option --{name.replace('_', '-')} not found")

    @pytest.mark.parametrize(
        ("option_name", "expected"),
        [
            ("batch_size", 30),
            ("cores", None),
            ("pool", None),
            ("no_skip_existing", False),
            ("chunk_size", None),
            ("chunk_overlap", None),
            ("recursive", False),
            ("verbose", False),
        ],
    )
    def test_option_default(
        self, option_name: str, expected: bool | int | None
    ) -> None:
        """Pin each option's effective default.

        click >= 8.3 stores a missing default as ``UNSET``; at parse time it
        resolves to ``None`` for value options and ``False`` for flags, which
        is the value the command callback receives.
        """
        option = self._option(option_name)
        default = option.default
        if default is UNSET:
            default = False if option.is_flag else None
        assert default == expected

    def test_batch_size_range_still_requires_positive(self) -> None:
        """The 30 default sits inside the validated IntRange(min=1)."""
        option = self._option("batch_size")
        assert option.type.min == 1

    def test_pool_choice_still_limited(self) -> None:
        """The None default means 'use config().ingest_pool', not 'anything'."""
        option = self._option("pool")
        assert tuple(option.type.choices) == ("process", "thread")


class TestIngestorDefaults:
    """Constructor and method signature defaults on both ingestors."""

    def test_constructor_defaults(self) -> None:
        ingestor = DocumentIngestor()
        assert ingestor.chunk_size == 4096
        assert ingestor.chunk_overlap == 50
        assert ingestor.verbose is False
        assert ingestor.progress_callback is None
        assert ingestor.on_chunk_progress is None
        assert ingestor.on_phase_progress is None

    def test_sync_ingest_signature_defaults(self) -> None:
        sig = inspect.signature(DocumentIngestor.ingest)
        assert sig.parameters["recursive"].default is False
        assert sig.parameters["batch_size"].default == 30
        assert sig.parameters["cores"].default is None
        assert sig.parameters["pool"].default is None
        assert sig.parameters["skip_existing"].default is None

    def test_async_ingest_signature_defaults(self) -> None:
        sig = inspect.signature(AsyncDocumentIngestor.ingest_async)
        assert sig.parameters["recursive"].default is False
        assert sig.parameters["batch_size"].default == 30
        assert sig.parameters["max_concurrent"].default == 5
        assert sig.parameters["skip_existing"].default is None


class TestEmptyIngestResultShape:
    """Empty-directory ingest returns the documented result key structure."""

    @staticmethod
    def _patch_factories(monkeypatch: pytest.MonkeyPatch) -> None:
        import secondbrain.embedding as emb_mod
        import secondbrain.storage as storage_mod

        monkeypatch.setattr(
            emb_mod.EmbeddingProviderFactory,
            "create_from_config",
            staticmethod(lambda cfg: MagicMock()),
        )
        monkeypatch.setattr(
            storage_mod.StorageFactory,
            "create_from_config",
            staticmethod(lambda cfg: MagicMock()),
        )

    def test_sync_ingest_empty_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_factories(monkeypatch)
        empty = tmp_path / "empty"
        empty.mkdir()

        result = DocumentIngestor().ingest(str(empty))

        assert result == {"success": 0, "failed": 0, "failures": [], "skipped": 0}

    @pytest.mark.asyncio
    async def test_async_ingest_empty_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_factories(monkeypatch)
        empty = tmp_path / "empty"
        empty.mkdir()

        result = await AsyncDocumentIngestor().ingest_async(str(empty))

        assert result == {"success": 0, "failed": 0, "failures": [], "skipped": 0}


class TestDefaultCoreResolution:
    """``_resolve_core_count(None)`` on the default config surface."""

    def test_resolves_to_cpu_count_when_unconfigured(self, monkeypatch) -> None:
        """max_workers None + max_ingest_processes 0 → raw CPU count."""
        ingestor = DocumentIngestor()
        monkeypatch.setattr(ingestor, "_cpu_count_fn", lambda: 7)
        cfg = SimpleNamespace(max_workers=None, max_ingest_processes=0)
        monkeypatch.setattr("secondbrain.document.ingestor._sync.config", lambda: cfg)

        assert ingestor._resolve_core_count(None) == 7

    def test_cpu_count_fallback_when_detection_fails(self, monkeypatch) -> None:
        """A CPU probe returning 0 still yields a positive worker count."""
        ingestor = DocumentIngestor()
        monkeypatch.setattr(ingestor, "_cpu_count_fn", lambda: 0)
        cfg = SimpleNamespace(max_workers=None, max_ingest_processes=0)
        monkeypatch.setattr("secondbrain.document.ingestor._sync.config", lambda: cfg)

        assert ingestor._resolve_core_count(None) == 1
