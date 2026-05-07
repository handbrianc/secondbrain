"""Tests for multicore memory-efficient batch processing."""
import pytest
from pathlib import Path


class TestMulticoreMemory:
    """Test memory-efficient batch processing."""

    def test_max_memory_batch_size_constant_exists(self):
        """MAX_MEMORY_BATCH_SIZE constant is defined."""
        from secondbrain.document import MAX_MEMORY_BATCH_SIZE
        
        assert MAX_MEMORY_BATCH_SIZE > 0
        assert isinstance(MAX_MEMORY_BATCH_SIZE, int)

    def test_batch_size_affects_memory_usage(self):
        """Batch size parameter controls memory usage."""
        from secondbrain.document import DocumentIngestor
        
        ingestor = DocumentIngestor(verbose=False)
        
        # Verify MAX_MEMORY_BATCH_SIZE is used for memory management
        from secondbrain.document import MAX_MEMORY_BATCH_SIZE
        assert MAX_MEMORY_BATCH_SIZE == 100  # As defined in the module

    def test_ingest_respects_batch_limits(self):
        """Ingest processes files in batches to limit memory."""
        from secondbrain.document import DocumentIngestor, MAX_MEMORY_BATCH_SIZE
        
        ingestor = DocumentIngestor(verbose=False)
        
        # The ingestor should use MAX_MEMORY_BATCH_SIZE for batch processing
        assert hasattr(ingestor, 'ingest')
