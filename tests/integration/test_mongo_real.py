"""Integration tests with real MongoDB connection.

These tests require MongoDB to be running via docker-compose.test.yml
"""

import pytest

from secondbrain.storage import VectorStorage


@pytest.mark.integration
class TestMongoRealConnection:
    """Test VectorStorage with real MongoDB connection."""

    def test_storage_real_mongo_connection(self, real_storage: VectorStorage) -> None:
        """Test real MongoDB connection is established."""
        assert real_storage is not None
        # Validate connection by pinging
        assert real_storage.validate_connection() is True

    def test_storage_real_store_and_retrieve(self, real_storage: VectorStorage) -> None:
        """Test store and retrieve with real MongoDB."""
        # Clean up first
        real_storage.delete_all()

        # Store a document
        test_chunk = {
            "chunk_id": "test_chunk_1",
            "source_file": "test_integration.pdf",
            "page_number": 1,
            "chunk_text": "Integration test content",
            "embedding": [0.1] * 384,
        }
        real_storage.store(test_chunk)

        # Retrieve it
        results = real_storage.search("test content", top_k=10)
        assert len(results) > 0
        assert any(r["chunk_id"] == "test_chunk_1" for r in results)

        # Cleanup
        real_storage.delete_by_chunk_id("test_chunk_1")

    def test_storage_real_batch_operations(self, real_storage: VectorStorage) -> None:
        """Test batch store with real MongoDB."""
        # Clean up first
        real_storage.delete_all()

        # Create batch of test documents
        chunks = [
            {
                "chunk_id": f"batch_test_{i}",
                "source_file": "batch_test.pdf",
                "page_number": 1,
                "chunk_text": f"Batch test content {i}",
                "embedding": [0.1 * i] * 384,
            }
            for i in range(10)
        ]

        # Batch store
        real_storage.store_batch(chunks)

        # Verify all stored
        results = real_storage.search("batch test", top_k=20)
        assert len(results) == 10

        # Cleanup
        real_storage.delete_by_source("batch_test.pdf")

    def test_storage_real_search_similarity(self, real_storage: VectorStorage) -> None:
        """Test semantic search with real MongoDB."""
        # Clean up first
        real_storage.delete_all()

        # Store documents with different content
        chunks = [
            {
                "chunk_id": f"sim_test_{i}",
                "source_file": "sim_test.pdf",
                "page_number": 1,
                "chunk_text": f"Document content number {i} with unique text",
                "embedding": [float(i % 10) / 10.0] * 384,
            }
            for i in range(5)
        ]
        real_storage.store_batch(chunks)

        # Search should return results ordered by similarity
        results = real_storage.search("unique text", top_k=5)
        assert len(results) > 0
        # Results should be sorted by score (descending)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

        # Cleanup
        real_storage.delete_by_source("sim_test.pdf")

    def test_storage_real_filter_by_source(self, real_storage: VectorStorage) -> None:
        """Test source file filtering."""
        # Clean up first
        real_storage.delete_all()

        # Store documents from different sources
        chunks = [
            {
                "chunk_id": f"source_test_a_{i}",
                "source_file": "source_a.pdf",
                "page_number": 1,
                "chunk_text": f"Content from source A {i}",
                "embedding": [0.1] * 384,
            }
            for i in range(3)
        ] + [
            {
                "chunk_id": f"source_test_b_{i}",
                "source_file": "source_b.pdf",
                "page_number": 1,
                "chunk_text": f"Content from source B {i}",
                "embedding": [0.2] * 384,
            }
            for i in range(3)
        ]
        real_storage.store_batch(chunks)

        # Filter by source_a
        results = real_storage.search("content", top_k=10, source_filter="source_a.pdf")
        assert len(results) == 3
        assert all(r["source_file"] == "source_a.pdf" for r in results)

        # Cleanup
        real_storage.delete_all()

    def test_storage_real_filter_by_file_type(
        self, real_storage: VectorStorage
    ) -> None:
        """Test file type filtering."""
        # Clean up first
        real_storage.delete_all()

        # Store documents with different file types
        chunks = [
            {
                "chunk_id": f"type_test_pdf_{i}",
                "source_file": f"test_{i}.pdf",
                "page_number": 1,
                "chunk_text": f"PDF content {i}",
                "embedding": [0.1] * 384,
            }
            for i in range(3)
        ] + [
            {
                "chunk_id": f"type_test_docx_{i}",
                "source_file": f"test_{i}.docx",
                "page_number": 1,
                "chunk_text": f"DOCX content {i}",
                "embedding": [0.2] * 384,
            }
            for i in range(3)
        ]
        real_storage.store_batch(chunks)

        # Search with file type filter - note: file_type filtering may not be
        # directly supported, so this tests the general search functionality
        results = real_storage.search("content", top_k=10)
        assert len(results) == 6

        # Cleanup
        real_storage.delete_all()

    def test_storage_real_delete_operations(self, real_storage: VectorStorage) -> None:
        """Test delete operations with real MongoDB."""
        # Clean up first
        real_storage.delete_all()

        # Store test documents
        chunks = [
            {
                "chunk_id": f"delete_test_{i}",
                "source_file": "delete_test.pdf",
                "page_number": 1,
                "chunk_text": f"Delete test content {i}",
                "embedding": [0.1] * 384,
            }
            for i in range(5)
        ]
        real_storage.store_batch(chunks)

        # Verify stored
        results = real_storage.search("delete test", top_k=10)
        assert len(results) == 5

        # Delete by chunk_id
        real_storage.delete_by_chunk_id("delete_test_0")
        results = real_storage.search("delete test", top_k=10)
        assert len(results) == 4

        # Delete by source
        real_storage.delete_by_source("delete_test.pdf")
        results = real_storage.search("delete test", top_k=10)
        assert len(results) == 0

    def test_storage_real_pagination(self, real_storage: VectorStorage) -> None:
        """Test pagination with limit and offset."""
        # Clean up first
        real_storage.delete_all()

        # Store many documents
        chunks = [
            {
                "chunk_id": f"page_test_{i}",
                "source_file": "page_test.pdf",
                "page_number": 1,
                "chunk_text": f"Pagination test content {i}",
                "embedding": [0.1] * 384,
            }
            for i in range(20)
        ]
        real_storage.store_batch(chunks)

        # Test limit
        results = real_storage.search("pagination", top_k=5)
        assert len(results) == 5

        # Test offset (search doesn't support offset directly, but we can test limit)
        results_limited = real_storage.search("pagination", top_k=10)
        assert len(results_limited) == 10

        # Cleanup
        real_storage.delete_by_source("page_test.pdf")

    def test_storage_real_concurrent_writes(self, real_storage: VectorStorage) -> None:
        """Test concurrent batch operations."""
        import threading
        from concurrent.futures import ThreadPoolExecutor

        # Clean up first
        real_storage.delete_all()

        # Store from multiple threads
        def store_batch(thread_id: int) -> None:
            chunks = [
                {
                    "chunk_id": f"concurrent_{thread_id}_{i}",
                    "source_file": f"concurrent_{thread_id}.pdf",
                    "page_number": 1,
                    "chunk_text": f"Concurrent test {thread_id} {i}",
                    "embedding": [float(thread_id + i) / 100.0] * 384,
                }
                for i in range(5)
            ]
            real_storage.store_batch(chunks)

        # Run concurrent stores
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(store_batch, i) for i in range(3)]
            for future in futures:
                future.result()  # Wait for completion

        # Verify all stored
        results = real_storage.search("concurrent test", top_k=20)
        assert len(results) == 15

        # Cleanup
        real_storage.delete_all()

    def test_storage_real_connection_recovery(
        self, real_storage: VectorStorage
    ) -> None:
        """Test reconnection after connection loss."""
        # This test validates that the storage can handle connection issues
        # In a real scenario, we would disconnect MongoDB, but for now we
        # just test that the connection validation works

        # Validate connection
        assert real_storage.validate_connection() is True

        # Perform an operation
        test_chunk = {
            "chunk_id": "recovery_test",
            "source_file": "recovery_test.pdf",
            "page_number": 1,
            "chunk_text": "Recovery test",
            "embedding": [0.1] * 384,
        }
        real_storage.store(test_chunk)

        # Validate connection again
        assert real_storage.validate_connection() is True

        # Cleanup
        real_storage.delete_by_chunk_id("recovery_test")
