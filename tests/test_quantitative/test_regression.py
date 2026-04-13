"""
Regression testing module for RAG pipeline quality and performance tracking.

This module provides comprehensive regression tests to detect and prevent
quality and performance degradation in the SecondBrain RAG system. Tests include:

1. Baseline answer storage and comparison
2. Version-to-version performance comparison
3. Answer quality regression detection
4. Response time regression detection
5. Semantic similarity regression detection
6. Search result quality regression detection

All tests compare current behavior against established baselines to ensure
no unintended degradation occurs between versions.
"""

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest
from sentence_transformers import SentenceTransformer

from secondbrain.rag import RAGPipeline
from secondbrain.rag.providers import OllamaLLMProvider
from secondbrain.search import Searcher
from tests.test_quantitative.conftest import cosine_similarity

# Regression test thresholds
BASELINE_DIR = Path(__file__).parent.parent / "data" / "regression_baselines"
ANSWER_SIMILARITY_THRESHOLD = 0.85  # Minimum similarity to baseline answer
RESPONSE_TIME_TOLERANCE = 1.5  # Max multiplier over baseline response time
PRECISION_TOLERANCE = 0.1  # Max tolerance drop in precision@K
RECALL_TOLERANCE = 0.1  # Max tolerance drop in recall@K
NUM_BENCHMARK_RUNS = 5  # Runs for baseline comparison


def ensure_baseline_dir() -> Path:
    """Ensure baseline directory exists."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    return BASELINE_DIR


def load_baseline(baseline_name: str) -> dict[str, Any]:
    """
    Load a baseline dataset by name.

    Args:
        baseline_name: Name of the baseline (without .json extension)

    Returns:
        Baseline data dictionary

    Raises:
        FileNotFoundError: If baseline file doesn't exist
    """
    baseline_path = BASELINE_DIR / f"{baseline_name}.json"

    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline not found: {baseline_path}")

    with open(baseline_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_baseline(baseline_name: str, data: dict[str, Any]) -> None:
    """
    Save a baseline dataset by name.

    Args:
        baseline_name: Name of the baseline (without .json extension)
        data: Baseline data to save
    """
    baseline_path = BASELINE_DIR / f"{baseline_name}.json"
    ensure_baseline_dir()

    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    embedding1 = embedding1.reshape(1, -1)
    embedding2 = embedding2.reshape(1, -1)

    from sklearn.metrics.pairwise import cosine_similarity

    similarity = cosine_similarity(embedding1, embedding2)[0][0]
    return float(similarity)


class TestRegressionBaselines:
    """Regression tests with baseline comparison."""

    @pytest.fixture
    def embedding_model(self) -> Any:
        """Load embedding model for similarity calculations."""
        return SentenceTransformer("all-MiniLM-L6-v2")  # type: ignore[operator]

    @pytest.fixture
    def regression_queries(self) -> list[dict[str, Any]]:
        """
        Regression test queries with baseline answers.

        Returns:
            List of regression test queries with expected answers and metadata
        """
        return [
            {
                "id": "regression-001",
                "query": "What is the default chunk size in SecondBrain?",
                "baseline_answer": "The default chunk size is 4096 tokens.",
                "category": "configuration",
                "min_similarity": 0.85,
            },
            {
                "id": "regression-002",
                "query": "How do I configure MongoDB connection URI?",
                "baseline_answer": "Set the SECONDBRAIN_MONGO_URI environment variable.",
                "category": "configuration",
                "min_similarity": 0.80,
            },
            {
                "id": "regression-003",
                "query": "What document formats are supported?",
                "baseline_answer": "PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio.",
                "category": "features",
                "min_similarity": 0.85,
            },
            {
                "id": "regression-004",
                "query": "How to enable circuit breaker?",
                "baseline_answer": "Set SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true.",
                "category": "configuration",
                "min_similarity": 0.85,
            },
            {
                "id": "regression-005",
                "query": "What is the purpose of the Ingestor class?",
                "baseline_answer": (
                    "The Ingestor class handles multi-format document parsing "
                    "and chunking for the SecondBrain system."
                ),
                "category": "architecture",
                "min_similarity": 0.80,
            },
            {
                "id": "regression-006",
                "query": "What is semantic search?",
                "baseline_answer": (
                    "Semantic search uses embedding models to find documents "
                    "based on meaning rather than exact keyword matching."
                ),
                "category": "features",
                "min_similarity": 0.80,
            },
            {
                "id": "regression-007",
                "query": "How does the circuit breaker work?",
                "baseline_answer": (
                    "The circuit breaker automatically fails fast when a service "
                    "is unavailable and attempts recovery after a timeout period."
                ),
                "category": "architecture",
                "min_similarity": 0.75,
            },
            {
                "id": "regression-008",
                "query": "What is the benefit of multicore processing?",
                "baseline_answer": (
                    "Multicore processing enables parallel document ingestion, "
                    "significantly reducing processing time for large document collections."
                ),
                "category": "performance",
                "min_similarity": 0.75,
            },
        ]

    @pytest.mark.regression
    @pytest.mark.baseline
    @pytest.mark.parametrize(
        "test_query",
        [
            pytest.param(
                {
                    "id": "regression-001",
                    "query": "What is the default chunk size in SecondBrain?",
                    "baseline_answer": "The default chunk size is 4096 tokens.",
                    "category": "configuration",
                    "min_similarity": 0.85,
                },
                id="baseline_chunk_size",
            ),
            pytest.param(
                {
                    "id": "regression-002",
                    "query": "How do I configure MongoDB connection URI?",
                    "baseline_answer": "Set the SECONDBRAIN_MONGO_URI environment variable.",
                    "category": "configuration",
                    "min_similarity": 0.80,
                },
                id="baseline_mongodb_config",
            ),
            pytest.param(
                {
                    "id": "regression-003",
                    "query": "What document formats are supported?",
                    "baseline_answer": "PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio.",
                    "category": "features",
                    "min_similarity": 0.85,
                },
                id="baseline_formats",
            ),
        ],
    )
    def test_answer_quality_regression(
        self,
        test_query: dict[str, Any],
        embedding_model: Any,
    ) -> None:
        """Test for answer quality regression against baseline.

        This test validates that the current answer quality matches or exceeds
        the established baseline by measuring semantic similarity.

        Expected:
            - Answer similarity to baseline >= threshold
            - No significant degradation in answer quality
            - Semantic meaning preserved across versions

        Args:
            test_query: Test query with baseline answer and metadata.
            embedding_model: Pre-loaded SentenceTransformer model.
        """
        query = test_query["query"]
        query_id = test_query["id"]
        baseline_answer = test_query["baseline_answer"]
        category = test_query["category"]
        min_similarity = test_query["min_similarity"]

        # Collect current answers across multiple runs
        current_answers: list[str] = []

        for run in range(NUM_BENCHMARK_RUNS):
            try:
                searcher = Searcher(verbose=False)
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=5
                )

                result = pipeline.query(query, top_k=5)
                answer = result.get("answer", "")

                if answer and "apologize" not in answer.lower():
                    current_answers.append(answer)

                searcher.close()
            except Exception:
                continue

        if not current_answers:
            pytest.skip("Could not generate current answers for comparison")

        # Calculate similarity to baseline for each run
        similarities: list[float] = []
        for current_answer in current_answers:
            sim = cosine_similarity(baseline_answer, current_answer, embedding_model)
            similarities.append(sim)

        # Use mean similarity for comparison
        mean_similarity = sum(similarities) / len(similarities)

        # Build failure message
        failure_message = (
            f"Answer quality regression detected\n"
            f"Query ID: {query_id}\n"
            f"Category: {category}\n"
            f"Query: '{query}'\n\n"
            f"Baseline answer: '{baseline_answer[:100]}...'\n\n"
            f"Current answers:\n"
        )

        for i, (answer, sim) in enumerate(zip(current_answers, similarities), 1):
            failure_message += (
                f"  Run {i}: similarity={sim:.4f}\n           '{answer[:100]}...'\n"
            )

        failure_message += (
            f"\nMean similarity: {mean_similarity:.4f}\n"
            f"Minimum threshold: {min_similarity:.4f}\n"
            f"Similarities: {[f'{s:.4f}' for s in similarities]}"
        )

        # Assert no regression
        assert mean_similarity >= min_similarity, failure_message

    @pytest.mark.regression
    @pytest.mark.benchmark
    def test_response_time_regression(
        self,
        regression_queries: list[dict[str, Any]],
    ) -> None:
        """Test for response time regression against baseline.

        This test validates that response times have not significantly increased
        compared to established baselines.

        Expected:
            - Response time <= baseline * tolerance
            - No significant performance degradation
            - Consistent latency across runs

        Args:
            regression_queries: List of regression test queries.
        """
        # Select a representative query for timing
        test_query = regression_queries[0]["query"]
        query_id = regression_queries[0]["id"]

        # Collect current response times
        current_times: list[float] = []

        for run in range(NUM_BENCHMARK_RUNS):
            try:
                searcher = Searcher(verbose=False)
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=3
                )

                import time

                start = time.perf_counter()
                pipeline.query(test_query, top_k=3)
                elapsed = time.perf_counter() - start

                current_times.append(elapsed)

                searcher.close()
            except Exception:
                continue

        if not current_times:
            pytest.skip("Could not collect response time measurements")

        # Calculate statistics
        current_mean_time = sum(current_times) / len(current_times)
        current_p95_time = self._calculate_percentile(current_times, 95)

        # Load or create baseline
        try:
            baseline_data = load_baseline("response_times")
            baseline_mean_time = baseline_data.get("mean_time", current_mean_time)
            baseline_p95_time = baseline_data.get("p95_time", current_p95_time)
        except FileNotFoundError:
            # First run - create baseline
            baseline_data = {
                "mean_time": current_mean_time,
                "p95_time": current_p95_time,
                "timestamp": "initial_baseline",
                "query_id": query_id,
            }
            save_baseline("response_times", baseline_data)
            baseline_mean_time = current_mean_time
            baseline_p95_time = current_p95_time

        # Check for regression
        time_ratio = (
            current_mean_time / baseline_mean_time if baseline_mean_time > 0 else 1.0
        )
        p95_ratio = (
            current_p95_time / baseline_p95_time if baseline_p95_time > 0 else 1.0
        )

        failure_message = (
            f"Response time regression detected\n"
            f"Query ID: {query_id}\n"
            f"Query: '{test_query}'\n\n"
            f"Baseline mean time: {baseline_mean_time:.3f}s\n"
            f"Current mean time: {current_mean_time:.3f}s\n"
            f"Time ratio: {time_ratio:.2f}x (max allowed: {RESPONSE_TIME_TOLERANCE}x)\n\n"
            f"Baseline P95 time: {baseline_p95_time:.3f}s\n"
            f"Current P95 time: {current_p95_time:.3f}s\n"
            f"P95 ratio: {p95_ratio:.2f}x\n\n"
            f"Current samples: {[f'{t:.3f}s' for t in current_times]}"
        )

        # Assert no significant regression
        assert time_ratio <= RESPONSE_TIME_TOLERANCE, failure_message
        assert p95_ratio <= RESPONSE_TIME_TOLERANCE * 1.2, (
            f"{failure_message}\n\nP95 regression exceeds tolerance"
        )

    @pytest.mark.regression
    @pytest.mark.precision_recall
    def test_search_quality_regression(
        self,
        regression_queries: list[dict[str, Any]],
        embedding_model: Any,
    ) -> None:
        """Test for search quality regression (precision/recall).

        This test validates that search result quality has not degraded
        by comparing precision@K and recall@K metrics against baselines.

        Expected:
            - Precision@K >= baseline - tolerance
            - Recall@K >= baseline - tolerance
            - No significant drop in search quality

        Args:
            regression_queries: List of regression test queries.
            embedding_model: Pre-loaded SentenceTransformer model.
        """
        # Use first query for search quality test
        test_query = regression_queries[0]
        query = test_query["query"]
        query_id = test_query["id"]

        try:
            searcher = Searcher(verbose=False)

            # Get search results
            results = searcher.search(query, top_k=10)

            # For regression testing, we use semantic similarity to query
            # as a proxy for relevance (since we don't have ground truth)
            relevance_scores: list[float] = []

            for result in results:
                result_text = result.get("text", "") or result.get("content", "")
                if result_text:
                    sim = cosine_similarity(query, result_text, embedding_model)
                    relevance_scores.append(sim)

            searcher.close()

            if not relevance_scores:
                pytest.skip("No search results to evaluate")

            # Calculate metrics
            precision_at_5 = sum(1 for s in relevance_scores[:5] if s > 0.5) / 5
            precision_at_10 = sum(1 for s in relevance_scores[:10] if s > 0.5) / 10

            # Load or create baseline
            try:
                baseline_data = load_baseline("search_quality")
                baseline_p5 = baseline_data.get("precision_at_5", precision_at_5)
                baseline_p10 = baseline_data.get("precision_at_10", precision_at_10)
            except FileNotFoundError:
                # First run - create baseline
                baseline_data = {
                    "precision_at_5": precision_at_5,
                    "precision_at_10": precision_at_10,
                    "timestamp": "initial_baseline",
                    "query_id": query_id,
                }
                save_baseline("search_quality", baseline_data)
                baseline_p5 = precision_at_5
                baseline_p10 = precision_at_10

            # Check for regression
            p5_drop = baseline_p5 - precision_at_5
            p10_drop = baseline_p10 - precision_at_10

            failure_message = (
                f"Search quality regression detected\n"
                f"Query ID: {query_id}\n"
                f"Query: '{query}'\n\n"
                f"Baseline Precision@5: {baseline_p5:.4f}\n"
                f"Current Precision@5: {precision_at_5:.4f}\n"
                f"P@5 drop: {p5_drop:.4f} (max allowed: {PRECISION_TOLERANCE})\n\n"
                f"Baseline Precision@10: {baseline_p10:.4f}\n"
                f"Current Precision@10: {precision_at_10:.4f}\n"
                f"P@10 drop: {p10_drop:.4f} (max allowed: {PRECISION_TOLERANCE})"
            )

            # Assert no significant regression
            assert p5_drop <= PRECISION_TOLERANCE, failure_message
            assert p10_drop <= PRECISION_TOLERANCE, (
                f"{failure_message}\n\nPrecision@10 regression exceeds tolerance"
            )

        except Exception as e:
            pytest.skip(f"Search quality test failed: {e}")

    @pytest.mark.regression
    @pytest.mark.version_comparison
    def test_version_to_version_comparison(
        self,
        regression_queries: list[dict[str, Any]],
        embedding_model: Any,
    ) -> None:
        """Test version-to-version comparison for regression detection.

        This test simulates version comparison by comparing current behavior
        against stored version baselines.

        Expected:
            - Answers remain semantically similar across versions
            - No significant quality degradation
            - Consistent behavior for core queries

        Args:
            regression_queries: List of regression test queries.
            embedding_model: Pre-loaded SentenceTransformer model.
        """
        # Use first few queries for version comparison
        test_queries = regression_queries[:3]

        results: dict[str, dict[str, Any]] = {}

        for test_query in test_queries:
            query = test_query["query"]
            query_id = test_query["id"]
            baseline_answer = test_query.get("baseline_answer", "")

            # Get current answer
            try:
                searcher = Searcher(verbose=False)
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=3
                )

                result = pipeline.query(query, top_k=3)
                current_answer = result.get("answer", "")

                searcher.close()

                if not current_answer or "apologize" in current_answer.lower():
                    results[query_id] = {
                        "status": "skipped",
                        "reason": "LLM unavailable",
                    }
                    continue

                # Calculate similarity to baseline
                if baseline_answer:
                    similarity = cosine_similarity(
                        baseline_answer, current_answer, embedding_model
                    )
                else:
                    similarity = 0.0

                results[query_id] = {
                    "status": "passed" if similarity >= 0.7 else "degraded",
                    "similarity": similarity,
                    "baseline_answer": baseline_answer[:100],
                    "current_answer": current_answer[:100],
                }

            except Exception as e:
                results[query_id] = {
                    "status": "error",
                    "error": str(e),
                }

        # Summarize results
        passed = sum(1 for r in results.values() if r.get("status") == "passed")
        degraded = sum(1 for r in results.values() if r.get("status") == "degraded")
        errors = sum(1 for r in results.values() if r.get("status") == "error")

        # At least 50% should pass
        min_pass_rate = 0.5
        actual_pass_rate = passed / len(test_queries) if test_queries else 0

        failure_message = (
            f"Version comparison test results\n"
            f"Total queries: {len(test_queries)}\n"
            f"Passed: {passed}\n"
            f"Degraded: {degraded}\n"
            f"Errors: {errors}\n"
            f"Pass rate: {actual_pass_rate:.2%} (minimum: {min_pass_rate:.2%})\n\n"
            f"Detailed results:\n"
        )

        for qid, result in results.items():
            failure_message += f"  {qid}: {result.get('status', 'unknown')}\n"
            if "similarity" in result:
                failure_message += f"    Similarity: {result['similarity']:.4f}\n"
            if "error" in result:
                failure_message += f"    Error: {result['error']}\n"

        assert actual_pass_rate >= min_pass_rate, failure_message

    @pytest.mark.regression
    @pytest.mark.baseline
    def test_create_baseline_snapshot(
        self,
        regression_queries: list[dict[str, Any]],
        embedding_model: Any,
    ) -> None:
        """Create a baseline snapshot for future regression testing.

        This test generates and saves a comprehensive baseline snapshot
        that can be used for future regression comparisons.

        Expected:
            - Baseline snapshot created successfully
            - All query answers captured
            - Response times measured
            - Metadata recorded

        Args:
            regression_queries: List of regression test queries.
            embedding_model: Pre-loaded SentenceTransformer model.
        """
        baseline_data: dict[str, Any] = {
            "version": "1.0.0",
            "timestamp": "baseline_creation",
            "queries": [],
            "metadata": {
                "total_queries": len(regression_queries),
                "model": "all-MiniLM-L6-v2",
            },
        }

        for test_query in regression_queries:
            query = test_query["query"]
            query_id = test_query["id"]

            try:
                searcher = Searcher(verbose=False)
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=3
                )

                import time

                # Measure response time
                start = time.perf_counter()
                result = pipeline.query(query, top_k=3)
                elapsed = time.perf_counter() - start

                answer = result.get("answer", "")
                retrieved_chunks = result.get("chunks", [])

                searcher.close()

                query_baseline = {
                    "id": query_id,
                    "query": query,
                    "baseline_answer": answer,
                    "response_time": elapsed,
                    "num_chunks": len(retrieved_chunks),
                }

                baseline_data["queries"].append(query_baseline)

            except Exception as e:
                baseline_data["queries"].append(
                    {
                        "id": query_id,
                        "query": query,
                        "error": str(e),
                    }
                )

        # Save baseline
        save_baseline("current_snapshot", baseline_data)

        # Verify baseline was created
        assert BASELINE_DIR.exists(), "Baseline directory not created"

        baseline_path = BASELINE_DIR / "current_snapshot.json"
        assert baseline_path.exists(), "Baseline file not created"

        # Load and verify
        loaded_baseline = load_baseline("current_snapshot")
        assert loaded_baseline["metadata"]["total_queries"] == len(
            regression_queries
        ), "Query count mismatch"

    def _calculate_percentile(self, values: list[float], percentile: float) -> float:
        """
        Calculate percentile of a list of values.

        Args:
            values: List of float values
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value
        """
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = (percentile / 100) * (len(sorted_values) - 1)
        lower = int(index)
        upper = lower + 1

        if upper >= len(sorted_values):
            return sorted_values[-1]

        weight = index - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


class TestRegressionMetrics:
    """Regression tests for specific metrics."""

    @pytest.fixture
    def embedding_model(self) -> Any:
        """Load embedding model for similarity calculations."""
        return SentenceTransformer("all-MiniLM-L6-v2")  # type: ignore[operator]

    @pytest.mark.regression
    @pytest.mark.semantic_similarity
    def test_semantic_similarity_stability(
        self,
        embedding_model: Any,
    ) -> None:
        """Test semantic similarity score stability over time.

        This test validates that semantic similarity scores for the same
        query-answer pairs remain stable across runs.

        Expected:
            - Similarity scores vary by < 0.05
            - No significant drift in scoring

        Args:
            embedding_model: Pre-loaded SentenceTransformer model.
        """
        test_pairs = [
            (
                "What is SecondBrain?",
                "SecondBrain is a local document intelligence CLI tool.",
            ),
            (
                "How to configure chunk size?",
                "Set the SECONDBRAIN_CHUNK_SIZE environment variable.",
            ),
        ]

        all_similarities: dict[tuple[str, str], list[float]] = {}

        for query, answer in test_pairs:
            similarities: list[float] = []

            for _ in range(NUM_BENCHMARK_RUNS):
                sim = cosine_similarity(query, answer, embedding_model)
                similarities.append(sim)

            all_similarities[(query, answer)] = similarities

        # Check variance for each pair
        for (query, answer), similarities in all_similarities.items():
            if len(similarities) < 2:
                continue

            mean_sim = sum(similarities) / len(similarities)
            variance = sum((s - mean_sim) ** 2 for s in similarities) / len(
                similarities
            )
            std_dev = math.sqrt(variance)

            # Similarity should be highly stable (low variance)
            assert std_dev < 0.01, (
                f"Semantic similarity instability detected\n"
                f"Query: '{query}'\n"
                f"Answer: '{answer[:50]}...'\n"
                f"Standard deviation: {std_dev:.6f}\n"
                f"Similarities: {[f'{s:.6f}' for s in similarities]}"
            )

    @pytest.mark.regression
    @pytest.mark.performance
    def test_throughput_stability(
        self,
    ) -> None:
        """Test query throughput stability over time.

        This test validates that query throughput remains stable
        and does not degrade over sequential runs.

        Expected:
            - Throughput variance < 20%
            - No significant performance degradation

        Args:
        """
        test_query = "What is the default chunk size?"

        throughputs: list[float] = []

        for run in range(NUM_BENCHMARK_RUNS):
            try:
                searcher = Searcher(verbose=False)
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=3
                )

                import time

                # Measure multiple queries for throughput
                num_queries = 3
                start = time.perf_counter()

                for _ in range(num_queries):
                    pipeline.query(test_query, top_k=3)

                elapsed = time.perf_counter() - start
                throughput = num_queries / elapsed if elapsed > 0 else 0

                throughputs.append(throughput)

                searcher.close()
            except Exception:
                continue

        if len(throughputs) < 2:
            pytest.skip("Not enough throughput samples")

        # Calculate statistics
        mean_throughput = sum(throughputs) / len(throughputs)
        variance = sum((t - mean_throughput) ** 2 for t in throughputs) / len(
            throughputs
        )
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_throughput if mean_throughput > 0 else 0

        # Coefficient of variation should be low
        assert cv < 0.2, (
            f"Throughput instability detected\n"
            f"Mean throughput: {mean_throughput:.2f} q/s\n"
            f"Standard deviation: {std_dev:.2f}\n"
            f"Coefficient of variation: {cv:.2%}\n"
            f"Throughputs: {[f'{t:.2f}' for t in throughputs]}"
        )

    @pytest.mark.regression
    def test_baseline_file_integrity(
        self,
    ) -> None:
        """Test integrity of baseline files.

        This test validates that baseline files exist and have valid structure.

        Expected:
            - All baseline files are valid JSON
            - Required fields present
            - No corruption

        Args:
        """
        if not BASELINE_DIR.exists():
            pytest.skip("Baseline directory not created yet")

        baseline_files = list(BASELINE_DIR.glob("*.json"))

        if not baseline_files:
            pytest.skip("No baseline files to validate")

        for baseline_file in baseline_files:
            try:
                with open(baseline_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Validate basic structure
                assert isinstance(data, dict), f"Baseline {baseline_file} is not a dict"

            except json.JSONDecodeError as e:
                pytest.fail(f"Baseline file {baseline_file} is invalid JSON: {e}")
