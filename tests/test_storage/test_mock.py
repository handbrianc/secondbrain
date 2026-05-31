"""Tests for MockVectorStorage."""

import pytest

from secondbrain.storage.mock import MockVectorStorage


class TestMockVectorStorageInit:
    """Test MockVectorStorage initialization."""

    def test_init_creates_empty_storage(self):
        """Test that initialization creates empty storage."""
        storage = MockVectorStorage()

        # Internal state should be empty
        assert storage._chunks == {}
        assert storage._chunk_ids == []
        assert storage._initialized is False

    def test_init_no_parameters_required(self):
        """Test that initialization requires no parameters."""
        # Should not raise any errors
        storage = MockVectorStorage()
        assert storage is not None


class TestMockVectorStorageInitialize:
    """Test MockVectorStorage initialize method."""

    def test_initialize_sets_flag(self):
        """Test that initialize sets the initialized flag."""
        storage = MockVectorStorage()
        assert storage._initialized is False

        storage.initialize()
        assert storage._initialized is True

    def test_initialize_can_be_called_multiple_times(self):
        """Test that initialize can be called multiple times safely."""
        storage = MockVectorStorage()
        storage.initialize()
        storage.initialize()
        storage.initialize()

        assert storage._initialized is True


class TestMockVectorStorageEnsureIndex:
    """Test MockVectorStorage ensure_index method."""

    def test_ensure_index_is_noop(self):
        """Test that ensure_index is a no-op for mock."""
        storage = MockVectorStorage()

        # Should not raise any errors
        storage.ensure_index()
        storage.ensure_index()


class TestMockVectorStorageStore:
    """Test MockVectorStorage store method."""

    def test_store_single_chunk(self):
        """Test storing a single chunk."""
        storage = MockVectorStorage()
        chunk = {"chunk_id": "test-1", "text": "Test content"}

        storage.store(chunk)

        assert "test-1" in storage._chunks
        assert storage._chunks["test-1"] == chunk
        assert "test-1" in storage._chunk_ids

    def test_store_chunk_without_id_raises_error(self):
        """Test that storing chunk without ID raises ValueError."""
        storage = MockVectorStorage()
        chunk = {"text": "No ID chunk"}

        with pytest.raises(ValueError, match="chunk_id"):
            storage.store(chunk)

    def test_store_overwrites_existing_chunk(self):
        """Test that storing with same ID overwrites existing chunk."""
        storage = MockVectorStorage()
        chunk1 = {"chunk_id": "test-1", "text": "Original"}
        chunk2 = {"chunk_id": "test-1", "text": "Updated"}

        storage.store(chunk1)
        storage.store(chunk2)

        assert storage._chunks["test-1"] == chunk2
        assert len(storage._chunk_ids) == 1  # Still only one ID

    def test_store_preserves_all_chunk_data(self):
        """Test that store preserves all chunk data."""
        storage = MockVectorStorage()
        chunk = {
            "chunk_id": "test-1",
            "text": "Content",
            "metadata": {"source": "test.pdf", "page": 1},
            "embedding": [0.1, 0.2, 0.3]
        }

        storage.store(chunk)

        assert storage._chunks["test-1"]["metadata"]["source"] == "test.pdf"
        assert storage._chunks["test-1"]["embedding"] == [0.1, 0.2, 0.3]


class TestMockVectorStorageStoreBatch:
    """Test MockVectorStorage store_batch method."""

    def test_store_batch_multiple_chunks(self):
        """Test storing multiple chunks at once."""
        storage = MockVectorStorage()
        chunks = [
            {"chunk_id": "test-1", "text": "First"},
            {"chunk_id": "test-2", "text": "Second"},
            {"chunk_id": "test-3", "text": "Third"},
        ]

        storage.store_batch(chunks)

        assert len(storage._chunks) == 3
        assert len(storage._chunk_ids) == 3
        assert all(cid in storage._chunks for cid in ["test-1", "test-2", "test-3"])

    def test_store_batch_empty_list(self):
        """Test storing empty batch."""
        storage = MockVectorStorage()

        # Should not raise any errors
        storage.store_batch([])

        assert len(storage._chunks) == 0

    def test_store_batch_with_duplicate_ids(self):
        """Test storing batch with duplicate IDs."""
        storage = MockVectorStorage()
        chunks = [
            {"chunk_id": "test-1", "text": "First"},
            {"chunk_id": "test-1", "text": "Duplicate"},
        ]

        storage.store_batch(chunks)

        # Should have only one chunk (last one wins)
        assert len(storage._chunks) == 1
        assert storage._chunks["test-1"]["text"] == "Duplicate"

    def test_store_batch_partial_failures(self):
        """Test batch with some invalid chunks."""
        storage = MockVectorStorage()
        chunks = [
            {"chunk_id": "test-1", "text": "Valid"},
            {"text": "No ID"},  # Invalid
            {"chunk_id": "test-2", "text": "Valid"},
        ]

        with pytest.raises(ValueError, match="chunk_id"):
            storage.store_batch(chunks)

        # First chunk should be stored before failure
        assert "test-1" in storage._chunks


class TestMockVectorStorageSearch:
    """Test MockVectorStorage search method."""

    def test_search_empty_storage(self):
        """Test search on empty storage."""
        storage = MockVectorStorage()
        query_embedding = [0.1, 0.2, 0.3]

        results = storage.search(query_embedding, top_k=5)

        assert results == []

    def test_search_returns_top_k_results(self):
        """Test search returns correct number of results."""
        storage = MockVectorStorage()
        storage.store({"chunk_id": "1", "embedding": [1.0, 0.0, 0.0]})
        storage.store({"chunk_id": "2", "embedding": [0.0, 1.0, 0.0]})
        storage.store({"chunk_id": "3", "embedding": [0.0, 0.0, 1.0]})

        # Query similar to chunk 1
        query = [1.0, 0.1, 0.1]
        results = storage.search(query, top_k=2)

        assert len(results) == 2
        assert results[0]["chunk_id"] == "1"  # Most similar

    def test_search_respects_top_k_limit(self):
        """Test search respects top_k parameter."""
        storage = MockVectorStorage()
        for i in range(10):
            storage.store({"chunk_id": str(i), "embedding": [1.0, 0.0, 0.0]})

        results = storage.search([1.0, 0.0, 0.0], top_k=3)

        assert len(results) == 3

    def test_search_with_zero_top_k(self):
        """Test search with top_k=0."""
        storage = MockVectorStorage()
        storage.store({"chunk_id": "1", "embedding": [1.0, 0.0, 0.0]})

        results = storage.search([1.0, 0.0, 0.0], top_k=0)

        assert results == []

    def test_search_returns_results_with_scores(self):
        """Test search returns results with similarity scores."""
        storage = MockVectorStorage()
        storage.store({"chunk_id": "1", "embedding": [1.0, 0.0, 0.0]})

        results = storage.search([1.0, 0.0, 0.0], top_k=1)

        assert len(results) == 1
        assert "score" in results[0]
        assert results[0]["chunk_id"] == "1"

    def test_search_results_sorted_by_score(self):
        """Test search results are sorted by similarity score."""
        storage = MockVectorStorage()
        storage.store({"chunk_id": "1", "embedding": [1.0, 0.0, 0.0]})
        storage.store({"chunk_id": "2", "embedding": [0.5, 0.5, 0.0]})
        storage.store({"chunk_id": "3", "embedding": [0.0, 1.0, 0.0]})

        results = storage.search([1.0, 0.0, 0.0], top_k=3)

        # Should be sorted by similarity (chunk 1 > chunk 2 > chunk 3)
        assert results[0]["chunk_id"] == "1"
        assert results[1]["chunk_id"] == "2"
        assert results[2]["chunk_id"] == "3"
        assert results[0]["score"] >= results[1]["score"] >= results[2]["score"]


class TestMockVectorStorageCalculateCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Test similarity of identical vectors is 1.0."""
        storage = MockVectorStorage()

        similarity = storage._calculate_cosine_similarity(
            [1.0, 2.0, 3.0],
            [1.0, 2.0, 3.0]
        )

        assert abs(similarity - 1.0) < 0.0001

    def test_orthogonal_vectors(self):
        """Test similarity of orthogonal vectors is 0.0."""
        storage = MockVectorStorage()

        similarity = storage._calculate_cosine_similarity(
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0]
        )

        assert abs(similarity - 0.0) < 0.0001

    def test_opposite_vectors(self):
        """Test similarity of opposite vectors is -1.0."""
        storage = MockVectorStorage()

        similarity = storage._calculate_cosine_similarity(
            [1.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0]
        )

        assert abs(similarity - (-1.0)) < 0.0001

    def test_empty_vectors(self):
        """Test similarity with empty vectors returns 0.0."""
        storage = MockVectorStorage()

        assert storage._calculate_cosine_similarity([], []) == 0.0
        assert storage._calculate_cosine_similarity([1.0, 2.0], []) == 0.0
        assert storage._calculate_cosine_similarity([], [1.0, 2.0]) == 0.0

    def test_different_length_vectors(self):
        """Test handling of different length vectors."""
        storage = MockVectorStorage()

        similarity = storage._calculate_cosine_similarity(
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0]
        )

        # Should use min length (first 2 elements)
        assert -1.0 <= similarity <= 1.0

    def test_zero_magnitude_vector(self):
        """Test handling of zero magnitude vector."""
        storage = MockVectorStorage()

        similarity = storage._calculate_cosine_similarity(
            [0.0, 0.0, 0.0],
            [1.0, 2.0, 3.0]
        )

        assert similarity == 0.0


class TestMockVectorStorageGetAllChunks:
    """Test getAllChunks method."""

    def test_get_all_chunks_empty(self):
        """Test getting all chunks from empty storage."""
        storage = MockVectorStorage()

        chunks = storage.get_all_chunks()

        assert chunks == []

    def test_get_all_chunks_returns_all(self):
        """Test getting all chunks returns all stored chunks."""
        storage = MockVectorStorage()
        for i in range(10):
            storage.store({"chunk_id": str(i), "text": f"Chunk {i}"})

        chunks = storage.get_all_chunks()

        assert len(chunks) == 10

    def test_get_all_chunks_returns_references(self):
        """Test that get_all_chunks returns references to chunks."""
        storage = MockVectorStorage()
        chunk = {"chunk_id": "1", "text": "Original"}
        storage.store(chunk)

        chunks = storage.get_all_chunks()
        chunks[0]["text"] = "Modified"

        # Original is modified (returns references, not copies)
        assert storage._chunks["1"]["text"] == "Modified"


class TestMockVectorStorageDeleteAll:
    """Test delete_all method."""

    def test_delete_all_empty_storage(self):
        """Test deleting all from empty storage."""
        storage = MockVectorStorage()

        count = storage.delete_all()

        assert count == 0
        assert storage._chunks == {}
        assert storage._chunk_ids == []

    def test_delete_all_populated_storage(self):
        """Test deleting all from populated storage."""
        storage = MockVectorStorage()
        for i in range(10):
            storage.store({"chunk_id": str(i), "text": f"Chunk {i}"})

        count = storage.delete_all()

        assert count == 10
        assert storage._chunks == {}
        assert storage._chunk_ids == []

    def test_delete_all_returns_correct_count(self):
        """Test that delete_all returns the correct count."""
        storage = MockVectorStorage()
        for i in range(5):
            storage.store({"chunk_id": str(i), "text": f"Chunk {i}"})

        count = storage.delete_all()

        assert count == 5
