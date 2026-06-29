"""Configuration and fixtures for example script tests."""

from __future__ import annotations

import os
import runpy
import sys
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from secondbrain.config import Config


@lru_cache(maxsize=1)
def _get_cached_env() -> dict[str, str]:
    """Test-safe env: values derived from Config (uses .env.test when PYTEST_CURRENT_TEST is set)."""
    env: dict[str, str] = {}
    test_config = Config()
    for key in dir(test_config):
        if key.isupper() and not key.startswith("_"):
            val = getattr(test_config, key, None)
            if val is not None and not callable(val):
                env[f"SECONDBRAIN_{key}"] = str(val)

    env["SECONDBRAIN_VERBOSE"] = "0"
    env.setdefault("SECONDBRAIN_STREAMING_ENABLED", "false")

    return env


@pytest.fixture
def example_runner(tmp_path: Path) -> Any:
    """Fixture to run example scripts in-process via runpy.

    Runs script main() directly in the current Python process instead of
    spawning a subprocess, eliminating interpreter startup and module reload
    overhead. Stdout/stderr are captured by redirecting print/rich streams.

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
        """Run an example script in-process and return results.

        Args:
            script_path: Path to the example script
            args: Command-line arguments to inject via sys.argv
            timeout: Maximum execution time (currently unused, in-process is fast)
            env_overrides: Environment variable overrides

        Returns:
            Dictionary with keys:
            - returncode: Exit code (0 for success, 1 for SystemExit)
            - stdout: Captured stdout
            - stderr: Captured stderr
            - success: Boolean indicating success
            - command: String showing what was run
        """
        # Preserve original state
        orig_argv = sys.argv.copy()
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr

        # Set up fake argv for argparser
        sys.argv = [str(script_path)] + (args or [])

        # Capture stdout/stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        # Also capture rich console output by swapping stdout at file-object level
        rich_console_outputs: list[StringIO] = []

        # Monkeypatch Rich's Console._file_wrapper to capture rich console prints
        # We'll just rely on sys.stdout redirection since rich writes to whatever stdout points to

        returncode = 0
        error_msg = None

        from secondbrain.config import get_config

        # Preserve original environ and inject test-safe environment to prevent
        # production .env bleed-through when example scripts call VectorStorage().
        # Also clear the config cache so a fresh Config reads our test env vars.
        orig_environ = os.environ.copy()
        get_config.cache_clear()
        os.environ.update(_get_cached_env())

        try:
            # Apply additional env overrides on top of test-safe defaults
            if env_overrides:
                for k, v in env_overrides.items():
                    os.environ[k] = v

            sys.stdout = stdout_capture
            sys.stderr = stderr_capture

            try:
                runpy.run_path(str(script_path), run_name="__main__")
            except SystemExit as e:
                returncode = (
                    e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
                )
            except Exception as e:
                returncode = 1
                error_msg = repr(e)

        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            sys.argv = orig_argv

            # Fully restore original environ (not just env_overrides keys)
            os.environ.clear()
            os.environ.update(orig_environ)

        stdout = stdout_capture.getvalue()
        stderr = stderr_capture.getvalue()

        # Append error to stderr if we caught an exception
        if error_msg:
            stderr += f"\n{error_msg}"

        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "success": returncode == 0,
            "command": f"runpy.run_path({script_path}, args={args})",
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


@pytest.fixture
def fast_test_config() -> dict:
    """Configuration for fast tests that don't need real services.

    Returns a config dict with test-friendly settings.
    """
    return {
        "skip_real_services": True,
        "mock_mode": True,
    }
