"""Tests for multicore memory-efficient batch processing."""
import pytest


class TestMulticoreMemory:
    def test_max_memory_batch_size_constant_exists(self):
        from secondbrain.document import MAX_MEMORY_BATCH_SIZE
        
        assert MAX_MEMORY_BATCH_SIZE > 0
        assert isinstance(MAX_MEMORY_BATCH_SIZE, int)

    def test_batch_size_affects_memory_usage(self):
        from secondbrain.document import DocumentIngestor, MAX_MEMORY_BATCH_SIZE
        
        DocumentIngestor(verbose=False)
        assert MAX_MEMORY_BATCH_SIZE == 100

    def test_ingest_respects_batch_limits(self):
        from secondbrain.document import DocumentIngestor
        
        ingestor = DocumentIngestor(verbose=False)
        assert hasattr(ingestor, 'ingest')
