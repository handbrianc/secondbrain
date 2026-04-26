"""
True unit tests for precision and recall metrics using mocked Searcher.

These tests validate the metrics calculation logic WITHOUT hitting MongoDB,
making them suitable for rapid development feedback loops.

Run with: pytest tests/test_quantitative/test_precision_unit.py -v

Expected runtime: <0.5 seconds for all 9 tests
"""

from unittest.mock import MagicMock

import pytest

from .conftest import (
    calculate_ndcg,
    calculate_precision_at_k,
    calculate_recall_at_k,
)


@pytest.fixture
def mock_searcher():
    """Create a mock searcher that returns pre-defined results."""
    searcher = MagicMock()

    # Pre-defined search results for different queries
    results_map = {
        "What is SecondBrain?": [
            {"chunk_id": "chunk-100", "score": 0.95, "text": "SecondBrain is..."},
            {"chunk_id": "chunk-101", "score": 0.87, "text": "SecondBrain provides..."},
            {"chunk_id": "chunk-102", "score": 0.72, "text": "Semantic search..."},
            {"chunk_id": "chunk-200", "score": 0.65, "text": "Performance..."},
            {"chunk_id": "chunk-300", "score": 0.58, "text": "API..."},
        ],
        "How does semantic search work?": [
            {"chunk_id": "chunk-102", "score": 0.92, "text": "Semantic search uses..."},
            {"chunk_id": "chunk-103", "score": 0.85, "text": "Embedding model..."},
            {"chunk_id": "chunk-100", "score": 0.68, "text": "SecondBrain is..."},
            {"chunk_id": "chunk-200", "score": 0.60, "text": "Performance..."},
            {"chunk_id": "chunk-030", "score": 0.52, "text": "Architecture..."},
        ],
        "System architecture": [
            {"chunk_id": "chunk-030", "score": 0.94, "text": "Architecture..."},
            {"chunk_id": "chunk-031", "score": 0.88, "text": "Circuit breaker..."},
            {"chunk_id": "chunk-032", "score": 0.82, "text": "Rate limiting..."},
            {"chunk_id": "chunk-040", "score": 0.70, "text": "CLI commands..."},
            {"chunk_id": "chunk-050", "score": 0.62, "text": "Search..."},
        ],
        "Configuration options": [
            {"chunk_id": "chunk-001", "score": 0.91, "text": "Chunk size..."},
            {"chunk_id": "chunk-002", "score": 0.86, "text": "MongoDB URI..."},
            {"chunk_id": "chunk-003", "score": 0.79, "text": "Logging..."},
            {"chunk_id": "chunk-070", "score": 0.71, "text": "Chunk config..."},
            {"chunk_id": "chunk-080", "score": 0.64, "text": "Rate limit..."},
        ],
        "Document processing": [
            {"chunk_id": "chunk-020", "score": 0.93, "text": "Document formats..."},
            {"chunk_id": "chunk-021", "score": 0.87, "text": "Pipeline..."},
            {"chunk_id": "chunk-022", "score": 0.80, "text": "PDF extraction..."},
            {"chunk_id": "chunk-030", "score": 0.68, "text": "Architecture..."},
            {"chunk_id": "chunk-041", "score": 0.61, "text": "Ingestor..."},
        ],
        "Rate limiting": [
            {"chunk_id": "chunk-080", "score": 0.92, "text": "Rate limit..."},
            {"chunk_id": "chunk-081", "score": 0.88, "text": "Protects..."},
            {"chunk_id": "chunk-031", "score": 0.75, "text": "Circuit breaker..."},
            {"chunk_id": "chunk-032", "score": 0.69, "text": "Rate limiting..."},
            {"chunk_id": "chunk-090", "score": 0.58, "text": "Logging..."},
        ],
        "CLI commands": [
            {"chunk_id": "chunk-040", "score": 0.95, "text": "CLI commands..."},
            {"chunk_id": "chunk-041", "score": 0.89, "text": "Ingestor class..."},
            {"chunk_id": "chunk-050", "score": 0.76, "text": "Search command..."},
            {"chunk_id": "chunk-051", "score": 0.68, "text": "Semantic search..."},
            {"chunk_id": "chunk-052", "score": 0.62, "text": "Search results..."},
        ],
        "Document formats": [
            {"chunk_id": "chunk-020", "score": 0.94, "text": "Document formats..."},
            {"chunk_id": "chunk-021", "score": 0.85, "text": "Pipeline..."},
            {"chunk_id": "chunk-022", "score": 0.78, "text": "PDF extraction..."},
            {"chunk_id": "chunk-002", "score": 0.67, "text": "Multiple formats..."},
            {"chunk_id": "chunk-030", "score": 0.55, "text": "Architecture..."},
        ],
    }

    def search(query, top_k=10):
        results = results_map.get(query, [])
        return results[:top_k]

    searcher.search = search
    return searcher


@pytest.mark.fast_test
@pytest.mark.precision_recall
@pytest.mark.unit
class TestPrecisionRecallUnit:
    """Unit tests for precision and recall metrics (mocked Searcher)."""

    def test_precision_at_k_5(self, mock_searcher):
        """Test precision@5 calculation."""
        results = mock_searcher.search("What is SecondBrain?", top_k=5)
        relevant_ids = {"chunk-100", "chunk-101"}  # 2 relevant in top 5
        precision = calculate_precision_at_k(results, relevant_ids, k=5)

        assert 0 <= precision <= 1
        assert precision == 2 / 5  # 2 relevant out of 5 results

    def test_precision_at_k_10(self, mock_searcher):
        """Test precision@10 calculation."""
        results = mock_searcher.search("How does semantic search work?", top_k=10)
        relevant_ids = {"chunk-102", "chunk-103"}  # 2 relevant in results
        precision = calculate_precision_at_k(results, relevant_ids, k=10)

        assert 0 <= precision <= 1
        # 2 relevant out of k=10 (even though only 5 results returned)
        assert precision == 2 / 10

    def test_precision_at_k_20(self, mock_searcher):
        """Test precision@20 calculation."""
        results = mock_searcher.search("System architecture", top_k=20)
        relevant_ids = {"chunk-030", "chunk-031", "chunk-032"}  # 3 relevant in results
        precision = calculate_precision_at_k(results, relevant_ids, k=20)

        assert 0 <= precision <= 1
        # 3 relevant out of k=20 (even though only 5 results returned)
        assert precision == 3 / 20

    def test_recall_at_k_5(self, mock_searcher):
        """Test recall@5 calculation."""
        results = mock_searcher.search("Configuration options", top_k=5)
        relevant_ids = {"chunk-001", "chunk-002", "chunk-003"}  # 3 relevant total
        recall = calculate_recall_at_k(results, relevant_ids, k=5)

        assert 0 <= recall <= 1
        # All 3 relevant found in top 5
        assert recall == 1.0

    def test_recall_at_k_10(self, mock_searcher):
        """Test recall@10 calculation."""
        results = mock_searcher.search("Document processing", top_k=10)
        relevant_ids = {"chunk-020", "chunk-021", "chunk-022"}  # 3 relevant total
        recall = calculate_recall_at_k(results, relevant_ids, k=10)

        assert 0 <= recall <= 1
        # All 3 relevant found in top 5 (only 5 results)
        assert recall == 1.0

    def test_recall_at_k_20(self, mock_searcher):
        """Test recall@20 calculation."""
        results = mock_searcher.search("Rate limiting", top_k=20)
        relevant_ids = {"chunk-080", "chunk-081", "chunk-032"}  # 3 relevant total
        recall = calculate_recall_at_k(results, relevant_ids, k=20)

        assert 0 <= recall <= 1
        # All 3 relevant found in top 5
        assert recall == 1.0

    def test_mean_average_precision(self, mock_searcher):
        """Test mean average precision calculation."""
        queries = [
            "What is SecondBrain?",
            "How does semantic search work?",
            "System architecture",
        ]

        ap_scores = []
        for query in queries:
            results = mock_searcher.search(query, top_k=10)

            # Define relevant IDs for each query
            if query == "What is SecondBrain?":
                relevant_ids = {"chunk-100", "chunk-101", "chunk-102"}
            elif query == "How does semantic search work?":
                relevant_ids = {"chunk-102", "chunk-103", "chunk-100"}
            else:  # System architecture
                relevant_ids = {"chunk-030", "chunk-031", "chunk-032"}

            # Calculate average precision
            hits = 0
            sum_precisions = 0
            for i, result in enumerate(results):
                if result["chunk_id"] in relevant_ids:
                    hits += 1
                    sum_precisions += hits / (i + 1)

            ap = sum_precisions / len(relevant_ids) if relevant_ids else 0
            ap_scores.append(ap)

        map_score = sum(ap_scores) / len(ap_scores) if ap_scores else 0

        assert 0 <= map_score <= 1
        # Should have reasonable AP scores
        assert map_score > 0.5

    def test_ndcg_at_k(self, mock_searcher):
        """Test NDCG@K calculation."""
        results = mock_searcher.search("CLI commands", top_k=10)
        relevant_ids = {"chunk-040", "chunk-041"}  # 2 relevant

        ndcg = calculate_ndcg(results, relevant_ids, k=10)

        assert 0 <= ndcg <= 1
        # Should have good NDCG since relevant docs are ranked high
        assert ndcg > 0.7

    def test_precision_recall_tradeoff(self, mock_searcher):
        """Test precision/recall tradeoff behavior."""
        # Get results at different k values
        results_5 = mock_searcher.search("Document formats", top_k=5)
        relevant_ids = {"chunk-020", "chunk-021", "chunk-022"}

        precision_5 = calculate_precision_at_k(results_5, relevant_ids, k=5)
        recall_5 = calculate_recall_at_k(results_5, relevant_ids, k=5)

        # Verify basic properties
        assert 0 <= precision_5 <= 1
        assert 0 <= recall_5 <= 1

        # With all relevant in top 5, recall should be 1.0
        assert recall_5 == 1.0
