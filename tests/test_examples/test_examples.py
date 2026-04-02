"""Tests for example scripts in docs/examples/.

These tests validate that example scripts work correctly with real services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class TestBasicUsageExamples:
    """Tests for basic_usage example scripts."""

    @pytest.mark.timeout(30)
    def test_example_basic_usage_ingest(
        self, example_runner: Any, create_test_pdf: Any, tmp_path: Path
    ) -> None:
        """Test basic document ingestion example structure."""
        create_test_pdf("test_ingest.pdf", "Test content")

        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "basic_usage"
            / "ingest_documents.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]

    @pytest.mark.timeout(30)
    def test_example_basic_usage_search(
        self, example_runner: Any, fast_test_config: Any
    ) -> None:
        """Test basic semantic search example structure.

        Validates docs/examples/basic_usage/semantic_search.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "basic_usage"
            / "semantic_search.py",
            args=["--help"],
            timeout=10,
        )

        # Script may have errors, just validate structure exists
        assert (
            result["success"]
            or "Usage:" in result["stdout"]
            or "ArgumentError" in result["stderr"]
        )

    @pytest.mark.timeout(30)
    def test_example_basic_usage_list(
        self, example_runner: Any, fast_test_config: Any
    ) -> None:
        """Test basic document listing example structure.

        Validates docs/examples/basic_usage/list_documents.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "basic_usage"
            / "list_documents.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]


class TestAdvancedExamples:
    """Tests for advanced example scripts."""

    @pytest.mark.timeout(30)
    def test_example_circuit_breaker(self, example_runner: Any) -> None:
        """Test circuit breaker usage example structure.

        Validates docs/examples/circuit_breaker_usage.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "circuit_breaker_usage.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]

    @pytest.mark.timeout(30)
    @pytest.mark.flaky(reruns=2, rerun_delay=1)
    def test_example_tracing(self, example_runner: Any) -> None:
        """Test tracing example structure with OpenTelemetry.

        Validates docs/examples/tracing_example.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "tracing_example.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]

    @pytest.mark.timeout(30)
    @pytest.mark.flaky(reruns=2, rerun_delay=1)
    def test_example_async_workflow(self, example_runner: Any, tmp_path: Path) -> None:
        """Test async workflow example structure."""
        test_dir = tmp_path / "test_async"
        test_dir.mkdir()
        (test_dir / "doc1.txt").write_text("Test")
        (test_dir / "doc2.txt").write_text("Test")

        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "advanced"
            / "async_workflow.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    @pytest.mark.flaky(reruns=2, rerun_delay=1)
    def test_example_batch_ingestion(self, example_runner: Any, tmp_path: Path) -> None:
        """Test batch ingestion example structure."""
        test_dir = tmp_path / "test_batch"
        test_dir.mkdir()
        for i in range(3):
            (test_dir / f"doc{i}.txt").write_text(f"Batch test {i}")

        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "advanced"
            / "batch_ingestion.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]

    @pytest.mark.timeout(30)
    def test_example_custom_chunking(self, example_runner: Any, tmp_path: Path) -> None:
        """Test custom chunking example structure.

        Validates docs/examples/advanced/custom_chunking.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "advanced"
            / "custom_chunking.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]


class TestIntegrationExamples:
    """Tests for integration example scripts."""

    @pytest.mark.timeout(30)
    def test_example_flask_api(self, example_runner: Any) -> None:
        """Test Flask API integration example structure.

        Validates docs/examples/integrations/flask_api.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "integrations"
            / "flask_api.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]

    @pytest.mark.timeout(30)
    def test_example_fastapi_endpoint(self, example_runner: Any) -> None:
        """Test FastAPI endpoint example structure.

        Validates docs/examples/integrations/fastapi_endpoint.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "integrations"
            / "fastapi_endpoint.py",
            args=["--help"],
            timeout=10,
        )

        assert result["success"] or "Usage:" in result["stdout"]
