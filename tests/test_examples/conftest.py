"""Configuration and fixtures for example script tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def example_runner(tmp_path: Path) -> Generator[Any, None, None]:
    """Fixture to run example scripts with timeout and output capture.

    This fixture provides a runner function that:
    - Executes example scripts with a 30s timeout
    - Captures stdout/stderr
    - Loads environment from .env file
    - Validates exit codes and output patterns

    Args:
        tmp_path: Temporary directory for test files

    Yields:
        Runner function with signature:
        (script_path: Path, args: list[str], timeout: int) -> dict
    """

    def run_example(
        script_path: Path,
        args: list[str] | None = None,
        timeout: int = 30,
        env_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Run an example script and return results.

        Args:
            script_path: Path to the example script
            args: Additional command line arguments
            timeout: Maximum execution time in seconds
            env_overrides: Environment variable overrides

        Returns:
            Dictionary with keys:
            - returncode: Exit code
            - stdout: Captured stdout
            - stderr: Captured stderr
            - success: Boolean indicating success
            - output_patterns: Dict of pattern check results
        """
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        # Build environment
        env = os.environ.copy()

        # Load .env if exists
        env_file = Path(__file__).parent.parent.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env[key.strip()] = value.strip().strip('"')

        # Apply overrides
        if env_overrides:
            env.update(env_overrides)

        # Set test-specific defaults
        env.setdefault("SECONDBRAIN_VERBOSE", "0")

        # Run the script
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=tmp_path,
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
            "command": " ".join(cmd),
        }

    yield run_example


@pytest.fixture
def create_test_pdf(tmp_path: Path) -> Any:
    """Fixture to create a test PDF file.

    Yields:
        Path to created PDF file
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        def _create_pdf(
            filename: str = "test_doc.pdf", content: str | None = None
        ) -> Path:
            pdf_path = tmp_path / filename
            c = canvas.Canvas(str(pdf_path), pagesize=A4)
            _, height = A4

            c.setFont("Helvetica-Bold", 24)
            c.drawString(50 * mm, height - 30 * mm, "Test Document")

            c.setFont("Helvetica", 12)
            text_y = height - 50 * mm
            text = (
                content
                or "This is a test PDF document for validating the ingestion pipeline. "
                "It contains machine learning and artificial intelligence content. "
                "The document tests text extraction and chunking functionality."
            )
            c.drawString(50 * mm, text_y, text)
            c.save()
            return pdf_path

        yield _create_pdf
    except ImportError:
        pytest.skip("reportlab not installed")


@pytest.fixture
def temp_docs_dir(tmp_path: Path) -> Any:
    """Fixture to create a temporary directory with test documents.

    Yields:
        Function to create test documents in the temp directory
    """
    docs_dir = tmp_path / "test_docs"
    docs_dir.mkdir()

    def _add_doc(filename: str, content: str, ext: str = ".txt") -> Path:
        doc_path = docs_dir / f"{filename}{ext}"
        with open(doc_path, "w") as f:
            f.write(content)
        return doc_path

    yield _add_doc, docs_dir


@pytest.fixture
def example_scripts_path() -> Path:
    """Path to the example scripts directory."""
    return Path(__file__).parent.parent.parent / "docs" / "examples"
