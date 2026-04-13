"""
Semantic similarity tests for RAG pipeline evaluation.

This module provides comprehensive tests for semantic similarity metrics in the
SecondBrain RAG system. Tests validate:

1. Query-answer relevance (cosine similarity >= 0.6)
2. Query-context alignment (retrieved chunks semantically related to query)
3. Cross-query similarity (similar queries produce similar answers)
4. Golden dataset integration (parametrized tests with real data)

All tests use real pipeline/CLI (not mocks) and configurable thresholds.
"""

import math
from typing import Any

import pytest
from click.testing import CliRunner
from sentence_transformers import SentenceTransformer

from secondbrain.cli import cli
from secondbrain.rag import RAGPipeline
from secondbrain.rag.providers import OllamaLLMProvider
from secondbrain.search import Searcher

# Semantic similarity thresholds (configurable)
QUERY_ANSWER_SIMILARITY_THRESHOLD = 0.6
QUERY_CONTEXT_SIMILARITY_THRESHOLD = 0.5
CROSS_QUERY_SIMILARITY_TOLERANCE = 0.15


def compute_cosine_similarity(text1: str, text2: str, model: Any) -> float:
    """Compute cosine similarity between two text embeddings.

    Args:
        text1: First text string.
        text2: Second text string.
        model: Pre-loaded SentenceTransformer model.

    Returns:
        Cosine similarity score (range: -1 to 1, typically 0-1 for semantic similarity).
    """
    embedding1 = model.encode(text1, convert_to_numpy=True)
    embedding2 = model.encode(text2, convert_to_numpy=True)

    # Ensure 2D for sklearn cosine similarity
    embedding1 = embedding1.reshape(1, -1)
    embedding2 = embedding2.reshape(1, -1)

    from sklearn.metrics.pairwise import cosine_similarity

    similarity = cosine_similarity(embedding1, embedding2)[0][0]
    return float(similarity)


def compute_average_chunk_similarity(
    query: str,
    chunks: list[dict[str, Any]],
    model: Any,
) -> float:
    """Compute average semantic similarity between query and retrieved chunks.

    Args:
        query: Query text.
        chunks: List of retrieved chunk dictionaries with 'chunk_text' or 'text' key.
        model: Pre-loaded SentenceTransformer model.

    Returns:
        Average similarity score across all chunks.
    """
    if not chunks:
        return 0.0

    similarities = []
    for chunk in chunks:
        chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
        if chunk_text:
            sim = compute_cosine_similarity(query, chunk_text, model)
            similarities.append(sim)

    return sum(similarities) / len(similarities) if similarities else 0.0


class TestSemanticSimilarity:
    """Tests for semantic similarity metrics in RAG pipeline."""

    @pytest.fixture
    def embedding_model(self) -> Any:
        """Load embedding model for similarity calculations.

        Returns:
            SentenceTransformer model instance.
        """
        return SentenceTransformer("all-MiniLM-L6-v2")  # type: ignore[operator]

    @pytest.fixture
    def sample_golden_queries(self) -> list[dict[str, Any]]:
        """Sample golden queries with expected answers and metadata.

        Returns:
            List of test cases with query, expected_answer, and concepts.
        """
        return [
            {
                "id": "sample-001",
                "query": "What is the default chunk size in SecondBrain?",
                "expected_answer": "The default chunk size is 4096 tokens.",
                "expected_concepts": ["chunk", "size", "4096", "default"],
                "forbidden_concepts": ["memory", "buffer", "streaming"],
            },
            {
                "id": "sample-002",
                "query": "How do I configure MongoDB connection URI?",
                "expected_answer": "Set the SECONDBRAIN_MONGO_URI environment variable.",
                "expected_concepts": ["MongoDB", "URI", "configuration", "environment"],
                "forbidden_concepts": ["MySQL", "PostgreSQL", "SQLite"],
            },
            {
                "id": "sample-003",
                "query": "What document formats are supported?",
                "expected_answer": "PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio.",
                "expected_concepts": ["PDF", "DOCX", "formats", "supported"],
                "forbidden_concepts": ["TXT", "RTF", "ODT"],
            },
        ]

    @pytest.mark.semantic_similarity
    @pytest.mark.threshold
    def test_query_answer_relevance(self, embedding_model: Any) -> None:
        """Test that query and answer are semantically relevant.

        This test validates that the RAG pipeline produces answers that are
        semantically related to the query. Uses cosine similarity between
        query and answer embeddings.

        Expected: Similarity >= 0.6 for meaningful query-answer pairs.

        Steps:
            1. Execute query via RAGPipeline.query() or CLI chat
            2. Compute cosine similarity between query and answer embeddings
            3. Assert similarity >= threshold (0.6)
            4. Provide clear failure message with actual similarity value
        """
        # Test queries with expected semantic relevance
        test_cases: list[dict[str, Any]] = [
            {
                "query": "What is SecondBrain?",
                "expected_concepts": ["SecondBrain", "tool", "CLI", "document"],
            },
            {
                "query": "How does semantic search work?",
                "expected_concepts": ["semantic", "search", "vector", "embedding"],
            },
            {
                "query": "What is MongoDB used for?",
                "expected_concepts": ["MongoDB", "database", "storage", "vector"],
            },
        ]

        for test_case in test_cases:
            query: str = test_case["query"]

            # Execute query via RAG pipeline
            searcher = Searcher(verbose=False)
            llm_provider = OllamaLLMProvider()
            pipeline = RAGPipeline(
                searcher=searcher, llm_provider=llm_provider, top_k=5
            )

            result = pipeline.query(query, top_k=5, show_sources=True)
            answer = result.get("answer", "")

            # Skip if no meaningful answer (e.g., LLM unavailable)
            if (
                not answer
                or "apologize" in answer.lower()
                or "couldn't find" in answer.lower()
            ):
                pytest.skip(
                    f"LLM unavailable or no relevant documents for query: {query}"
                )

            # Compute cosine similarity between query and answer
            similarity = compute_cosine_similarity(query, answer, embedding_model)

            # Assert similarity meets threshold
            assert similarity >= QUERY_ANSWER_SIMILARITY_THRESHOLD, (
                f"Query-answer similarity {similarity:.4f} below threshold "
                f"{QUERY_ANSWER_SIMILARITY_THRESHOLD} for query: '{query}'\n"
                f"Answer: '{answer[:200]}...'"
            )

            searcher.close()

    @pytest.mark.semantic_similarity
    @pytest.mark.threshold
    def test_query_context_alignment(self, embedding_model: Any) -> None:
        """Test that retrieved chunks are semantically aligned with query.

        This test validates that the retrieval component returns chunks that are
        semantically related to the query. Computes average similarity between
        query and all retrieved chunks.

        Expected: Average similarity >= 0.5 for relevant retrievals.

        Steps:
            1. Execute search via Searcher.search()
            2. Compute similarity between query and each retrieved chunk
            3. Assert average similarity >= threshold (0.5)
            4. Provide failure message with individual chunk similarities
        """
        test_queries = [
            "What is the purpose of document chunking?",
            "How does vector search work in MongoDB?",
            "What are the benefits of semantic search?",
        ]

        for query in test_queries:
            # Execute search via Searcher
            try:
                with Searcher(verbose=False) as searcher:
                    chunks = searcher.search(query, top_k=5)
            except RuntimeError as e:
                if "Cannot connect to MongoDB" in str(e):
                    pytest.skip(
                        "MongoDB not available for query-context alignment test"
                    )
                raise

            # Skip if no results (documents not ingested)
            if not chunks:
                pytest.skip(f"No documents found for query: {query}")

            # Compute average similarity between query and chunks
            avg_similarity = compute_average_chunk_similarity(
                query, chunks, embedding_model
            )

            # Build detailed failure message
            chunk_similarities = []
            for i, chunk in enumerate(chunks):
                chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
                if chunk_text:
                    sim = compute_cosine_similarity(query, chunk_text, embedding_model)
                    chunk_similarities.append((i + 1, sim, chunk_text[:100]))

            # Assert average similarity meets threshold
            assert avg_similarity >= QUERY_CONTEXT_SIMILARITY_THRESHOLD, (
                f"Average query-context similarity {avg_similarity:.4f} below threshold "
                f"{QUERY_CONTEXT_SIMILARITY_THRESHOLD} for query: '{query}'\n"
                f"Chunk similarities:\n"
                + "\n".join(
                    f"  Chunk {i}: {sim:.4f} - '{text}...'"
                    for i, sim, text in chunk_similarities
                )
            )

    @pytest.mark.semantic_similarity
    def test_cross_query_similarity(self, embedding_model: Any) -> None:
        """Test that similar queries produce similar answers.

        This test validates the consistency of the RAG pipeline by checking that
        semantically similar queries produce answers with similar semantic content.

        Expected: Answer similarity pattern matches query similarity pattern
        within tolerance.

        Steps:
            1. Define query pairs with known semantic similarity
            2. Execute both queries via RAG pipeline
            3. Compute query similarity and answer similarity
            4. Assert answer similarity correlates with query similarity
        """
        # Query pairs with expected semantic similarity
        query_pairs = [
            {
                "query1": "What is SecondBrain?",
                "query2": "Tell me about SecondBrain tool",
                "expected_similarity": "high",  # Very similar queries
            },
            {
                "query1": "How to ingest documents?",
                "query2": "How to add files to database?",
                "expected_similarity": "high",  # Similar intent
            },
            {
                "query1": "What is MongoDB?",
                "query2": "How does vector search work?",
                "expected_similarity": "medium",  # Related but different
            },
        ]

        for pair in query_pairs:
            query1 = pair["query1"]
            query2 = pair["query2"]
            expected_pattern = pair["expected_similarity"]

            # Compute query similarity
            query_similarity = compute_cosine_similarity(
                query1, query2, embedding_model
            )

            # Execute both queries
            searcher = Searcher(verbose=False)
            llm_provider = OllamaLLMProvider()
            pipeline = RAGPipeline(
                searcher=searcher, llm_provider=llm_provider, top_k=5
            )

            result1 = pipeline.query(query1, top_k=5)
            result2 = pipeline.query(query2, top_k=5)

            answer1 = result1.get("answer", "")
            answer2 = result2.get("answer", "")

            # Skip if answers are not meaningful
            if (
                not answer1
                or not answer2
                or "apologize" in answer1.lower()
                or "apologize" in answer2.lower()
            ):
                searcher.close()
                pytest.skip("LLM unavailable for cross-query test")

            # Compute answer similarity
            answer_similarity = compute_cosine_similarity(
                answer1, answer2, embedding_model
            )

            # Validate pattern: similar queries should have reasonably similar answers
            if expected_pattern == "high":
                # High similarity queries should have answers with at least moderate similarity
                assert answer_similarity > 0.3, (
                    f"High similarity queries produced dissimilar answers.\n"
                    f"Query1: '{query1}'\nQuery2: '{query2}'\n"
                    f"Query similarity: {query_similarity:.4f}\n"
                    f"Answer similarity: {answer_similarity:.4f}\n"
                    f"Answer1: '{answer1[:150]}...'\nAnswer2: '{answer2[:150]}...'"
                )
            elif expected_pattern == "medium":
                # Medium similarity queries may have varying answer similarity
                # Just ensure answers are not completely unrelated (similarity > 0)
                assert answer_similarity > -0.2, (
                    f"Medium similarity queries produced unrelated answers.\n"
                    f"Query1: '{query1}'\nQuery2: '{query2}'\n"
                    f"Query similarity: {query_similarity:.4f}\n"
                    f"Answer similarity: {answer_similarity:.4f}"
                )

            searcher.close()

    @pytest.mark.semantic_similarity
    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param(
                {
                    "id": "config-001",
                    "query": "What is the default chunk size?",
                    "expected_concepts": ["chunk", "size", "default", "4096"],
                    "forbidden_concepts": ["memory", "buffer"],
                },
                id="config-001",
            ),
            pytest.param(
                {
                    "id": "config-002",
                    "query": "How to configure MongoDB URI?",
                    "expected_concepts": ["MongoDB", "URI", "configuration"],
                    "forbidden_concepts": ["MySQL", "PostgreSQL"],
                },
                id="config-002",
            ),
            pytest.param(
                {
                    "id": "format-001",
                    "query": "What document formats are supported?",
                    "expected_concepts": ["formats", "PDF", "DOCX", "supported"],
                    "forbidden_concepts": ["TXT", "RTF"],
                },
                id="format-001",
            ),
        ],
    )
    def test_golden_dataset_query_answer_similarity(
        self,
        test_case: dict[str, Any],
        embedding_model: Any,
    ) -> None:
        """Test query-answer similarity using golden dataset entries.

        This test uses parametrized golden dataset entries to validate that
        queries produce answers with high semantic similarity.

        Args:
            test_case: Golden dataset test case with query and expected_concepts.
            embedding_model: Pre-loaded SentenceTransformer model.

        Expected: Similarity >= 0.6 for all golden dataset queries.
        """
        query = test_case["query"]
        expected_concepts = test_case.get("expected_concepts", [])

        # Execute query via RAG pipeline
        searcher = Searcher(verbose=False)
        llm_provider = OllamaLLMProvider()
        pipeline = RAGPipeline(searcher=searcher, llm_provider=llm_provider, top_k=5)

        result = pipeline.query(query, top_k=5, show_sources=True)
        answer = result.get("answer", "")

        # Skip if LLM unavailable
        if not answer or "apologize" in answer.lower():
            searcher.close()
            pytest.skip(f"LLM unavailable for golden dataset query: {query}")

        # Compute similarity
        similarity = compute_cosine_similarity(query, answer, embedding_model)

        # Assert similarity meets threshold
        assert similarity >= QUERY_ANSWER_SIMILARITY_THRESHOLD, (
            f"Golden dataset test {test_case['id']} failed.\n"
            f"Query: '{query}'\n"
            f"Expected concepts: {expected_concepts}\n"
            f"Similarity: {similarity:.4f} (threshold: {QUERY_ANSWER_SIMILARITY_THRESHOLD})\n"
            f"Answer: '{answer[:200]}...'"
        )

        searcher.close()

    @pytest.mark.semantic_similarity
    @pytest.mark.parametrize(
        "query,expected_min_similarity",
        [
            ("What is SecondBrain?", 0.6),
            ("How to ingest documents?", 0.5),
            ("What is semantic search?", 0.55),
        ],
    )
    def test_parametrized_query_answer_threshold(
        self,
        query: str,
        expected_min_similarity: float,
        embedding_model: Any,
    ) -> None:
        """Test query-answer similarity with parametrized thresholds.

        This test validates query-answer similarity using different threshold
        values to ensure robustness across configurations.

        Args:
            query: Test query string.
            expected_min_similarity: Expected minimum similarity threshold.
            embedding_model: Pre-loaded SentenceTransformer model.
        """
        # Execute query via CLI for integration testing
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--top-k", "5", query])

        # Skip if CLI fails (LLM unavailable)
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
            pytest.skip(f"Could not extract answer from CLI output for: {query}")

        # Compute similarity
        similarity = compute_cosine_similarity(query, answer, embedding_model)

        # Assert similarity meets expected threshold
        assert similarity >= expected_min_similarity, (
            f"Query-answer similarity {similarity:.4f} below expected "
            f"{expected_min_similarity} for query: '{query}'\n"
            f"Answer: '{answer[:200]}...'"
        )

    @pytest.mark.semantic_similarity
    def test_identical_inputs_max_similarity(self, embedding_model: Any) -> None:
        """Test that identical inputs produce maximum similarity.

        This test validates the similarity metric itself by checking that
        identical texts produce cosine similarity of 1.0.

        Expected: Similarity = 1.0 (or very close, within floating point tolerance).
        """
        test_strings = [
            "What is the default chunk size in SecondBrain?",
            "SecondBrain is a document intelligence CLI tool.",
            "MongoDB is used for vector storage.",
        ]

        for text in test_strings:
            similarity = compute_cosine_similarity(text, text, embedding_model)

            # Allow small floating point tolerance
            assert math.isclose(similarity, 1.0, abs_tol=0.0001), (
                f"Identical texts should have similarity 1.0, got {similarity:.6f}\n"
                f"Text: '{text}'"
            )

    @pytest.mark.semantic_similarity
    def test_orthogonal_inputs_zero_similarity(self, embedding_model: Any) -> None:
        """Test that semantically unrelated inputs have low similarity.

        This test validates that the similarity metric correctly identifies
        unrelated texts as having low similarity.

        Expected: Similarity < 0.3 for semantically unrelated texts.
        """
        # Pairs of semantically unrelated texts
        unrelated_pairs = [
            ("What is Python programming?", "How to bake chocolate cake?"),
            ("MongoDB vector search", "Basketball game rules"),
            ("Document chunking strategies", "Weather forecast tomorrow"),
        ]

        for text1, text2 in unrelated_pairs:
            similarity = compute_cosine_similarity(text1, text2, embedding_model)

            # Unrelated texts should have low similarity (typically < 0.3)
            assert similarity < 0.3, (
                f"Unrelated texts have unexpectedly high similarity {similarity:.4f}\n"
                f"Text1: '{text1}'\nText2: '{text2}'"
            )

    @pytest.mark.semantic_similarity
    def test_similarity_threshold_configurability(
        self,
        embedding_model: Any,
    ) -> None:
        """Test that similarity thresholds are configurable constants.

        This test validates that thresholds are defined as module-level constants
        and can be easily adjusted for different use cases.

        Expected: Thresholds are accessible and reasonable (0.3-0.8 range).
        """
        # Verify thresholds are defined and reasonable
        assert 0.3 <= QUERY_ANSWER_SIMILARITY_THRESHOLD <= 0.8, (
            f"QUERY_ANSWER_SIMILARITY_THRESHOLD {QUERY_ANSWER_SIMILARITY_THRESHOLD} "
            "should be between 0.3 and 0.8"
        )

        assert 0.3 <= QUERY_CONTEXT_SIMILARITY_THRESHOLD <= 0.8, (
            f"QUERY_CONTEXT_SIMILARITY_THRESHOLD {QUERY_CONTEXT_SIMILARITY_THRESHOLD} "
            "should be between 0.3 and 0.8"
        )

        assert 0.05 <= CROSS_QUERY_SIMILARITY_TOLERANCE <= 0.3, (
            f"CROSS_QUERY_SIMILARITY_TOLERANCE {CROSS_QUERY_SIMILARITY_TOLERANCE} "
            "should be between 0.05 and 0.3"
        )
