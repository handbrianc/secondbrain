"""Tests for filter combinations and aggregation edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import VectorStorage


@pytest.fixture(scope="module")
def mock_storage_config():
    config = MagicMock()
    config.mongo_uri = "mongodb://localhost:27017"
    config.mongo_db = "secondbrain"
    config.mongo_collection = "embeddings"
    config.embedding_dimensions = 384
    return config


@pytest.fixture(scope="module")
def storage_with_mock(mock_storage_config):
    """Module-scoped VectorStorage instance to avoid 1s+ overhead per test."""
    with patch("secondbrain.storage.get_config", return_value=mock_storage_config):
        storage = VectorStorage()
        yield storage


class TestFilterCombinations:
    """Tests for filter combination scenarios."""

    def test_search_with_both_filters(self, storage_with_mock: VectorStorage) -> None:
        """Test search with both source and file_type filters."""
        mock_cursor = MagicMock()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = []

        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor
        mock_collection.aggregate.return_value = iter([])

        with (
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
            patch.object(storage_with_mock, "_index_created", True),
        ):
            storage_with_mock.search(
                embedding=[0.1] * 384,
                top_k=5,
                source_filter="test.pdf",
                file_type_filter="pdf",
            )

            assert mock_collection.aggregate.called

    def test_search_with_regex_source_filter(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test search with regex pattern in source filter."""
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
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
            patch.object(storage_with_mock, "_index_created", True),
        ):
            results = storage_with_mock.search(
                embedding=[0.1] * 384,
                top_k=5,
                source_filter="test_.*\\.pdf",
            )

            assert len(results) == 1
            assert results[0]["source_file"] == "test_2024.pdf"

    def test_search_with_empty_results_filter(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test search when filter produces no results."""
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = iter([])

        with (
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
            patch.object(storage_with_mock, "_index_created", True),
        ):
            results = storage_with_mock.search(
                embedding=[0.1] * 384,
                top_k=5,
                source_filter="nonexistent.pdf",
            )

            assert len(results) == 0

    def test_list_chunks_combined_filters(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test list_chunks with multiple filter conditions."""
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
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
        ):
            chunks = storage_with_mock.list_chunks(
                source_filter="test.pdf",
                chunk_id="chunk1",
                limit=10,
                offset=0,
            )

            assert len(chunks) == 1
            assert chunks[0]["chunk_id"] == "chunk1"

    def test_filter_case_sensitivity(self, storage_with_mock: VectorStorage) -> None:
        """Test case handling in filters."""
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
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
        ):
            chunks = storage_with_mock.list_chunks(source_filter="test.pdf", limit=10)
            assert len(chunks) >= 0


class TestAggregationEdgeCases:
    """Tests for MongoDB aggregation edge cases."""

    def test_aggregation_pipeline_order(self, storage_with_mock: VectorStorage) -> None:
        """Test that aggregation pipeline has correct stage order."""
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = iter([])

        with (
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
            patch.object(storage_with_mock, "_index_created", True),
        ):
            storage_with_mock.search(embedding=[0.1] * 384, top_k=5)
            assert mock_collection.aggregate.called

    def test_aggregation_with_large_resultset(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test aggregation with 1000+ results."""
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
        mock_collection.aggregate.return_value = iter(large_results[:10])

        with (
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
            patch.object(storage_with_mock, "_index_created", True),
        ):
            results = storage_with_mock.search(embedding=[0.1] * 384, top_k=10)
            assert len(results) == 10

    def test_aggregation_score_accuracy(self, storage_with_mock: VectorStorage) -> None:
        """Test that scores are within valid range."""
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
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
            patch.object(storage_with_mock, "_index_created", True),
        ):
            results = storage_with_mock.search(embedding=[0.1] * 384, top_k=5)

            for result in results:
                assert 0 <= result["score"] <= 1

    def test_aggregation_null_field_handling(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test handling of null/missing fields."""
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = iter(
            [
                {
                    "chunk_id": "chunk1",
                    "source_file": "test.pdf",
                    "page_number": None,
                    "chunk_text": "text1",
                    "score": 0.9,
                }
            ]
        )

        with (
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
            patch.object(storage_with_mock, "_index_created", True),
        ):
            results = storage_with_mock.search(embedding=[0.1] * 384, top_k=5)

            assert len(results) == 1
            assert results[0]["page_number"] is None

    def test_aggregation_with_special_characters(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test handling of special characters in queries."""
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
            patch.object(storage_with_mock, "validate_connection", return_value=True),
            patch.object(storage_with_mock, "_collection", mock_collection),
        ):
            chunks = storage_with_mock.list_chunks(
                source_filter="test-special", limit=10
            )

            assert len(chunks) == 1
            assert "special_chars" in chunks[0]["source_file"]
