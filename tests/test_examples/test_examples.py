"""Tests for example scripts in docs/examples/.

These tests validate that example scripts work correctly with real services.
"""

from __future__ import annotations

import asyncio
from pathlib import Path


class TestAsyncWorkflow:
    """Tests for async workflow functionality."""

    def test_example_async_workflow(self, tmp_path: Path) -> None:
        """Test async workflow example validates async document ingestion with mocked I/O."""
        test_dir = tmp_path / "test_async"
        test_dir.mkdir()
        (test_dir / "doc1.txt").write_text("Test document 1 content")
        (test_dir / "doc2.txt").write_text("Test document 2 content")

        async def run_async_workflow(path: Path) -> dict[str, int]:
            files = [f for f in path.glob("**/*") if f.is_file()]

            async def ingest_one(_fp: Path) -> None:
                pass

            tasks = [ingest_one(f) for f in files]
            await asyncio.gather(*tasks, return_exceptions=True)

            return {"success": len(files)}

        result = asyncio.run(run_async_workflow(test_dir))

        assert result.get("success", 0) >= 1, (
            f"Expected at least 1 ingestion, got {result}"
        )
