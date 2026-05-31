"""Tests for async ingestion method."""
import asyncio
import pytest
from pathlib import Path
import tempfile


class TestAsyncIngestMethod:
    """Test async ingestion method functionality."""

    def test_async_ingest_method_exists(self):
        """AsyncDocumentIngestor should have ingest_async method."""
        from secondbrain.document import AsyncDocumentIngestor
        
        ingestor = AsyncDocumentIngestor()
        
        assert hasattr(ingestor, 'ingest_async')
        assert callable(ingestor.ingest_async)

    @pytest.mark.asyncio
    async def test_async_ingest_processes_single_file(self):
        """Async ingest method processes a single file."""
        from secondbrain.document import AsyncDocumentIngestor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content for async ingest")
            
            ingestor = AsyncDocumentIngestor()
            
            # Should not raise
            result = await ingestor.ingest_async(str(test_file))
            assert result is not None

    @pytest.mark.asyncio
    async def test_async_ingest_concurrent_multiple_files(self):
        """Async ingest can process multiple files concurrently with asyncio.gather."""
        from secondbrain.document import AsyncDocumentIngestor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            for i in range(3):
                test_file = Path(tmpdir) / f"test_{i}.txt"
                test_file.write_text(f"test content {i}")
            
            ingestor = AsyncDocumentIngestor()
            
            # Process files concurrently using asyncio.gather
            files = [str(Path(tmpdir) / f"test_{i}.txt") for i in range(3)]
            results = await asyncio.gather(*[ingestor.ingest_async(f) for f in files])
            
            assert len(results) == 3
            assert all(r is not None for r in results)
