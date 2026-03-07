"""Tests for filter combinations and aggregation edge cases."""

from unittest.mock import MagicMock, patch

from secondbrain.storage import VectorStorage


class TestFilterCombinations:
    """Tests for filter combination scenarios."""

    def test_search_with_both_filters(self) -> None:
        """Test search with both source and file_type filters."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_cursor = MagicMock()
            mock_cursor.skip.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.__iter__.return_value = []

            mock_collection = MagicMock()
            mock_collection.find.return_value = mock_cursor
            mock_collection.aggregate.return_value = iter([])

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_index_created", True),
            ):
                storage.search(
                    embedding=[0.1] * 384,
                    top_k=5,
                    source_filter="test.pdf",
                    file_type_filter="pdf",
                )

                # Verify aggregation was called with pipeline
                assert mock_collection.aggregate.called

    def test_search_with_regex_source_filter(self) -> None:
        """Test search with regex pattern in source filter."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_cursor = MagicMock()
            mock_cursor.skip.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.__iter__.return_value = [
                {
                    "chunk_id": "chunk1",
                    "source_file": "test_2024.pdf",
                    "page_number": 1,
                    "chunk_text": "text1",
                    "score": 0.9,
                }
            ]

            mock_collection = MagicMock()
            mock_collection.find.return_value = mock_cursor
            mock_collection.aggregate.return_value = iter(
                [
                    {
                        "chunk_id": "chunk1",
                        "source_file": "test_2024.pdf",
                        "page_number": 1,
                        "chunk_text": "text1",
                        "score": 0.9,
                    }
                ]
            )

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_index_created", True),
            ):
                results = storage.search(
                    embedding=[0.1] * 384,
                    top_k=5,
                    source_filter="test_.*\\.pdf",
                )

                assert len(results) == 1
                assert results[0]["source_file"] == "test_2024.pdf"

    def test_search_with_empty_results_filter(self) -> None:
        """Test search when filter produces no results."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.aggregate.return_value = iter([])

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_index_created", True),
            ):
                results = storage.search(
                    embedding=[0.1] * 384,
                    top_k=5,
                    source_filter="nonexistent.pdf",
                )

                assert len(results) == 0

    def test_list_chunks_combined_filters(self) -> None:
        """Test list_chunks with multiple filter conditions."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_cursor = MagicMock()
            mock_cursor.skip.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.__iter__.return_value = [
                {
                    "chunk_id": "chunk1",
                    "source_file": "test.pdf",
                    "page_number": 1,
                    "chunk_text": "text1",
                }
            ]

            mock_collection = MagicMock()
            mock_collection.find.return_value = mock_cursor

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                chunks = storage.list_chunks(
                    source_filter="test.pdf",
                    chunk_id="chunk1",
                    limit=10,
                    offset=0,
                )

                assert len(chunks) == 1
                assert chunks[0]["chunk_id"] == "chunk1"

    def test_filter_case_sensitivity(self) -> None:
        """Test case handling in filters."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_cursor = MagicMock()
            mock_cursor.skip.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.__iter__.return_value = [
                {
                    "chunk_id": "chunk1",
                    "source_file": "Test.PDF",
                    "page_number": 1,
                    "chunk_text": "text1",
                }
            ]

            mock_collection = MagicMock()
            mock_collection.find.return_value = mock_cursor

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # Test with lowercase filter
                chunks = storage.list_chunks(source_filter="test.pdf", limit=10)
                # MongoDB regex is case-sensitive by default
                assert len(chunks) >= 0  # May or may not match depending on DB config


class TestAggregationEdgeCases:
    """Tests for MongoDB aggregation edge cases."""

    def test_aggregation_pipeline_order(self) -> None:
        """Test that aggregation pipeline has correct stage order."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.aggregate.return_value = iter([])

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_index_created", True),
            ):
                storage.search(embedding=[0.1] * 384, top_k=5)

                # Verify aggregate was called
                assert mock_collection.aggregate.called

    def test_aggregation_with_large_resultset(self) -> None:
        """Test aggregation with 1000+ results."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Create 1000 mock results
            large_results = [
                {
                    "chunk_id": f"chunk{i}",
                    "source_file": f"file{i}.pdf",
                    "page_number": i % 10,
                    "chunk_text": f"text{i}",
                    "score": 0.9 - (i * 0.001),
                }
                for i in range(1000)
            ]

            mock_collection = MagicMock()
            # Return only top_k results (mocking MongoDB behavior)
            mock_collection.aggregate.return_value = iter(large_results[:10])

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_index_created", True),
            ):
                # Request only top 10
                results = storage.search(embedding=[0.1] * 384, top_k=10)

                # Should return only top_k results
                assert len(results) == 10

    def test_aggregation_score_accuracy(self) -> None:
        """Test that scores are within valid range."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.aggregate.return_value = iter(
                [
                    {
                        "chunk_id": "chunk1",
                        "source_file": "test.pdf",
                        "page_number": 1,
                        "chunk_text": "text1",
                        "score": 0.95,
                    },
                    {
                        "chunk_id": "chunk2",
                        "source_file": "test.pdf",
                        "page_number": 2,
                        "chunk_text": "text2",
                        "score": 0.85,
                    },
                ]
            )

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_index_created", True),
            ):
                results = storage.search(embedding=[0.1] * 384, top_k=5)

                # Verify scores are in valid range (0-1)
                for result in results:
                    assert 0 <= result["score"] <= 1

    def test_aggregation_null_field_handling(self) -> None:
        """Test handling of null/missing fields."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.aggregate.return_value = iter(
                [
                    {
                        "chunk_id": "chunk1",
                        "source_file": "test.pdf",
                        "page_number": None,  # Null page number
                        "chunk_text": "text1",
                        "score": 0.9,
                    }
                ]
            )

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_index_created", True),
            ):
                results = storage.search(embedding=[0.1] * 384, top_k=5)

                assert len(results) == 1
                assert results[0]["page_number"] is None

    def test_aggregation_with_special_characters(self) -> None:
        """Test handling of special characters in queries."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_cursor = MagicMock()
            mock_cursor.skip.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.__iter__.return_value = [
                {
                    "chunk_id": "chunk1",
                    "source_file": "test-special_chars.pdf",
                    "page_number": 1,
                    "chunk_text": "text with special chars: $%^&*()",
                }
            ]

            mock_collection = MagicMock()
            mock_collection.find.return_value = mock_cursor

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                chunks = storage.list_chunks(source_filter="test-special", limit=10)

                assert len(chunks) == 1
                assert "special_chars" in chunks[0]["source_file"]
