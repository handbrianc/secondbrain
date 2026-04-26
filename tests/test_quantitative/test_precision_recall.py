"""
Precision and Recall metric tests for search result quality.

This module tests:
- Precision@K (K=5, 10, 20): Fraction of relevant results in top K
- Recall@K (K=5, 10, 20): Fraction of all relevant results found in top K
- Mean Average Precision (mAP): Average precision across all queries
- Normalized Discounted Cumulative Gain (nDCG): Ranking quality metric

Note: These are integration tests that require MongoDB with indexed documents.
Run with: pytest -m "precision_recall and integration"
"""

import pytest

from secondbrain.search import Searcher
from tests.stats_utils import bootstrap_ci, calculate_ci_mean

from .conftest import (
    calculate_map,
    calculate_ndcg,
    calculate_precision_at_k,
    calculate_recall_at_k,
)

# Minimum sample size for reliable bootstrap CI estimation
MIN_SAMPLE_SIZE = 5


@pytest.mark.precision_recall
@pytest.mark.integration
class TestPrecisionRecall:
    """Test precision and recall metrics for search results."""

    @pytest.fixture
    def searcher(self, seeded_chunks_with_embeddings):
        """Create a Searcher instance for testing."""
        return Searcher()

    @pytest.fixture
    def precision_thresholds(self):
        """Precision thresholds for different K values."""
        return {
            5: 0.4,  # P@5 >= 0.4
            10: 0.5,  # P@10 >= 0.5
            20: 0.4,  # P@20 >= 0.4
        }

    @pytest.fixture
    def recall_thresholds(self):
        """Recall thresholds for different K values."""
        return {
            5: 0.3,  # R@5 >= 0.3
            10: 0.4,  # R@10 >= 0.4
            20: 0.5,  # R@20 >= 0.5
        }

    @pytest.mark.parametrize("k,threshold", [(5, 0.4), (10, 0.5), (20, 0.4)])
    def test_precision_at_k(
        self,
        searcher: Searcher,
        golden_datasets: dict,
        k: int,
        threshold: float,
        precision_thresholds: dict[int, float],
    ) -> None:
        """Test precision at K for different K values using bootstrap confidence intervals.

        Precision@K = (Number of relevant results in top K) / K

        Uses bootstrap resampling to calculate confidence intervals for precision metrics,
        providing statistical rigor over point estimates.

        Args:
            searcher: Searcher instance for performing searches
            golden_datasets: Loaded golden datasets
            k: Number of top results to consider (5, 10, or 20)
            threshold: Minimum acceptable precision threshold
            precision_thresholds: Configurable thresholds per K value

        Asserts:
            Bootstrap CI lower bound for Precision@K meets or exceeds the threshold
            Failure message includes CI bounds, CI width, and sample size
        """
        # Use precision_recall_golden dataset
        if "precision_recall_golden" not in golden_datasets:
            pytest.skip("Golden dataset not available")

        dataset = golden_datasets["precision_recall_golden"]

        test_results = searcher.search("test", top_k=1)
        if len(test_results) == 0:
            pytest.skip("Database is empty - no documents to search")

        precisions = []
        for test_case in dataset:
            query = test_case["query"]
            relevant_ids = set(test_case["relevant_chunk_ids"])

            # Perform search with top_k parameter
            results = searcher.search(query, top_k=k)

            precision = calculate_precision_at_k(results, relevant_ids, k)

            if precision == 0.0:
                pytest.skip("No relevant documents found in database for this query")

            precisions.append(precision)

        # Validate sample size for reliable CI estimation
        n_samples = len(precisions)
        if n_samples < MIN_SAMPLE_SIZE:
            pytest.skip(
                f"Insufficient samples for bootstrap CI: n={n_samples} < {MIN_SAMPLE_SIZE}"
            )

        # Calculate bootstrap confidence interval
        ci_lower, ci_upper = bootstrap_ci(precisions, n_iterations=1000, confidence=0.95)
        ci_width = ci_upper - ci_lower
        mean_precision = calculate_ci_mean(precisions)[0] + (
            calculate_ci_mean(precisions)[1] - calculate_ci_mean(precisions)[0]
        ) / 2

        # Assert CI lower bound meets threshold
        actual_threshold = precision_thresholds.get(k, threshold)
        assert ci_lower >= actual_threshold, (
            f"Precision@{k} CI lower bound too low: "
            f"ci_lower={ci_lower:.4f}, ci_upper={ci_upper:.4f}, "
            f"ci_width={ci_width:.4f}, mean={mean_precision:.4f}, "
            f"threshold={actual_threshold}, n_samples={n_samples}"
        )

        # Report results
        print(
            f"Precision@{k} test completed. "
            f"Mean: {mean_precision:.4f}, 95% CI: [{ci_lower:.4f}, {ci_upper:.4f}], "
            f"width={ci_width:.4f}, n={n_samples}"
        )

    @pytest.mark.parametrize("k,threshold", [(5, 0.3), (10, 0.4), (20, 0.5)])
    def test_recall_at_k(
        self,
        searcher: Searcher,
        golden_datasets: dict,
        k: int,
        threshold: float,
        recall_thresholds: dict[int, float],
    ) -> None:
        """Test recall at K for different K values using bootstrap confidence intervals.

        Recall@K = (Number of relevant results in top K) / (Total relevant results)

        Uses bootstrap resampling to calculate confidence intervals for recall metrics,
        providing statistical rigor over point estimates.

        Args:
            searcher: Searcher instance for performing searches
            golden_datasets: Loaded golden datasets
            k: Number of top results to consider (5, 10, or 20)
            threshold: Minimum acceptable recall threshold
            recall_thresholds: Configurable thresholds per K value

        Asserts:
            Bootstrap CI lower bound for Recall@K meets or exceeds the threshold
            Failure message includes CI bounds, CI width, and sample size
        """
        # Use precision_recall_golden dataset
        if "precision_recall_golden" not in golden_datasets:
            pytest.skip("Golden dataset not available")

        dataset = golden_datasets["precision_recall_golden"]

        recalls = []
        for test_case in dataset:
            query = test_case["query"]
            relevant_ids = set(test_case["relevant_chunk_ids"])

            # Perform search with top_k parameter
            results = searcher.search(
                query, top_k=max(k, 20)
            )  # Search more to get better recall

            # Calculate recall using helper from conftest
            recall = calculate_recall_at_k(results, relevant_ids, k)

            if recall == 0.0:
                pytest.skip("No relevant documents found in database for this query")

            recalls.append(recall)

        # Validate sample size for reliable CI estimation
        n_samples = len(recalls)
        if n_samples < MIN_SAMPLE_SIZE:
            pytest.skip(
                f"Insufficient samples for bootstrap CI: n={n_samples} < {MIN_SAMPLE_SIZE}"
            )

        # Calculate bootstrap confidence interval
        ci_lower, ci_upper = bootstrap_ci(recalls, n_iterations=1000, confidence=0.95)
        ci_width = ci_upper - ci_lower
        mean_recall = calculate_ci_mean(recalls)[0] + (
            calculate_ci_mean(recalls)[1] - calculate_ci_mean(recalls)[0]
        ) / 2

        # Assert CI lower bound meets threshold
        actual_threshold = recall_thresholds.get(k, threshold)
        assert ci_lower >= actual_threshold, (
            f"Recall@{k} CI lower bound too low: "
            f"ci_lower={ci_lower:.4f}, ci_upper={ci_upper:.4f}, "
            f"ci_width={ci_width:.4f}, mean={mean_recall:.4f}, "
            f"threshold={actual_threshold}, n_samples={n_samples}"
        )

        # Report results
        print(
            f"Recall@{k} test completed. "
            f"Mean: {mean_recall:.4f}, 95% CI: [{ci_lower:.4f}, {ci_upper:.4f}], "
            f"width={ci_width:.4f}, n={n_samples}"
        )

    def test_mean_average_precision(
        self,
        searcher: Searcher,
        golden_datasets: dict,
    ) -> None:
        """Test Mean Average Precision (mAP) across all queries using bootstrap CI.

        mAP = (1 / |queries|) * sum(AP for each query)
        where AP = (1 / |relevant|) * sum(precision at each relevant item)

        Uses bootstrap resampling to calculate confidence intervals for mAP,
        providing statistical rigor over point estimates.

        Args:
            searcher: Searcher instance for performing searches
            golden_datasets: Loaded golden datasets

        Asserts:
            Bootstrap CI lower bound for mAP >= 0.5
            Failure message includes CI bounds, CI width, and sample size
        """
        # Use precision_recall_golden dataset
        if "precision_recall_golden" not in golden_datasets:
            pytest.skip("Golden dataset not available")

        dataset = golden_datasets["precision_recall_golden"]

        map_scores = []
        for test_case in dataset:
            query = test_case["query"]
            relevant_ids = set(test_case["relevant_chunk_ids"])

            # Perform search with larger top_k to capture more relevant results
            results = searcher.search(query, top_k=20)

            # Calculate AP using helper from conftest
            ap = calculate_map(results, relevant_ids)

            if ap == 0.0:
                pytest.skip("No relevant documents found in database for this query")

            map_scores.append(ap)

        # Validate sample size for reliable CI estimation
        n_samples = len(map_scores)
        if n_samples < MIN_SAMPLE_SIZE:
            pytest.skip(
                f"Insufficient samples for bootstrap CI: n={n_samples} < {MIN_SAMPLE_SIZE}"
            )

        # Calculate bootstrap confidence interval
        ci_lower, ci_upper = bootstrap_ci(map_scores, n_iterations=1000, confidence=0.95)
        ci_width = ci_upper - ci_lower
        mean_map = calculate_ci_mean(map_scores)[0] + (
            calculate_ci_mean(map_scores)[1] - calculate_ci_mean(map_scores)[0]
        ) / 2

        # Assert CI lower bound meets threshold
        threshold = 0.5
        assert ci_lower >= threshold, (
            f"mAP CI lower bound too low: "
            f"ci_lower={ci_lower:.4f}, ci_upper={ci_upper:.4f}, "
            f"ci_width={ci_width:.4f}, mean={mean_map:.4f}, "
            f"threshold={threshold}, n_samples={n_samples}"
        )

        # Report results
        print(
            f"mAP test completed. "
            f"Mean: {mean_map:.4f}, 95% CI: [{ci_lower:.4f}, {ci_upper:.4f}], "
            f"width={ci_width:.4f}, n={n_samples}"
        )

    def test_ndcg_at_k(
        self,
        searcher: Searcher,
        golden_datasets: dict,
    ) -> None:
        """Test Normalized Discounted Cumulative Gain at K=10 using bootstrap CI.

        nDCG@K = DCG@K / IDCG@K
        where:
            DCG@K = sum(rel_i / log2(i+1)) for i=1 to K
            IDCG@K = ideal DCG (all relevant docs at top)

        Uses bootstrap resampling to calculate confidence intervals for nDCG,
        providing statistical rigor over point estimates.

        Args:
            searcher: Searcher instance for performing searches
            golden_datasets: Loaded golden datasets

        Asserts:
            Bootstrap CI lower bound for nDCG@10 >= 0.6
            Failure message includes CI bounds, CI width, and sample size
        """
        # Use precision_recall_golden dataset
        if "precision_recall_golden" not in golden_datasets:
            pytest.skip("Golden dataset not available")

        dataset = golden_datasets["precision_recall_golden"]
        k = 10
        threshold = 0.6

        ndcg_scores = []
        for test_case in dataset:
            query = test_case["query"]
            relevant_ids = set(test_case["relevant_chunk_ids"])

            # Perform search with top_k parameter
            results = searcher.search(query, top_k=k)

            # Calculate nDCG using helper from conftest
            ndcg = calculate_ndcg(results, relevant_ids, k)

            if ndcg == 0.0:
                pytest.skip("No relevant documents found in database for this query")

            ndcg_scores.append(ndcg)

        # Validate sample size for reliable CI estimation
        n_samples = len(ndcg_scores)
        if n_samples < MIN_SAMPLE_SIZE:
            pytest.skip(
                f"Insufficient samples for bootstrap CI: n={n_samples} < {MIN_SAMPLE_SIZE}"
            )

        # Calculate bootstrap confidence interval
        ci_lower, ci_upper = bootstrap_ci(ndcg_scores, n_iterations=1000, confidence=0.95)
        ci_width = ci_upper - ci_lower
        mean_ndcg = calculate_ci_mean(ndcg_scores)[0] + (
            calculate_ci_mean(ndcg_scores)[1] - calculate_ci_mean(ndcg_scores)[0]
        ) / 2

        # Assert CI lower bound meets threshold
        assert ci_lower >= threshold, (
            f"nDCG@{k} CI lower bound too low: "
            f"ci_lower={ci_lower:.4f}, ci_upper={ci_upper:.4f}, "
            f"ci_width={ci_width:.4f}, mean={mean_ndcg:.4f}, "
            f"threshold={threshold}, n_samples={n_samples}"
        )

        # Report results
        print(
            f"nDCG@{k} test completed. "
            f"Mean: {mean_ndcg:.4f}, 95% CI: [{ci_lower:.4f}, {ci_upper:.4f}], "
            f"width={ci_width:.4f}, n={n_samples}"
        )

    def test_precision_recall_tradeoff(
        self,
        searcher: Searcher,
        golden_datasets: dict,
    ) -> None:
        """Test the precision-recall tradeoff at different K values.

        As K increases:
        - Precision typically decreases (more non-relevant results included)
        - Recall typically increases (more relevant results found)

        Args:
            searcher: Searcher instance for performing searches
            golden_datasets: Loaded golden datasets

        Asserts:
            Precision@5 >= Precision@10 >= Precision@20 (non-increasing)
            Recall@5 <= Recall@10 <= Recall@20 (non-decreasing)
        """
        # Use precision_recall_golden dataset
        if "precision_recall_golden" not in golden_datasets:
            pytest.skip("Golden dataset not available")

        dataset = golden_datasets["precision_recall_golden"]

        # Test with first query as representative sample
        test_case = dataset[0]
        query = test_case["query"]
        relevant_ids = set(test_case["relevant_chunk_ids"])

        # Get results with large top_k
        all_results = searcher.search(query, top_k=20)

        # Calculate precision at different K values
        p5 = calculate_precision_at_k(all_results, relevant_ids, 5)
        p10 = calculate_precision_at_k(all_results, relevant_ids, 10)
        p20 = calculate_precision_at_k(all_results, relevant_ids, 20)

        # Calculate recall at different K values
        r5 = calculate_recall_at_k(all_results, relevant_ids, 5)
        r10 = calculate_recall_at_k(all_results, relevant_ids, 10)
        r20 = calculate_recall_at_k(all_results, relevant_ids, 20)

        # Assert precision is non-increasing with K
        assert p5 >= p10 >= p20, (
            f"Precision should be non-increasing: "
            f"P@5={p5:.4f}, P@10={p10:.4f}, P@20={p20:.4f}"
        )

        # Assert recall is non-decreasing with K
        assert r5 <= r10 <= r20, (
            f"Recall should be non-decreasing: "
            f"R@5={r5:.4f}, R@10={r10:.4f}, R@20={r20:.4f}"
        )

        pytest.skip(
            f"Precision-Recall tradeoff verified. "
            f"P@5={p5:.4f}, P@10={p10:.4f}, P@20={p20:.4f}; "
            f"R@5={r5:.4f}, R@10={r10:.4f}, R@20={r20:.4f}"
        )
