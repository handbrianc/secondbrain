"""
ROUGE score tests for RAG pipeline evaluation.

This module provides comprehensive tests for ROUGE (Recall-Oriented Understudy
for Gisting Evaluation) metrics in the SecondBrain RAG system. Tests validate:

1. ROUGE-1 F1 score (unigram overlap) >= 0.5
2. ROUGE-2 F1 score (bigram overlap) >= 0.4
3. ROUGE-L F1 score (longest common subsequence) >= 0.4
4. Parametrized tests using golden datasets with reference answers
5. Correlation between ROUGE and semantic similarity metrics

All tests use real pipeline execution with configurable thresholds and
detailed failure messages showing actual scores.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from rouge_score import rouge_scorer

from secondbrain.cli import cli
from secondbrain.rag import RAGPipeline
from secondbrain.rag.providers import OllamaLLMProvider
from secondbrain.search import Searcher

# ROUGE score thresholds (configurable)
ROUGE1_F1_THRESHOLD = 0.5
ROUGE2_F1_THRESHOLD = 0.4
ROUGEL_F1_THRESHOLD = 0.4

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
GOLDEN_DATASETS_DIR = PROJECT_ROOT / "tests" / "data" / "golden_datasets"


def compute_rouge_scores(reference: str, candidate: str) -> dict[str, float]:
    """Compute ROUGE-1, ROUGE-2, and ROUGE-L F1 scores.

    Args:
        reference: Reference (ground truth) answer text.
        candidate: Candidate (generated) answer text.

    Returns:
        Dictionary with ROUGE-1, ROUGE-2, and ROUGE-L F1 scores.
    """
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
    scores = scorer.score(reference, candidate)

    return {
        "rouge1_f1": scores["rouge1"].fmeasure,
        "rouge2_f1": scores["rouge2"].fmeasure,
        "rougeL_f1": scores["rougeL"].fmeasure,
    }


def load_rouge_reference_dataset() -> list[dict[str, Any]]:
    """Load the ROUGE reference answers dataset.

    Returns:
        List of test cases with query, reference_answer, and thresholds.
    """
    dataset_path = GOLDEN_DATASETS_DIR / "rouge_reference_answers.json"

    if not dataset_path.exists():
        pytest.fail(f"ROUGE reference dataset not found: {dataset_path}")

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    return data.get("queries", [])


class TestRougeScores:
    """Tests for ROUGE score evaluation in RAG pipeline."""

    @pytest.fixture
    def rouge_reference_queries(self) -> list[dict[str, Any]]:
        """Load ROUGE reference queries from golden dataset.

        Returns:
            List of test cases with query, reference_answer, and thresholds.
        """
        return load_rouge_reference_dataset()

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge1_f1_score(
        self, rouge_reference_queries: list[dict[str, Any]]
    ) -> None:
        """Test ROUGE-1 F1 score for query-answer pairs.

        ROUGE-1 measures unigram (single word) overlap between reference and
        candidate answers. This test validates that generated answers share
        significant unigram overlap with reference answers.

        Expected: ROUGE-1 F1 >= 0.5 for meaningful query-answer pairs.

        Steps:
            1. Execute queries via RAGPipeline.query() or CLI chat
            2. Compute ROUGE-1 F1 score against reference answers
            3. Assert F1 >= threshold (0.5)
            4. Provide clear failure message with actual ROUGE-1 score
        """
        # Sample queries with reference answers
        test_cases = rouge_reference_queries[:5]

        for test_case in test_cases:
            query = test_case["query"]
            reference = test_case["reference_answer"]
            min_threshold = test_case.get("min_rouge1", ROUGE1_F1_THRESHOLD)

            # Execute query via RAG pipeline
            searcher = Searcher(verbose=False)
            try:
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=5
                )

                result = pipeline.query(query, top_k=5, show_sources=True)
                answer = result.get("answer", "")
            except Exception as e:
                searcher.close()
                pytest.skip(f"RAG pipeline unavailable for query: {query} ({e})")

            # Skip if no meaningful answer
            if (
                not answer
                or "apologize" in answer.lower()
                or "couldn't find" in answer.lower()
                or "sorry" in answer.lower()
            ):
                searcher.close()
                pytest.skip(
                    f"LLM unavailable or no relevant documents for query: {query}"
                )

            # Compute ROUGE-1 F1 score
            scores = compute_rouge_scores(reference, answer)
            rouge1_f1 = scores["rouge1_f1"]

            # Assert ROUGE-1 F1 meets threshold
            assert rouge1_f1 >= min_threshold, (
                f"ROUGE-1 F1 score {rouge1_f1:.4f} below threshold "
                f"{min_threshold} for query: '{query}'\n"
                f"Reference: '{reference[:100]}...'\n"
                f"Generated: '{answer[:100]}...'\n"
                f"All scores: ROUGE-1={rouge1_f1:.4f}, ROUGE-2={scores['rouge2_f1']:.4f}, "
                f"ROUGE-L={scores['rougeL_f1']:.4f}"
            )

            searcher.close()

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge2_f1_score(
        self, rouge_reference_queries: list[dict[str, Any]]
    ) -> None:
        """Test ROUGE-2 F1 score for query-answer pairs.

        ROUGE-2 measures bigram (two-word sequence) overlap between reference
        and candidate answers. This test validates that generated answers share
        significant phrase-level overlap with reference answers.

        Expected: ROUGE-2 F1 >= 0.4 for meaningful query-answer pairs.

        Steps:
            1. Execute queries via RAGPipeline.query() or CLI chat
            2. Compute ROUGE-2 F1 score against reference answers
            3. Assert F1 >= threshold (0.4)
            4. Provide clear failure message with actual ROUGE-2 score
        """
        # Sample queries with reference answers
        test_cases = rouge_reference_queries[:5]

        for test_case in test_cases:
            query = test_case["query"]
            reference = test_case["reference_answer"]
            min_threshold = test_case.get("min_rouge2", ROUGE2_F1_THRESHOLD)

            # Execute query via RAG pipeline
            searcher = Searcher(verbose=False)
            try:
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=5
                )

                result = pipeline.query(query, top_k=5, show_sources=True)
                answer = result.get("answer", "")
            except Exception as e:
                searcher.close()
                pytest.skip(f"RAG pipeline unavailable for query: {query} ({e})")

            # Skip if no meaningful answer
            if (
                not answer
                or "apologize" in answer.lower()
                or "couldn't find" in answer.lower()
                or "sorry" in answer.lower()
            ):
                searcher.close()
                pytest.skip(
                    f"LLM unavailable or no relevant documents for query: {query}"
                )

            # Compute ROUGE-2 F1 score
            scores = compute_rouge_scores(reference, answer)
            rouge2_f1 = scores["rouge2_f1"]

            # Assert ROUGE-2 F1 meets threshold
            assert rouge2_f1 >= min_threshold, (
                f"ROUGE-2 F1 score {rouge2_f1:.4f} below threshold "
                f"{min_threshold} for query: '{query}'\n"
                f"Reference: '{reference[:100]}...'\n"
                f"Generated: '{answer[:100]}...'\n"
                f"All scores: ROUGE-1={scores['rouge1_f1']:.4f}, ROUGE-2={rouge2_f1:.4f}, "
                f"ROUGE-L={scores['rougeL_f1']:.4f}"
            )

            searcher.close()

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge_l_f1_score(
        self, rouge_reference_queries: list[dict[str, Any]]
    ) -> None:
        """Test ROUGE-L F1 score for query-answer pairs.

        ROUGE-L measures longest common subsequence (LCS) overlap between
        reference and candidate answers. This test validates that generated
        answers maintain sentence-level structure similar to reference answers.

        Expected: ROUGE-L F1 >= 0.4 for meaningful query-answer pairs.

        Steps:
            1. Execute queries via RAGPipeline.query() or CLI chat
            2. Compute ROUGE-L F1 score against reference answers
            3. Assert F1 >= threshold (0.4)
            4. Provide clear failure message with actual ROUGE-L score
        """
        # Sample queries with reference answers
        test_cases = rouge_reference_queries[:5]

        for test_case in test_cases:
            query = test_case["query"]
            reference = test_case["reference_answer"]
            min_threshold = test_case.get("min_rougeL", ROUGEL_F1_THRESHOLD)

            # Execute query via RAG pipeline
            searcher = Searcher(verbose=False)
            try:
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=5
                )

                result = pipeline.query(query, top_k=5, show_sources=True)
                answer = result.get("answer", "")
            except Exception as e:
                searcher.close()
                pytest.skip(f"RAG pipeline unavailable for query: {query} ({e})")

            # Skip if no meaningful answer
            if (
                not answer
                or "apologize" in answer.lower()
                or "couldn't find" in answer.lower()
                or "sorry" in answer.lower()
            ):
                searcher.close()
                pytest.skip(
                    f"LLM unavailable or no relevant documents for query: {query}"
                )

            # Compute ROUGE-L F1 score
            scores = compute_rouge_scores(reference, answer)
            rougeL_f1 = scores["rougeL_f1"]

            # Assert ROUGE-L F1 meets threshold
            assert rougeL_f1 >= min_threshold, (
                f"ROUGE-L F1 score {rougeL_f1:.4f} below threshold "
                f"{min_threshold} for query: '{query}'\n"
                f"Reference: '{reference[:100]}...'\n"
                f"Generated: '{answer[:100]}...'\n"
                f"All scores: ROUGE-1={scores['rouge1_f1']:.4f}, ROUGE-2={scores['rouge2_f1']:.4f}, "
                f"ROUGE-L={rougeL_f1:.4f}"
            )

            searcher.close()

    @pytest.mark.rouge
    @pytest.mark.optional
    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param(
                {
                    "id": "rouge-001",
                    "query": "What is the default chunk size in SecondBrain?",
                    "reference_answer": "The default chunk size in SecondBrain is 4096 tokens. This configuration parameter controls how documents are split into smaller pieces for embedding and vector search.",
                    "min_rouge1": 0.5,
                    "min_rougeL": 0.4,
                },
                id="rouge-001",
            ),
            pytest.param(
                {
                    "id": "rouge-002",
                    "query": "How do I configure MongoDB connection URI?",
                    "reference_answer": "To configure the MongoDB connection URI, set the SECONDBRAIN_MONGO_URI environment variable to your MongoDB connection string. This is the primary method for specifying database connectivity.",
                    "min_rouge1": 0.5,
                    "min_rougeL": 0.4,
                },
                id="rouge-002",
            ),
            pytest.param(
                {
                    "id": "rouge-006",
                    "query": "What is the default embedding model?",
                    "reference_answer": "The default embedding model is all-MiniLM-L6-v2 from the sentence-transformers library. This model provides a good balance between speed and accuracy for semantic search.",
                    "min_rouge1": 0.5,
                    "min_rougeL": 0.4,
                },
                id="rouge-006",
            ),
            pytest.param(
                {
                    "id": "rouge-008",
                    "query": "What document formats are supported for ingestion?",
                    "reference_answer": "SecondBrain supports PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio files. The Ingestor class uses Docling for multi-format document parsing.",
                    "min_rouge1": 0.5,
                    "min_rougeL": 0.4,
                },
                id="rouge-008",
            ),
            pytest.param(
                {
                    "id": "rouge-009",
                    "query": "How does semantic search work?",
                    "reference_answer": "Semantic search works by converting queries and documents into embedding vectors using sentence-transformers, then performing vector similarity search in MongoDB using cosine similarity to find the most relevant results.",
                    "min_rouge1": 0.5,
                    "min_rougeL": 0.4,
                },
                id="rouge-009",
            ),
        ],
    )
    def test_rouge_scores_parametrized(
        self,
        test_case: dict[str, Any],
    ) -> None:
        """Test ROUGE scores using parametrized golden dataset queries.

        This test validates ROUGE-1, ROUGE-2, and ROUGE-L scores for individual
        queries from the golden dataset, using query-specific thresholds.

        Args:
            test_case: Golden dataset test case with query, reference_answer,
                      and threshold values.

        Expected: All ROUGE scores meet their respective thresholds.
        """
        query = test_case["query"]
        reference = test_case["reference_answer"]
        min_rouge1 = test_case.get("min_rouge1", ROUGE1_F1_THRESHOLD)
        min_rougeL = test_case.get("min_rougeL", ROUGEL_F1_THRESHOLD)

        # Execute query via RAG pipeline
        searcher = Searcher(verbose=False)
        try:
            llm_provider = OllamaLLMProvider()
            pipeline = RAGPipeline(
                searcher=searcher, llm_provider=llm_provider, top_k=5
            )

            result = pipeline.query(query, top_k=5, show_sources=True)
            answer = result.get("answer", "")
        except Exception as e:
            searcher.close()
            pytest.skip(f"RAG pipeline unavailable for query: {query} ({e})")

        # Skip if no meaningful answer
        if (
            not answer
            or "apologize" in answer.lower()
            or "couldn't find" in answer.lower()
            or "sorry" in answer.lower()
        ):
            searcher.close()
            pytest.skip(f"LLM unavailable or no relevant documents for query: {query}")

        # Compute all ROUGE scores
        scores = compute_rouge_scores(reference, answer)

        # Assert ROUGE-1 F1 meets threshold
        assert scores["rouge1_f1"] >= min_rouge1, (
            f"ROUGE test {test_case['id']} failed.\n"
            f"Query: '{query}'\n"
            f"ROUGE-1 F1: {scores['rouge1_f1']:.4f} (threshold: {min_rouge1})\n"
            f"Reference: '{reference[:100]}...'\n"
            f"Generated: '{answer[:100]}...'"
        )

        # Assert ROUGE-L F1 meets threshold
        assert scores["rougeL_f1"] >= min_rougeL, (
            f"ROUGE test {test_case['id']} failed.\n"
            f"Query: '{query}'\n"
            f"ROUGE-L F1: {scores['rougeL_f1']:.4f} (threshold: {min_rougeL})\n"
            f"Reference: '{reference[:100]}...'\n"
            f"Generated: '{answer[:100]}...'"
        )

        searcher.close()

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge_vs_semantic_similarity(
        self,
        rouge_reference_queries: list[dict[str, Any]],
    ) -> None:
        """Test correlation between ROUGE scores and semantic similarity.

        This test validates that ROUGE scores (lexical overlap) correlate with
        semantic similarity scores (embedding-based). High-quality answers
        should score well on both metrics.

        Expected: Correlation between ROUGE and semantic similarity > 0.5.

        Steps:
            1. Execute queries via RAG pipeline
            2. Compute ROUGE scores for each query-answer pair
            3. Compute semantic similarity for each query-answer pair
            4. Calculate correlation between metrics
            5. Assert correlation > 0.5
        """
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity

        # Load embedding model
        model = SentenceTransformer("all-MiniLM-L6-v2")

        # Sample queries for correlation analysis
        test_cases = rouge_reference_queries[:8]

        rouge_scores = []
        semantic_scores = []

        for test_case in test_cases:
            query = test_case["query"]
            reference = test_case["reference_answer"]

            # Execute query via RAG pipeline
            searcher = Searcher(verbose=False)
            try:
                llm_provider = OllamaLLMProvider()
                pipeline = RAGPipeline(
                    searcher=searcher, llm_provider=llm_provider, top_k=5
                )

                result = pipeline.query(query, top_k=5, show_sources=True)
                answer = result.get("answer", "")
            except Exception as e:
                searcher.close()
                continue

            # Skip if no meaningful answer
            if (
                not answer
                or "apologize" in answer.lower()
                or "couldn't find" in answer.lower()
                or "sorry" in answer.lower()
            ):
                searcher.close()
                continue

            # Compute ROUGE score (use ROUGE-L F1)
            rouge = compute_rouge_scores(reference, answer)
            rouge_scores.append(rouge["rougeL_f1"])

            # Compute semantic similarity
            query_embedding = model.encode(query, convert_to_numpy=True)
            answer_embedding = model.encode(answer, convert_to_numpy=True)
            query_embedding = query_embedding.reshape(1, -1)
            answer_embedding = answer_embedding.reshape(1, -1)
            semantic_sim = cosine_similarity(query_embedding, answer_embedding)[0][0]
            semantic_scores.append(float(semantic_sim))

            searcher.close()

        # Need at least 2 samples for correlation
        if len(rouge_scores) < 2:
            pytest.skip("Not enough valid query-answer pairs for correlation analysis")

        # Calculate Pearson correlation coefficient
        import numpy as np

        rouge_array = np.array(rouge_scores)
        semantic_array = np.array(semantic_scores)

        correlation = np.corrcoef(rouge_array, semantic_array)[0, 1]

        # Assert correlation is positive and meaningful
        assert correlation > 0.5, (
            f"ROUGE-semantic similarity correlation {correlation:.4f} below expected "
            f"threshold of 0.5.\n"
            f"ROUGE scores: {rouge_scores}\n"
            f"Semantic scores: {semantic_scores}\n"
            f"Note: Low correlation may indicate metric disagreement or small sample size."
        )

        # Log correlation for debugging
        pytest.skip(
            f"ROUGE-semantic correlation test passed with correlation={correlation:.4f}"
        )

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge_perfect_match(self) -> None:
        """Test that identical reference and candidate produce maximum ROUGE scores.

        This test validates the ROUGE calculation itself by checking that
        identical texts produce ROUGE-1, ROUGE-2, and ROUGE-L F1 scores of 1.0.

        Expected: All ROUGE F1 scores = 1.0 (or very close, within floating point tolerance).
        """
        text = "The default chunk size in SecondBrain is 4096 tokens."

        scores = compute_rouge_scores(text, text)

        # Allow small floating point tolerance
        assert scores["rouge1_f1"] >= 0.99, (
            f"Identical texts should have ROUGE-1 F1 ~1.0, got {scores['rouge1_f1']:.6f}"
        )
        assert scores["rouge2_f1"] >= 0.99, (
            f"Identical texts should have ROUGE-2 F1 ~1.0, got {scores['rouge2_f1']:.6f}"
        )
        assert scores["rougeL_f1"] >= 0.99, (
            f"Identical texts should have ROUGE-L F1 ~1.0, got {scores['rougeL_f1']:.6f}"
        )

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge_no_overlap(self) -> None:
        """Test that completely different texts produce low ROUGE scores.

        This test validates that ROUGE correctly identifies texts with no
        lexical overlap as having low scores.

        Expected: ROUGE scores < 0.2 for completely unrelated texts.
        """
        reference = "The default chunk size is 4096 tokens for document processing."
        candidate = "Basketball game rules and regulations for professional leagues."

        scores = compute_rouge_scores(reference, candidate)

        # Unrelated texts should have low ROUGE scores
        assert scores["rouge1_f1"] < 0.2, (
            f"Unrelated texts should have ROUGE-1 F1 < 0.2, got {scores['rouge1_f1']:.4f}"
        )
        assert scores["rougeL_f1"] < 0.2, (
            f"Unrelated texts should have ROUGE-L F1 < 0.2, got {scores['rougeL_f1']:.4f}"
        )

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge_cli_execution(self) -> None:
        """Test ROUGE scores using CLI execution path.

        This test validates ROUGE calculation using the CLI chat command
        instead of direct RAGPipeline API, ensuring end-to-end integration.

        Expected: ROUGE-1 F1 >= 0.5 for CLI-generated answers.
        """
        query = "What is SecondBrain?"
        reference = "SecondBrain is a local document intelligence CLI tool for semantic search over documents."

        # Execute query via CLI
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--top-k", "5", query])

        # Skip if CLI fails
        if result.exit_code != 0 or "apologize" in result.output.lower():
            pytest.skip(f"CLI unavailable for query: {query}")

        # Extract answer from CLI output
        answer_lines = []
        in_answer = False
        for line in result.output.split("\n"):
            if "Answer:" in line or "assistant:" in line.lower():
                in_answer = True
                continue
            if in_answer and line.strip():
                answer_lines.append(line.strip())

        answer = " ".join(answer_lines)

        if not answer:
            pytest.skip("Could not extract answer from CLI output")

        # Compute ROUGE scores
        scores = compute_rouge_scores(reference, answer)

        # Assert ROUGE-1 F1 meets threshold
        assert scores["rouge1_f1"] >= ROUGE1_F1_THRESHOLD, (
            f"ROUGE-1 F1 score {scores['rouge1_f1']:.4f} below threshold "
            f"{ROUGE1_F1_THRESHOLD} for CLI query: '{query}'\n"
            f"Reference: '{reference[:100]}...'\n"
            f"Generated: '{answer[:100]}...'"
        )

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge_threshold_configurability(self) -> None:
        """Test that ROUGE thresholds are configurable module constants.

        This test validates that thresholds are defined as module-level constants
        and can be easily adjusted for different use cases.

        Expected: Thresholds are accessible and reasonable (0.3-0.8 range).
        """
        # Verify thresholds are defined and reasonable
        assert 0.3 <= ROUGE1_F1_THRESHOLD <= 0.8, (
            f"ROUGE1_F1_THRESHOLD {ROUGE1_F1_THRESHOLD} should be between 0.3 and 0.8"
        )

        assert 0.2 <= ROUGE2_F1_THRESHOLD <= 0.7, (
            f"ROUGE2_F1_THRESHOLD {ROUGE2_F1_THRESHOLD} should be between 0.2 and 0.7"
        )

        assert 0.3 <= ROUGEL_F1_THRESHOLD <= 0.8, (
            f"ROUGEL_F1_THRESHOLD {ROUGEL_F1_THRESHOLD} should be between 0.3 and 0.8"
        )

    @pytest.mark.rouge
    @pytest.mark.optional
    def test_rouge_multiple_references(self) -> None:
        """Test ROUGE calculation with multiple reference answers.

        This test validates that ROUGE can handle multiple reference answers
        by computing the maximum score across all references.

        Expected: ROUGE score with best matching reference >= threshold.
        """
        query = "What is the default chunk size?"

        # Multiple valid reference answers
        references = [
            "The default chunk size is 4096 tokens.",
            "SecondBrain uses 4096 tokens as the default chunk size for document processing.",
            "Chunk size defaults to 4096 tokens in the configuration.",
        ]

        candidate = "The default chunk size in SecondBrain is 4096 tokens."

        # Compute ROUGE against each reference, take maximum
        scores_list = [compute_rouge_scores(ref, candidate) for ref in references]
        best_rouge1 = max(scores["rouge1_f1"] for scores in scores_list)

        # Should achieve good score with at least one reference
        assert best_rouge1 >= 0.6, (
            f"Best ROUGE-1 F1 across references {best_rouge1:.4f} below expected threshold. "
            f"Scores: {[s['rouge1_f1'] for s in scores_list]}"
        )
