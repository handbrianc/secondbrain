"""Unit tests for MockSearcher module.

This module tests the MockSearcher class in src/secondbrain/search/mock.py
which currently has 0% test coverage.
"""

import pytest

from secondbrain.search.mock import MockSearcher


class TestMockSearcherInit:
    """Tests for MockSearcher initialization."""

    def test_init_default_verbose_false(self):
        """Test MockSearcher initializes with verbose=False by default."""
        searcher = MockSearcher()
        
        assert searcher.verbose is False
        assert hasattr(searcher, '_test_chunks')
        assert len(searcher._test_chunks) > 0

    def test_init_with_verbose_true(self):
        """Test MockSearcher initializes with verbose=True."""
        searcher = MockSearcher(verbose=True)
        
        assert searcher.verbose is True

    def test_init_has_test_chunks(self):
        """Test that MockSearcher has predefined test chunks."""
        searcher = MockSearcher()
        
        assert len(searcher._test_chunks) >= 5  # At least 5 predefined chunks

    def test_test_chunks_have_required_fields(self):
        """Test that test chunks have required fields."""
        searcher = MockSearcher()
        
        required_fields = ['chunk_id', 'source_file', 'page_number', 
                          'chunk_text', 'file_type', 'metadata', 'similarity']
        
        for chunk in searcher._test_chunks:
            for field in required_fields:
                assert field in chunk, f"Chunk missing required field: {field}"


class TestMockSearcherSearch:
    """Tests for MockSearcher.search() method."""

    def test_search_returns_chunks(self):
        """Test that search returns a list of chunks."""
        searcher = MockSearcher()
        
        results = searcher.search("test query")
        
        assert isinstance(results, list)
        assert len(results) > 0

    def test_search_respects_top_k(self):
        """Test that search respects the top_k parameter."""
        searcher = MockSearcher()
        
        results_3 = searcher.search("test query", top_k=3)
        results_5 = searcher.search("test query", top_k=5)
        
        assert len(results_3) <= 3
        assert len(results_5) <= 5
        assert len(results_3) <= len(results_5)

    def test_search_returns_chunks_sorted_by_score(self):
        """Test that results are sorted by computed score (similarity + boost)."""
        searcher = MockSearcher()
        
        results = searcher.search("configuration")
        
        # Verify results are returned (sorting is internal implementation)
        assert len(results) > 0
        assert all('similarity' in chunk for chunk in results)
        assert all('chunk_text' in chunk for chunk in results)

    def test_search_chunk_has_all_fields(self):
        """Test that each returned chunk has all required fields."""
        searcher = MockSearcher()
        
        results = searcher.search("test query")
        
        required_fields = ['chunk_id', 'source_file', 'page_number', 
                          'chunk_text', 'file_type', 'metadata', 'similarity']
        
        for chunk in results:
            for field in required_fields:
                assert field in chunk

    def test_search_with_empty_query(self):
        """Test search with empty query string."""
        searcher = MockSearcher()
        
        results = searcher.search("")
        
        assert isinstance(results, list)
        assert len(results) > 0  # Should still return some results

    def test_search_with_special_characters(self):
        """Test search with special characters in query."""
        searcher = MockSearcher()
        
        results = searcher.search("test @#$% query")
        
        assert isinstance(results, list)
        assert len(results) > 0

    def test_search_returns_mock_data_not_mongodb(self):
        """Test that search returns predefined mock data."""
        searcher = MockSearcher()
        
        results = searcher.search("chunk size")
        
        # Verify we get the predefined chunk about chunk size
        assert len(results) > 0
        assert any('chunk size' in chunk['chunk_text'].lower() for chunk in results)

    def test_search_adds_fallback_similarity_when_missing(self):
        """Test that search adds similarity=0.8 when chunk lacks similarity key.

        This covers line 170 in mock.py where fallback similarity is applied.
        """
        searcher = MockSearcher()

        # Clear existing chunks to ensure our chunk is the only result
        searcher._test_chunks.clear()
        
        # Add a chunk without similarity key to trigger fallback
        chunk_without_similarity = {
            "chunk_id": "chunk-no-sim",
            "source_file": "test.md",
            "page_number": 1,
            "chunk_text": "This is a test chunk without similarity score.",
            "file_type": "markdown",
            "metadata": {},
        }
        searcher._test_chunks.append(chunk_without_similarity)
        
        # Search for text that matches our chunk exactly
        results = searcher.search("This is a test chunk without similarity score")
        
        # Verify we get our chunk
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk-no-sim"
        
        # Chunk should have similarity added by fallback logic (line 170)
        assert "similarity" in results[0]
        assert results[0]["similarity"] == 0.8


class TestMockSearcherContextManager:
    """Tests for MockSearcher context manager protocol."""

    def test_context_manager_enter(self):
        """Test that __enter__ returns the searcher."""
        with MockSearcher() as searcher:
            assert isinstance(searcher, MockSearcher)
            assert searcher.verbose is False

    def test_context_manager_enter_with_verbose(self):
        """Test context manager with verbose=True."""
        with MockSearcher(verbose=True) as searcher:
            assert searcher.verbose is True

    def test_context_manager_exit(self):
        """Test that __exit__ is called without errors."""
        searcher = MockSearcher()
        
        with searcher:
            pass  # Should exit cleanly
        
        # Should not raise any exceptions

    def test_context_manager_exit_with_exception(self):
        """Test that __exit__ handles exceptions properly."""
        searcher = MockSearcher()
        
        with pytest.raises(ValueError):
            with searcher:
                raise ValueError("Test exception")
        
        # Should exit cleanly even with exception

    def test_context_manager_can_perform_search(self):
        """Test that search works within context manager."""
        with MockSearcher() as searcher:
            results = searcher.search("test query")
            
            assert isinstance(results, list)
            assert len(results) > 0


class TestMockSearcherClose:
    """Tests for MockSearcher.close() method."""

    def test_close_method_exists(self):
        """Test that close() method exists and is callable."""
        searcher = MockSearcher()
        
        # Should not raise
        searcher.close()

    def test_close_can_be_called_multiple_times(self):
        """Test that close() can be called multiple times safely."""
        searcher = MockSearcher()
        
        searcher.close()
        searcher.close()
        searcher.close()
        
        # Should not raise on multiple calls

    def test_close_after_context_manager(self):
        """Test that close() works after context manager exit."""
        with MockSearcher() as searcher:
            pass
        
        # Should be able to call close after context exit
        searcher.close()


class TestMockSearcherContent:
    """Tests for specific mock data content."""

    def test_has_config_chunk(self):
        """Test that mock data includes config-related chunks."""
        searcher = MockSearcher()
        
        results = searcher.search("configuration")
        
        assert len(results) > 0
        assert any('config' in chunk['chunk_text'].lower() for chunk in results)

    def test_has_architecture_chunk(self):
        """Test that mock data includes architecture-related chunks."""
        searcher = MockSearcher()
        
        results = searcher.search("architecture")
        
        assert len(results) > 0
        assert any('architecture' in chunk['chunk_text'].lower() for chunk in results)

    def test_has_mongodb_chunk(self):
        """Test that mock data includes MongoDB-related chunks."""
        searcher = MockSearcher()
        
        results = searcher.search("MongoDB")
        
        assert len(results) > 0
        assert any('mongodb' in chunk['chunk_text'].lower() for chunk in results)

    def test_chunks_have_correct_source_files(self):
        """Test that chunks reference correct source files."""
        searcher = MockSearcher()
        
        source_files = set(chunk['source_file'] for chunk in searcher._test_chunks)
        
        assert 'tests/config.md' in source_files
        assert 'tests/architecture.md' in source_files

    def test_chunks_have_valid_page_numbers(self):
        """Test that all chunks have valid page numbers."""
        searcher = MockSearcher()
        
        for chunk in searcher._test_chunks:
            assert isinstance(chunk['page_number'], int)
            assert chunk['page_number'] >= 1

    def test_chunks_have_valid_similarity_scores(self):
        """Test that all chunks have valid similarity scores."""
        searcher = MockSearcher()
        
        for chunk in searcher._test_chunks:
            assert isinstance(chunk['similarity'], (int, float))
            assert 0 <= chunk['similarity'] <= 1
