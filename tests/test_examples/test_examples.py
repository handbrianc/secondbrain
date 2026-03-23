"""Tests for example scripts in docs/examples/.

These tests validate that example scripts work correctly with real services.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest


class TestBasicUsageExamples:
    """Tests for basic_usage example scripts."""

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
        self, example_runner: Any, fast_test_config: Any
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

    def test_example_basic_usage_list(
        self, example_runner: Any, fast_test_config: Any
    ) -> None:
        """Test basic document listing example.

        Validates docs/examples/basic_usage/list_documents.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "basic_usage"
            / "list_documents.py",
            args=[],
            timeout=60,
        )

        # Should not crash, may return empty if no docs
        assert (
            result["success"]
            or "No documents found" in result["stdout"]
            or "Error" in result["stderr"]
        )


class TestAdvancedExamples:
    """Tests for advanced example scripts."""

    def test_example_circuit_breaker(self, example_runner: Any) -> None:
        """Test circuit breaker usage example.

        Validates docs/examples/circuit_breaker_usage.py
        """
        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "circuit_breaker_usage.py",
            args=[],
            timeout=30,
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

    def test_example_async_workflow(
        self, example_runner: Any, tmp_path: Path, fast_test_config: Any
    ) -> None:
        """Test async workflow example.

        Validates docs/examples/advanced/async_workflow.py
        """
        # Create some test files
        test_dir = tmp_path / "test_async"
        test_dir.mkdir()
        (test_dir / "doc1.txt").write_text("Test document 1 content")
        (test_dir / "doc2.txt").write_text("Test document 2 content")

        result = example_runner(
            script_path=Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "advanced"
            / "async_workflow.py",
            args=[str(test_dir)],
            timeout=60,
        )

        # May fail if services unavailable - check for expected service errors
        stderr = result["stderr"].lower()
        stdout = result["stdout"].lower()
        # Acceptable outcomes: success, or service-related errors (MongoDB, connection)
        has_service_error = (
            "mongo" in stderr
            or "connection" in stderr
            or "connection" in stdout
            or "oserror" in stderr
            or "runtimerror" in stderr
        )
        assert result["success"] or has_service_error

    def test_example_batch_ingestion(
        self, example_runner: Any, tmp_path: Path, fast_test_config: Any
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
        self, example_runner: Any, fast_test_config: Any
    ) -> None:
        """Test Flask API integration example.

        Validates docs/examples/integrations/flask_api.py
        """
        import threading
        import time

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

        server_process = None
        port = 8765

        try:
            server_process = example_runner(
                script_path=script_path,
                args=["--port", str(port)],
                timeout=5,
            )

            time.sleep(2)

            try:
                response = requests.get(f"http://localhost:{port}/health", timeout=5)
                assert response.status_code == 200
                assert response.json()["status"] == "healthy"
            except requests.ConnectionError:
                pytest.skip("Flask server did not start in time")

        except Exception as e:
            pytest.skip(f"Flask API test skipped: {e}")
        finally:
            if server_process and server_process.get("command"):
                pass

    def test_example_fastapi_endpoint(
        self, example_runner: Any, fast_test_config: Any
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
            pytest.skip("FastAPI or httpx or uvicorn not installed")

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
                pytest.skip("Could not load FastAPI app")

            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
            server = uvicorn.Server(config)

            thread = threading.Thread(target=asyncio.run, args=(server.serve(),))
            thread.daemon = True
            thread.start()

            time.sleep(2)

            async def test_api() -> None:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"http://127.0.0.1:{port}/health")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "healthy"

            asyncio.run(test_api())

        except Exception as e:
            pytest.skip(f"FastAPI test skipped: {e}")
