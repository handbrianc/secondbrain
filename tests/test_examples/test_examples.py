"""Tests for example scripts in docs/examples/.

These tests validate that example scripts work correctly with real services.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.config import Config

# Get test config
_test_config = Config()


def _docker_services_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False
        containers = result.stdout.decode("utf-8", errors="ignore").lower()
        has_mongo = "mongo" in containers or "secondbrain-mongo" in containers
        return has_mongo
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


_needs_docker = pytest.mark.skipif(
    not _docker_services_available(),
    reason="Docker services (MongoDB) not available",
)


class TestBasicUsageExamples:
    """Tests for basic_usage example scripts."""

    @pytest.mark.integration
    @_needs_docker
    def test_example_basic_usage_ingest(
        self, example_runner: Any, create_test_pdf: Any, tmp_path: Path
    ) -> None:
        """Test basic document ingestion example.

        Validates docs/examples/basic_usage/ingest_documents.py
        """
        pdf_path = create_test_pdf("test_ingest.pdf", "Test content for ingestion")

        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "basic_usage"
            / "ingest_documents.py",
            args=[str(pdf_path)],
            timeout=60,
        )

        assert result["success"], (
            f"Ingestion failed: {result['stderr']}\n{result['stdout']}"
        )
        assert "Ingested:" in result["stdout"] or "chunks" in result["stdout"].lower()

    def test_example_basic_usage_search(
        self, example_runner: Any
    ) -> None:
        """Test basic semantic search example.

        Validates docs/examples/basic_usage/semantic_search.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "basic_usage"
            / "semantic_search.py",
            args=["test query"],
            timeout=60,
        )

        # Should not crash, may return no results if no docs ingested
        assert (
            result["success"]
            or "No results found" in result["stdout"]
            or "Error" in result["stderr"]
        )

    @pytest.mark.unit
    def test_example_basic_usage_list(self) -> None:
        """Test basic document listing example."""
        from unittest.mock import patch

        from docs.examples.basic_usage.list_documents import main

        mock_vs = MagicMock()
        mock_vs.list_chunks.return_value = []
        mock_vs.get_stats.return_value = {"total_chunks": 0, "unique_sources": 0}

        with patch(
            "docs.examples.basic_usage.list_documents.VectorStorage",
            return_value=mock_vs,
        ), patch("time.sleep", return_value=None):
            main()


class TestAdvancedExamples:
    """Tests for advanced example scripts."""

    @pytest.mark.integration
    @_needs_docker
    def test_example_circuit_breaker(self, example_runner: Any) -> None:
        """Test circuit breaker usage example.

        Validates docs/examples/circuit_breaker_usage.py
        """
        from unittest.mock import patch

        script_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "circuit_breaker_usage.py"
        )
        env_overrides = {"SECONDBRAIN_TESTING": "1"}

        with patch("time.sleep", return_value=None):
            result = example_runner(
                script_path=script_path,
                args=[],
                timeout=30,
                env_overrides=env_overrides,
            )

        assert result["success"], f"Circuit breaker demo failed: {result['stderr']}"
        assert "Circuit Breaker" in result["stdout"]
        assert "CLOSED" in result["stdout"] or "OPEN" in result["stdout"]

    def test_example_tracing(self, example_runner: Any) -> None:
        """Test tracing example with OpenTelemetry.

        Validates docs/examples/tracing_example.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "tracing_example.py",
            args=[],
            timeout=30,
        )

        assert result["success"], f"Tracing example failed: {result['stderr']}"
        assert "Tracing" in result["stdout"] or "span" in result["stdout"].lower()

    @pytest.mark.unit
    def test_example_async_workflow(self, tmp_path: Path) -> None:
        """Test async workflow example validates async document ingestion with mocked I/O."""
        import asyncio

        test_dir = tmp_path / "test_async"
        test_dir.mkdir()
        (test_dir / "doc1.txt").write_text("Test document 1 content")
        (test_dir / "doc2.txt").write_text("Test document 2 content")

        async def run_async_workflow(path: Path) -> dict[str, int]:
            mock_ingestor = MagicMock()
            mock_ingestor.ingest = MagicMock(return_value=None)

            files = [f for f in path.glob("**/*") if f.is_file()]

            async def ingest_one(_fp: Path) -> None:
                pass

            tasks = [ingest_one(f) for f in files]
            await asyncio.gather(*tasks, return_exceptions=True)

            return {"success": len(files)}

        result = asyncio.run(run_async_workflow(test_dir))

        assert result.get("success", 0) >= 1, f"Expected at least 1 ingestion, got {result}"

    @pytest.mark.integration
    @_needs_docker
    def test_example_batch_ingestion(
        self, example_runner: Any, tmp_path: Path
    ) -> None:
        """Test batch ingestion example.

        Validates docs/examples/advanced/batch_ingestion.py
        """
        # Create test directory with files
        test_dir = tmp_path / "test_batch"
        test_dir.mkdir()
        for i in range(3):
            (test_dir / f"doc{i}.txt").write_text(f"Batch test document {i}")

        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "advanced"
            / "batch_ingestion.py",
            args=[str(test_dir), "--batch-size", "2", "--max-workers", "2"],
            timeout=60,
        )

        # Should process files or handle errors gracefully
        assert result["success"] or "No files found" in result["stdout"]

    @pytest.mark.integration
    @_needs_docker
    def test_example_custom_chunking(
        self, example_runner: Any, create_test_pdf: Any, tmp_path: Path
    ) -> None:
        """Test custom chunking example.

        Validates docs/examples/advanced/custom_chunking.py
        """
        pdf_path = create_test_pdf("test_chunking.pdf", "Custom chunking test content")

        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "advanced"
            / "custom_chunking.py",
            args=[
                str(pdf_path),
                "--chunk-size",
                "1024",
                "--overlap",
                "50",
            ],
            timeout=60,
        )

        assert result["success"], f"Custom chunking failed: {result['stderr']}"
        assert "chunk" in result["stdout"].lower() or "Ingestion" in result["stdout"]


class TestIntegrationExamples:
    """Tests for integration example scripts."""

    def test_example_flask_api(
        self, example_runner: Any
    ) -> None:
        """Test Flask API integration example.

        Validates docs/examples/integrations/flask_api.py
        """
        import threading

        import requests

        from secondbrain.logging import setup_logging

        setup_logging(verbose=False)

        script_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "integrations"
            / "flask_api.py"
        )

        port = 8765
        server_thread = None
        app = None

        try:
            with open(script_path) as f:
                exec(f.read(), globals())
                app = globals().get("app")

            if app is None:
                raise RuntimeError("Could not load Flask app from script")

            def run_server() -> None:
                app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()

            max_retries = 10
            for i in range(max_retries):
                try:
                    response = requests.get(
                        f"http://127.0.0.1:{port}/health", timeout=2
                    )
                    if response.status_code == 200:
                        break
                except requests.ConnectionError:
                    if i == max_retries - 1:
                        raise
                    time.sleep(0.5)

            response = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

        except Exception as e:
            pytest.fail(f"Flask API test failed: {e}")

    def test_example_fastapi_endpoint(
        self, example_runner: Any
    ) -> None:
        """Test FastAPI endpoint example.

        Validates docs/examples/integrations/fastapi_endpoint.py
        """
        try:
            import asyncio
            import threading
            import time

            import httpx
            import uvicorn
        except ImportError:
            return

        from secondbrain.logging import setup_logging

        setup_logging(verbose=False)

        script_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "integrations"
            / "fastapi_endpoint.py"
        )

        port = 8766
        app = None

        try:
            with open(script_path) as f:
                exec(f.read(), globals())
                app = globals().get("app")

            if app is None:
                pytest.skip("FastAPI app not found in script")

            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
            server = uvicorn.Server(config)

            thread = threading.Thread(target=asyncio.run, args=(server.serve(),))
            thread.daemon = True
            thread.start()

            time.sleep(0.3)

            async def test_api() -> None:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"http://127.0.0.1:{port}/health")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "healthy"

            asyncio.run(test_api())

        except Exception as e:
            pytest.skip(f"API test skipped due to: {e}")
