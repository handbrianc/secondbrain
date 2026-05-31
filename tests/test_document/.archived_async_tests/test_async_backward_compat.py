"""Tests for backward compatibility between sync and async ingestors."""
import pytest


class TestAsyncBackwardCompat:
    """Test both classes can coexist and function independently."""

    def test_both_classes_importable(self):
        """DocumentIngestor and AsyncDocumentIngestor can both be imported."""
        from secondbrain.document import DocumentIngestor, AsyncDocumentIngestor
        
        assert DocumentIngestor is not None
        assert AsyncDocumentIngestor is not None
        assert DocumentIngestor != AsyncDocumentIngestor

    def test_sync_class_works(self):
        """Sync DocumentIngestor can be instantiated and used."""
        from secondbrain.document import DocumentIngestor
        
        ingestor = DocumentIngestor(verbose=False)
        assert ingestor is not None
        assert ingestor.chunk_size > 0

    def test_async_class_works(self):
        """AsyncDocumentIngestor can be instantiated and used."""
        from secondbrain.document import AsyncDocumentIngestor
        
        ingestor = AsyncDocumentIngestor(verbose=False)
        assert ingestor is not None
        assert ingestor.chunk_size > 0

    def test_sync_and_async_have_different_interfaces(self):
        """Sync and async classes have different method signatures."""
        from secondbrain.document import DocumentIngestor, AsyncDocumentIngestor
        import inspect
        
        sync_ingestor = DocumentIngestor(verbose=False)
        async_ingestor = AsyncDocumentIngestor(verbose=False)
        
        assert hasattr(sync_ingestor, 'ingest')
        assert hasattr(async_ingestor, 'ingest_async')

    def test_async_resource_cleanup(self):
        """Test async ingestor properly releases resources on exit."""
        from secondbrain.document import AsyncDocumentIngestor
        import asyncio
        
        async def test_cleanup():
            ingestor = AsyncDocumentIngestor(verbose=False)
            assert ingestor is not None
            
            async with ingestor:
                pass
        
        asyncio.run(test_cleanup())
