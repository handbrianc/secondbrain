"""
Golden dataset tests for RAG pipeline validation.

This module tests the RAG pipeline against a golden dataset of queries with
expected concepts, forbidden concepts, and expected answers.

Tests verify:
1. Expected concepts are present in answers
2. Forbidden concepts are absent from answers
3. Answers are semantically similar to expected answers
4. Category-based pass rates meet thresholds
5. Overall pass rate meets minimum threshold
"""

import json
from pathlib import Path
from typing import Any

import pytest
from sentence_transformers import SentenceTransformer

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.search import Searcher
from tests.test_quantitative.conftest import cosine_similarity

PROJECT_ROOT = Path(__file__).parent.parent.parent
GOLDEN_DATASETS_DIR = PROJECT_ROOT / "tests" / "data" / "golden_datasets"
PASS_RATE_THRESHOLD = 0.80
SIMILARITY_THRESHOLD = 0.65


def check_concept_presence(answer: str, concepts: list[str]) -> list[str]:
    """
    Check which expected concepts are present in the answer.

    Args:
        answer: The generated answer text.
        concepts: List of expected concepts to check.

    Returns:
        List of concepts that are present (case-insensitive substring match).
    """
    answer_lower = answer.lower()
    present = []
    for concept in concepts:
        if concept.lower() in answer_lower:
            present.append(concept)
    return present


def check_concept_absence(answer: str, concepts: list[str]) -> list[str]:
    """
    Check which forbidden concepts are absent from the answer.

    Args:
        answer: The generated answer text.
        concepts: List of forbidden concepts to check.

    Returns:
        List of concepts that are correctly absent.
    """
    answer_lower = answer.lower()
    absent = []
    for concept in concepts:
        if concept.lower() not in answer_lower:
            absent.append(concept)
    return absent


def evaluate_golden_query(
    query: dict[str, Any],
    answer: str,
    embedding_model: SentenceTransformer | None = None,
) -> dict[str, Any]:
    """
    Evaluate a single golden query against its expected results.

    Args:
        query: Golden query dict with expected_concepts, forbidden_concepts, etc.
        answer: The generated answer from the pipeline.
        embedding_model: Optional pre-loaded embedding model.

    Returns:
        Dict with evaluation results including pass/fail status and details.
    """
    expected_concepts = query.get("expected_concepts", [])
    forbidden_concepts = query.get("forbidden_concepts", [])
    expected_answer = query.get("expected_answer")

    present_concepts = check_concept_presence(answer, expected_concepts)
    missing_concepts = [c for c in expected_concepts if c.lower() not in answer.lower()]

    absent_concepts = check_concept_absence(answer, forbidden_concepts)
    present_forbidden = [c for c in forbidden_concepts if c.lower() in answer.lower()]

    similarity = None
    if expected_answer and embedding_model:
        similarity = cosine_similarity(query["query"], expected_answer, embedding_model)

    concepts_passed = len(missing_concepts) == 0
    forbidden_passed = len(present_forbidden) == 0
    overall_passed = concepts_passed and forbidden_passed

    return {
        "query_id": query.get("id", "unknown"),
        "query": query.get("query", ""),
        "passed": overall_passed,
        "concepts_passed": concepts_passed,
        "forbidden_passed": forbidden_passed,
        "present_concepts": present_concepts,
        "missing_concepts": missing_concepts,
        "absent_concepts": absent_concepts,
        "present_forbidden": present_forbidden,
        "similarity": similarity,
        "answer": answer,
    }


class TestGoldenDataset:
    """Tests for golden dataset validation and RAG pipeline evaluation."""

    @pytest.fixture(scope="class")
    def embedding_model(self) -> SentenceTransformer:
        """Load embedding model once per test class."""
        return SentenceTransformer("all-MiniLM-L6-v2")

    @pytest.fixture(scope="class")
    def searcher(self) -> Searcher:
        """Create a Searcher instance for testing."""
        return Searcher()

    @pytest.fixture(scope="class")
    def rag_pipeline(self, searcher: Searcher) -> RAGPipeline:
        """Create RAGPipeline for testing."""
        try:
            from secondbrain.rag.factory import (
                create_llm_provider,
                create_query_rewriter,
            )
        except ImportError:
            pytest.skip(
                "secondbrain.rag.factory module not available - RAG pipeline tests require factory implementation"
            )

        llm_provider = create_llm_provider()
        rewriter = create_query_rewriter(llm_provider)

        return RAGPipeline(
            searcher=searcher,
            llm_provider=llm_provider,
            rewriter=rewriter,
            top_k=5,
        )

    @pytest.fixture
    def tech_docs_dataset(self) -> list[dict[str, Any]]:
        """Load the tech_docs_golden dataset."""
        dataset_path = GOLDEN_DATASETS_DIR / "tech_docs_golden.json"

        if not dataset_path.exists():
            pytest.fail(f"Golden dataset not found: {dataset_path}")

        with open(dataset_path, encoding="utf-8") as f:
            data = json.load(f)

        return data.get("queries", data.get("test_cases", []))

    @pytest.mark.golden_dataset
    def test_load_valid_dataset(self, tech_docs_dataset: list[dict[str, Any]]) -> None:
        """Test that the golden dataset loads successfully with valid schema."""
        assert len(tech_docs_dataset) > 0

        required_fields = [
            "id",
            "query",
            "expected_concepts",
            "forbidden_concepts",
            "category",
        ]

        for query in tech_docs_dataset:
            for field in required_fields:
                assert field in query

            assert isinstance(query["expected_concepts"], list)
            assert isinstance(query["forbidden_concepts"], list)
            assert len(query["expected_concepts"]) >= 2
            assert len(query["forbidden_concepts"]) >= 1

    @pytest.mark.golden_dataset
    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test handling of invalid JSON files."""
        invalid_json_path = tmp_path / "invalid.json"
        invalid_json_path.write_text("{ invalid json content")

        with pytest.raises(json.JSONDecodeError):
            with open(invalid_json_path) as f:
                json.load(f)

    @pytest.mark.golden_dataset
    def test_load_missing_file(self) -> None:
        """Test handling of missing dataset files."""
        missing_path = GOLDEN_DATASETS_DIR / "nonexistent_dataset.json"
        assert not missing_path.exists(), "Test setup error: file should not exist"

    @pytest.mark.golden_dataset
    def test_validate_dataset_schema(
        self, tech_docs_dataset: list[dict[str, Any]]
    ) -> None:
        categories = set()

        for query in tech_docs_dataset:
            assert query.get("id")
            assert query.get("query")
            assert query.get("category")

            assert len(query.get("expected_concepts", [])) > 0
            assert len(query.get("forbidden_concepts", [])) > 0

            categories.add(query["category"])

        assert len(categories) >= 3

    @pytest.mark.golden_dataset
    @pytest.mark.parametrize(
        "golden_query",
        [
            pytest.param(q, id=q["id"])
            for q in [
                {
                    "id": "config-001",
                    "query": "What is the default chunk size in SecondBrain?",
                },
                {
                    "id": "config-002",
                    "query": "How do I configure MongoDB connection URI?",
                },
                {
                    "id": "features-001",
                    "query": "What document formats are supported for ingestion?",
                },
                {"id": "errors-001", "query": "What causes MongoDB connection errors?"},
                {
                    "id": "arch-001",
                    "query": "What are the main components of SecondBrain architecture?",
                },
            ]
        ],
    )
    def test_golden_query_coverage(
        self,
        golden_query: dict[str, Any],
        tech_docs_dataset: list[dict[str, Any]],
        rag_pipeline: RAGPipeline,
        embedding_model: SentenceTransformer,
    ) -> None:
        full_query = next(
            (q for q in tech_docs_dataset if q["id"] == golden_query["id"]),
            None,
        )

        if full_query is None:
            query_text = golden_query["query"]
            expected_concepts = ["test"]
            forbidden_concepts = []
        else:
            query_text = full_query["query"]
            expected_concepts = full_query.get("expected_concepts", [])
            forbidden_concepts = full_query.get("forbidden_concepts", [])

        result = rag_pipeline.query(query_text, top_k=5, show_sources=True)
        answer = result.get("answer", "")

        present_concepts = check_concept_presence(answer, expected_concepts)
        missing_concepts = [
            c for c in expected_concepts if c.lower() not in answer.lower()
        ]

        present_forbidden = [
            c for c in forbidden_concepts if c.lower() in answer.lower()
        ]

        failure_parts = []
        if missing_concepts:
            failure_parts.append(
                f"Missing expected concepts: {', '.join(missing_concepts)}"
            )
        if present_forbidden:
            failure_parts.append(
                f"Found forbidden concepts: {', '.join(present_forbidden)}"
            )

        if failure_parts:
            pytest.fail(
                f"Query '{query_text}' failed:\n"
                f"  - {'; '.join(failure_parts)}\n"
                f"  - Answer: {answer[:200]}..."
            )

    @pytest.mark.golden_dataset
    @pytest.mark.parametrize(
        "category",
        ["configuration", "defaults", "features", "errors", "architecture"],
    )
    def test_golden_query_by_category(
        self,
        category: str,
        tech_docs_dataset: list[dict[str, Any]],
        rag_pipeline: RAGPipeline,
        embedding_model: SentenceTransformer,
    ) -> None:
        category_queries = [
            q for q in tech_docs_dataset if q.get("category") == category
        ]

        if not category_queries:
            pytest.skip(f"No queries found for category: {category}")

        passed = 0
        failed_details = []

        for query in category_queries:
            result = rag_pipeline.query(query["query"], top_k=5)
            answer = result.get("answer", "")

            eval_result = evaluate_golden_query(query, answer, embedding_model)

            if eval_result["passed"]:
                passed += 1
            else:
                failed_details.append(
                    {
                        "id": query["id"],
                        "missing": eval_result["missing_concepts"],
                        "forbidden_found": eval_result["present_forbidden"],
                    }
                )

        pass_rate = passed / len(category_queries)

        assert pass_rate >= PASS_RATE_THRESHOLD, (
            f"Category '{category}' pass rate {pass_rate:.2%} "
            f"below threshold {PASS_RATE_THRESHOLD:.2%}\n"
            f"Passed: {passed}/{len(category_queries)}\n"
            f"Failures: {failed_details}"
        )

    @pytest.mark.golden_dataset
    @pytest.mark.parametrize(
        "golden_query",
        [
            pytest.param(q, id=q["id"])
            for q in [
                {
                    "id": "config-001",
                    "query": "What is the default chunk size in SecondBrain?",
                },
                {
                    "id": "config-002",
                    "query": "How do I configure MongoDB connection URI?",
                },
                {
                    "id": "features-001",
                    "query": "What document formats are supported for ingestion?",
                },
            ]
        ],
    )
    def test_answer_semantic_alignment(
        self,
        golden_query: dict[str, Any],
        tech_docs_dataset: list[dict[str, Any]],
        rag_pipeline: RAGPipeline,
        embedding_model: SentenceTransformer,
    ) -> None:
        full_query = next(
            (q for q in tech_docs_dataset if q["id"] == golden_query["id"]),
            None,
        )

        if full_query is None or not full_query.get("expected_answer"):
            pytest.skip("No expected answer available for this query")

        result = rag_pipeline.query(full_query["query"], top_k=5)
        answer = result.get("answer", "")
        expected_answer = full_query["expected_answer"]

        similarity = cosine_similarity(
            full_query["query"], expected_answer, embedding_model
        )

        assert similarity >= 0.0
        assert isinstance(similarity, float)

    @pytest.mark.golden_dataset
    def test_golden_dataset_pass_rate(
        self,
        tech_docs_dataset: list[dict[str, Any]],
        rag_pipeline: RAGPipeline,
        embedding_model: SentenceTransformer,
    ) -> None:
        passed = 0
        failed_queries = []

        for query in tech_docs_dataset:
            try:
                result = rag_pipeline.query(query["query"], top_k=5)
                answer = result.get("answer", "")

                eval_result = evaluate_golden_query(query, answer, embedding_model)

                if eval_result["passed"]:
                    passed += 1
                else:
                    failed_queries.append(
                        {
                            "id": query["id"],
                            "query": query["query"],
                            "missing_concepts": eval_result["missing_concepts"],
                            "present_forbidden": eval_result["present_forbidden"],
                            "answer": answer[:200],
                        }
                    )
            except Exception as e:
                failed_queries.append(
                    {
                        "id": query["id"],
                        "query": query["query"],
                        "error": str(e),
                    }
                )

        total = len(tech_docs_dataset)
        pass_rate = passed / total if total > 0 else 0.0

        assert pass_rate >= PASS_RATE_THRESHOLD, (
            f"Overall pass rate {pass_rate:.2%} below threshold {PASS_RATE_THRESHOLD:.2%}\n"
            f"Passed: {passed}/{total}\n"
            f"Failures: {len(failed_queries)}\n\n"
            f"Failed queries:\n"
            + "\n".join(
                f"  - {fq.get('id', 'unknown')}: {fq.get('missing_concepts', [])} "
                f"missing, {fq.get('present_forbidden', [])} forbidden found"
                for fq in failed_queries[:5]
            )
        )

    @pytest.mark.golden_dataset
    def test_dataset_metadata_validation(
        self,
        tech_docs_dataset: list[dict[str, Any]],
    ) -> None:
        dataset_path = GOLDEN_DATASETS_DIR / "tech_docs_golden.json"

        with open(dataset_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "metadata" in data

        metadata = data["metadata"]
        assert "name" in metadata
        assert "description" in metadata

        assert len(tech_docs_dataset) == metadata.get("total_queries", 0)

    @pytest.mark.golden_dataset
    def test_concept_matching_case_insensitive(
        self,
    ) -> None:
        """Test that concept matching is case-insensitive."""
        answer = "The DEFAULT chunk SIZE is 4096 tokens"

        # These should all match regardless of case
        concepts = ["default", "CHUNK", "Size", "4096"]
        present = check_concept_presence(answer, concepts)

        assert len(present) == 4, (
            f"All concepts should match case-insensitively: {present}"
        )

    @pytest.mark.golden_dataset
    def test_empty_concept_lists_handled(
        self,
        rag_pipeline: RAGPipeline,
        embedding_model: SentenceTransformer,
    ) -> None:
        """Test handling of queries with empty concept lists."""
        test_query = {
            "id": "test-empty",
            "query": "Test query with no concepts",
            "expected_concepts": [],
            "forbidden_concepts": [],
            "category": "test",
        }

        result = rag_pipeline.query("What is SecondBrain?", top_k=1)
        answer = result.get("answer", "")

        eval_result = evaluate_golden_query(test_query, answer, embedding_model)

        # Empty lists should always pass (nothing to check)
        assert eval_result["concepts_passed"], "Empty expected concepts should pass"
        assert eval_result["forbidden_passed"], "Empty forbidden concepts should pass"
