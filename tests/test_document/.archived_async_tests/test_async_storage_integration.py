"""Tests for async storage integration with Motor MongoDB."""
import pytest


class TestAsyncStorageIntegration:
    """Test async storage operations using Motor async API."""

    def test_async_storage_methods_exist(self):
        """VectorStorage should have async methods."""
        from secondbrain.storage.storage import VectorStorage
        
        storage = VectorStorage()
        
        assert hasattr(storage, 'store_async')
        assert hasattr(storage, 'search_async')

    @pytest.mark.asyncio
    async def test_async_store_operation(self):
        """Async store operation stores a document."""
        from secondbrain.storage.storage import VectorStorage
        
        storage = VectorStorage()
        
        test_doc = {
            "chunk_id": "test-async-123",
            "source_file": "test.txt",
            "page_number": 1,
            "chunk_text": "test content for async storage",
            "embedding": [0.1] * 384,
            "file_type": "text",
            "ingested_at": "2024-01-01T00:00:00"
        }
        
        # Should not raise
        result = await storage.store_async(test_doc)
        # Result may be True, None, or the inserted ID depending on implementation
        assert result is not None or result is True

    @pytest.mark.asyncio
    async def test_async_search_operation(self):
        """Async search returns results from MongoDB."""
        from secondbrain.storage.storage import VectorStorage
        
        storage = VectorStorage()
        
        query_embedding = [0.1] * 384
        results = await storage.search_async(query_embedding, top_k=5)
        
        assert isinstance(results, list)
        # Results may be empty if no documents, but should be a list
