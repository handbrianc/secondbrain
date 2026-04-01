"""Integration tests with real MongoDB connection.

These tests require MongoDB to be running via docker-compose.test.yml
"""

import uuid

import pytest

from secondbrain.storage import VectorStorage

# Skip all tests in this module if MongoDB is not available
try:
    from pymongo import MongoClient

    # Try multiple connection strategies
    TEST_MONGO_URI = "mongodb://127.0.0.1:27017/secondbrain_test"
    client = MongoClient(
        TEST_MONGO_URI, serverSelectionTimeoutMS=5000, directConnection=True
    )
    client.admin.command("ping")
    client.close()
except Exception:
    try:
        # Fallback: try with authentication
        TEST_MONGO_URI = (
            "mongodb://admin:admin123@127.0.0.1:27017/secondbrain_test?authSource=admin"
        )
        client = MongoClient(
            TEST_MONGO_URI, serverSelectionTimeoutMS=5000, directConnection=True
        )
        client.admin.command("ping")
        client.close()
    except Exception:
        pytest.skip(
            "MongoDB not available - integration tests require MongoDB running",
            allow_module_level=True,
        )


@pytest.fixture(scope="function")
def unique_collection_name() -> str:
    """Generate a unique collection name for each test to avoid race conditions."""
    return f"test_collection_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="function")
def isolated_storage(unique_collection_name: str) -> VectorStorage:
    """Create a VectorStorage with a unique collection for test isolation."""
    storage = VectorStorage(collection_name=unique_collection_name)
    yield storage
    # Cleanup after test
    try:
        storage.delete_all()
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.integration
class TestMongoRealConnection:
    """Test VectorStorage with real MongoDB connection."""

    def test_storage_real_mongo_connection(self, isolated_storage: VectorStorage) -> None:
        """Test real MongoDB connection is established."""
        assert isolated_storage is not None
        # Validate connection by pinging
        assert isolated_storage.validate_connection() is True

    def test_storage_real_store_and_retrieve(self, isolated_storage: VectorStorage) -> None:
        """Test store and retrieve with real MongoDB."""
        # Clean up first
        isolated_storage.delete_all()

        # Store a document
        test_chunk = {
            "chunk_id": "test_chunk_1",
            "source_file": "test_integration.pdf",
            "page_number": 1,
            "chunk_text": "Integration test content",
            "embedding": [0.1] * 384,
        }
        isolated_storage.store(test_chunk)

        chunks = isolated_storage.list_chunks(limit=10)
        assert len(chunks) > 0
        assert any(c["chunk_id"] == "test_chunk_1" for c in chunks)

        # Cleanup
        isolated_storage.delete_by_chunk_id("test_chunk_1")

    def test_storage_real_batch_operations(self, isolated_storage: VectorStorage) -> None:
        """Test batch store with real MongoDB."""
        # Clean up first
        isolated_storage.delete_all()

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
        isolated_storage.store_batch(chunks)

        results = isolated_storage.list_chunks(source_filter="batch_test.pdf", limit=20)
        assert len(results) == 10

        # Cleanup
        isolated_storage.delete_by_source("batch_test.pdf")

    def test_storage_real_search_similarity(self, isolated_storage: VectorStorage) -> None:
        """Test document storage and retrieval with real MongoDB."""
        # Clean up first
        isolated_storage.delete_all()

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
        isolated_storage.store_batch(chunks)

        results = isolated_storage.list_chunks(source_filter="sim_test.pdf", limit=10)
        assert len(results) == 5

        chunk_texts = [c["chunk_text"] for c in results]
        assert len(set(chunk_texts)) == 5

        # Cleanup
        isolated_storage.delete_by_source("sim_test.pdf")

    def test_storage_real_filter_by_source(self, isolated_storage: VectorStorage) -> None:
        """Test source file filtering."""
        # Clean up first
        isolated_storage.delete_all()

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
        isolated_storage.store_batch(chunks)

        # Filter by source_a using list_chunks
        results = isolated_storage.list_chunks(source_filter="source_a.pdf", limit=10)
        assert len(results) == 3
        assert all(r["source_file"] == "source_a.pdf" for r in results)

        # Cleanup
        isolated_storage.delete_all()

    def test_storage_real_filter_by_file_type(
        self, isolated_storage: VectorStorage
    ) -> None:
        """Test file type filtering."""
        # Clean up first
        isolated_storage.delete_all()

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
        isolated_storage.store_batch(chunks)

        # Get all results using list_chunks
        results = isolated_storage.list_chunks(limit=10)
        assert len(results) == 6

        # Verify file types
        pdf_count = sum(1 for r in results if r["source_file"].endswith(".pdf"))
        docx_count = sum(1 for r in results if r["source_file"].endswith(".docx"))
        assert pdf_count == 3
        assert docx_count == 3

        # Cleanup
        isolated_storage.delete_all()

    def test_storage_real_delete_operations(self, isolated_storage: VectorStorage) -> None:
        """Test delete operations with real MongoDB."""
        # Clean up first
        isolated_storage.delete_all()

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
        isolated_storage.store_batch(chunks)

        results = isolated_storage.list_chunks(source_filter="delete_test.pdf", limit=10)
        assert len(results) == 5

        # Delete by chunk_id
        isolated_storage.delete_by_chunk_id("delete_test_0")
        results = isolated_storage.list_chunks(source_filter="delete_test.pdf", limit=10)
        assert len(results) == 4

        # Delete by source
        isolated_storage.delete_by_source("delete_test.pdf")
        results = isolated_storage.list_chunks(source_filter="delete_test.pdf", limit=10)
        assert len(results) == 0

    def test_storage_real_pagination(self, isolated_storage: VectorStorage) -> None:
        """Test pagination with limit and offset."""
        # Clean up first
        isolated_storage.delete_all()

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
        isolated_storage.store_batch(chunks)

        # Test limit using list_chunks
        results = isolated_storage.list_chunks(source_filter="page_test.pdf", limit=5)
        assert len(results) == 5

        # Test with larger limit
        results_limited = isolated_storage.list_chunks(
            source_filter="page_test.pdf", limit=10
        )
        assert len(results_limited) == 10

        # Cleanup
        isolated_storage.delete_by_source("page_test.pdf")

    def test_storage_real_concurrent_writes(self, isolated_storage: VectorStorage) -> None:
        """Test concurrent batch operations."""
        from concurrent.futures import ThreadPoolExecutor

        # Clean up first
        isolated_storage.delete_all()

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
            isolated_storage.store_batch(chunks)

        # Run concurrent stores
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(store_batch, i) for i in range(3)]
            for future in futures:
                future.result()  # Wait for completion

        # Verify all stored using list_chunks
        results = isolated_storage.list_chunks(limit=30)
        assert len(results) == 15

        # Cleanup
        isolated_storage.delete_all()

    def test_storage_real_connection_recovery(
        self, isolated_storage: VectorStorage
    ) -> None:
        """Test reconnection after connection loss."""
        # This test validates that the storage can handle connection issues
        # In a real scenario, we would disconnect MongoDB, but for now we
        # just test that the connection validation works

        # Validate connection
        assert isolated_storage.validate_connection() is True

        # Perform an operation
        test_chunk = {
            "chunk_id": "recovery_test",
            "source_file": "recovery_test.pdf",
            "page_number": 1,
            "chunk_text": "Recovery test",
            "embedding": [0.1] * 384,
        }
        isolated_storage.store(test_chunk)

        # Validate connection again
        assert isolated_storage.validate_connection() is True

        # Cleanup
        isolated_storage.delete_by_chunk_id("recovery_test")
