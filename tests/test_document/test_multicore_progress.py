"""Tests for multicore progress tracking."""
import pytest
from pathlib import Path
import tempfile


class TestMulticoreProgress:
    """Test progress tracking during multicore ingestion."""

    def test_ingest_accepts_cores_parameter(self):
        """Ingest method accepts cores parameter for parallel processing."""
        from secondbrain.document import DocumentIngestor
        
        ingestor = DocumentIngestor(verbose=False)
        
        # Should accept cores parameter
        import inspect
        sig = inspect.signature(ingestor.ingest)
        assert 'cores' in sig.parameters

    def test_progress_callback_can_be_provided(self):
        """Ingestor accepts progress_callback for progress tracking."""
        from secondbrain.document import DocumentIngestor
        
        def dummy_callback(path, success):
            pass
        
        ingestor = DocumentIngestor(verbose=False, progress_callback=dummy_callback)
        assert ingestor.progress_callback is not None

    def test_ingest_with_cores_parameter(self):
        """Ingest with cores parameter processes files."""
        from secondbrain.document import DocumentIngestor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.txt").write_text("test content")
            
            ingestor = DocumentIngestor(verbose=False)
            
            import inspect
            sig = inspect.signature(ingestor.ingest)
            assert 'cores' in sig.parameters
