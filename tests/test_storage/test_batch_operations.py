# NOTE: Use the `storage_with_mock` fixture from conftest.py to avoid
# ~1s overhead per test. Example:
#     def test_something(self, storage_with_mock):
#         with patch.object(storage_with_mock, "_collection", mock_coll):
#             # test code
"""Tests for batch operations in storage module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestVectorStorageBatchOperations:
    """Tests for VectorStorage batch operations."""

    def test_store_batch_empty_list(self) -> None:
        """Test store_batch with empty document list."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.inserted_ids = []

            mock_collection = MagicMock()
            mock_collection.insert_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.store_batch([])
                assert result == 0
                mock_collection.insert_many.assert_called_once_with([])

    def test_store_batch_single_document(self) -> None:
        """Test store_batch with single document."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.inserted_ids = ["single_id"]

            mock_collection = MagicMock()
            mock_collection.insert_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                docs = [
                    {
                        "chunk_id": "chunk1",
                        "text": "test text",
                        "embedding": [0.1] * 384,
                        "metadata": {"source": "test.pdf"},
                    }
                ]
                result = storage.store_batch(docs)
                assert result == 1
                mock_collection.insert_many.assert_called_once()

    def test_store_batch_large_batch(self) -> None:
        """Test store_batch with 100+ documents."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Create 150 documents
            large_batch = [
                {
                    "chunk_id": f"chunk{i}",
                    "text": f"test text {i}",
                    "embedding": [0.1] * 384,
                    "metadata": {"source": f"file{i}.pdf"},
                }
                for i in range(150)
            ]

            mock_result = MagicMock()
            mock_result.inserted_ids = [f"id{i}" for i in range(150)]

            mock_collection = MagicMock()
            mock_collection.insert_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.store_batch(large_batch)
                assert result == 150
                mock_collection.insert_many.assert_called_once()

    def test_store_batch_timestamps_consistent(self) -> None:
        """Test that all documents in batch get the same timestamp."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Mock the insert_many to capture the documents
            captured_docs = []

            def capture_insert(docs):
                captured_docs.extend(docs)
                mock_result = MagicMock()
                mock_result.inserted_ids = [f"id{i}" for i in range(len(docs))]
                return mock_result

            mock_collection = MagicMock()
            mock_collection.insert_many.side_effect = capture_insert

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                docs = [
                    {
                        "chunk_id": "chunk1",
                        "text": "text1",
                        "embedding": [0.1],
                        "metadata": {"ingested_at": "old_time_1"},
                    },
                    {
                        "chunk_id": "chunk2",
                        "text": "text2",
                        "embedding": [0.2],
                        "metadata": {"ingested_at": "old_time_2"},
                    },
                ]
                _ = storage.store_batch(docs)

                # All documents should have the same timestamp
                assert len(captured_docs) == 2
                timestamps = [doc["metadata"]["ingested_at"] for doc in captured_docs]
                assert timestamps[0] == timestamps[1]
                # Timestamp should be ISO format
                assert "T" in timestamps[0]

    def test_store_batch_preserves_metadata(self) -> None:
        """Test that metadata is preserved during batch insert."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Mock the insert_many to capture the documents
            captured_docs = []

            def capture_insert(docs):
                captured_docs.extend(docs)
                mock_result = MagicMock()
                mock_result.inserted_ids = [f"id{i}" for i in range(len(docs))]
                return mock_result

            mock_collection = MagicMock()
            mock_collection.insert_many.side_effect = capture_insert

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                docs = [
                    {
                        "chunk_id": "chunk1",
                        "text": "text1",
                        "embedding": [0.1],
                        "metadata": {
                            "source": "test.pdf",
                            "page": 1,
                            "custom_field": "value1",
                        },
                    },
                    {
                        "chunk_id": "chunk2",
                        "text": "text2",
                        "embedding": [0.2],
                        "metadata": {
                            "source": "test2.pdf",
                            "page": 2,
                            "custom_field": "value2",
                        },
                    },
                ]
                _ = storage.store_batch(docs)

                # Verify metadata is preserved
                assert captured_docs[0]["metadata"]["source"] == "test.pdf"
                assert captured_docs[0]["metadata"]["page"] == 1
                assert captured_docs[0]["metadata"]["custom_field"] == "value1"
                assert captured_docs[1]["metadata"]["source"] == "test2.pdf"
                assert captured_docs[1]["metadata"]["page"] == 2
                assert captured_docs[1]["metadata"]["custom_field"] == "value2"

    def test_store_batch_connection_error(self) -> None:
        """Test store_batch raises error when connection is invalid."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection", return_value=False),
                pytest.raises(StorageConnectionError),
            ):
                storage.store_batch(
                    [
                        {
                            "chunk_id": "chunk1",
                            "text": "text1",
                            "embedding": [0.1],
                            "metadata": {},
                        }
                    ]
                )

    def test_store_batch_returns_correct_count(self) -> None:
        """Test that store_batch returns the correct count of inserted documents."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            for batch_size in [1, 5, 10, 50]:
                mock_result = MagicMock()
                mock_result.inserted_ids = [f"id{i}" for i in range(batch_size)]

                mock_collection = MagicMock()
                mock_collection.insert_many.return_value = mock_result

                with (
                    patch.object(storage, "validate_connection", return_value=True),
                    patch.object(storage, "_collection", mock_collection),
                ):
                    docs = [
                        {
                            "chunk_id": f"chunk{i}",
                            "text": f"text{i}",
                            "embedding": [0.1],
                            "metadata": {},
                        }
                        for i in range(batch_size)
                    ]
                    result = storage.store_batch(docs)
                    assert result == batch_size

    def test_store_batch_with_missing_metadata(self) -> None:
        """Test store_batch handles documents without metadata field."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Mock the insert_many to capture the documents
            captured_docs = []

            def capture_insert(docs):
                captured_docs.extend(docs)
                mock_result = MagicMock()
                mock_result.inserted_ids = [f"id{i}" for i in range(len(docs))]
                return mock_result

            mock_collection = MagicMock()
            mock_collection.insert_many.side_effect = capture_insert

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                docs = [
                    {
                        "chunk_id": "chunk1",
                        "text": "text1",
                        "embedding": [0.1],
                        # No metadata field
                    },
                    {
                        "chunk_id": "chunk2",
                        "text": "text2",
                        "embedding": [0.2],
                        "metadata": {},  # Empty metadata
                    },
                ]
                _ = storage.store_batch(docs)

                # Verify documents were processed
                assert len(captured_docs) == 2
                # Documents without metadata field won't have metadata added
                # Only documents with existing metadata get timestamp updated

    def test_store_batch_preserves_original_documents(self) -> None:
        """Test that original documents are not modified during batch insert."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Mock the insert_many to capture the documents
            captured_docs = []

            def capture_insert(docs):
                captured_docs.extend(docs)
                mock_result = MagicMock()
                mock_result.inserted_ids = [f"id{i}" for i in range(len(docs))]
                return mock_result

            mock_collection = MagicMock()
            mock_collection.insert_many.side_effect = capture_insert

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                original_doc = {
                    "chunk_id": "chunk1",
                    "text": "text1",
                    "embedding": [0.1],
                    "metadata": {"ingested_at": "original_time"},
                }
                import copy

                original_doc_copy = copy.deepcopy(original_doc)

                docs = [original_doc]
                _ = storage.store_batch(docs)

                # Verify key fields remain unchanged
                assert original_doc["chunk_id"] == original_doc_copy["chunk_id"]
                assert original_doc["text"] == original_doc_copy["text"]
                assert original_doc["embedding"] == original_doc_copy["embedding"]
                # Captured doc should have updated timestamp
                assert captured_docs[0]["metadata"]["ingested_at"] != "original_time"
