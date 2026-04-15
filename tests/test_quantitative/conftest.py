"""
Shared fixtures and utilities for quantitative testing.

This module provides:
- Session-scoped embedding model fixture
- Golden dataset loading fixtures
- Sample golden query fixtures
- Helper functions for metrics calculation (cosine similarity, precision/recall@K)
- Test data seeding fixture for MongoDB
"""

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

from secondbrain.rag.providers.mock import MockLLMProvider, MockLLMProviderWithContext

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
GOLDEN_DATASETS_DIR = PROJECT_ROOT / "tests" / "data" / "golden_datasets"


def _check_mongo_has_documents() -> bool:
    try:
        from secondbrain.config import config

        uri = config.mongo_uri
        db_name = config.mongo_db
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        db = client.get_database(db_name)
        # Check 'chunks' collection (tests need actual chunk data)
        chunks_collection = db.get_collection("chunks")
        chunks_count = chunks_collection.count_documents({}, limit=1)
        client.close()
        return chunks_count > 0
    except Exception:
        return False


def _seed_test_data() -> None:
    """Seed MongoDB with test data for quantitative tests.

    Creates sample chunks with embeddings that match the golden dataset queries
    to ensure tests can run without requiring actual document ingestion.
    """
    try:
        from secondbrain.config import config
        from secondbrain.embedding import LocalEmbeddingGenerator

        uri = config.mongo_uri
        db_name = config.mongo_db
        # Use very short timeout to avoid hanging
        client = MongoClient(uri, serverSelectionTimeoutMS=1000)
        db = client.get_database(db_name)
        chunks_collection = db.get_collection("chunks")

        # Check if test chunks already exist
        existing_test_chunks = chunks_collection.count_documents(
            {"chunk_id": {"$regex": "^test-chunk-"}}, limit=1
        )
        if existing_test_chunks > 0:
            client.close()
            return

        # Load embedding generator
        embed_gen = LocalEmbeddingGenerator()

        # Sample test chunks matching golden dataset queries
        # These are designed to have good semantic overlap with common test queries
        test_chunks = [
            {
                "chunk_id": "test-chunk-001",
                "source_file": "tests/config.md",
                "page_number": 1,
                "chunk_text": "The default chunk size in SecondBrain is 4096 tokens. This is the standard configuration for document processing. You can configure the chunk size using the SECONDBRAIN_CHUNK_SIZE environment variable.",
                "file_type": "markdown",
                "metadata": {
                    "chunk_size": 4096,
                    "chunk_overlap": 256,
                },
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-002",
                "source_file": "tests/config.md",
                "page_number": 1,
                "chunk_text": "MongoDB connection URI configuration is done through the SECONDBRAIN_MONGO_URI environment variable. The default MongoDB URI is mongodb://localhost:27017 for local development.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-003",
                "source_file": "tests/config.md",
                "page_number": 2,
                "chunk_text": "Logging configuration uses SECONDBRAIN_LOG_LEVEL environment variable with values INFO, DEBUG, WARNING, or ERROR. The SECONDBRAIN_LOG_FORMAT controls output format with options pretty or json.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-004",
                "source_file": "tests/config.md",
                "page_number": 2,
                "chunk_text": "Circuit breaker protection can be enabled by setting SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true. This provides automatic failure handling with recovery mechanisms for production reliability.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-005",
                "source_file": "tests/features.md",
                "page_number": 1,
                "chunk_text": "SecondBrain supports multiple document formats for ingestion including PDF, DOCX, PPTX, XLSX, HTML, Markdown files, images, and audio files. The Ingestor class handles multi-format document parsing and automatic chunking.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-006",
                "source_file": "tests/features.md",
                "page_number": 2,
                "chunk_text": "Semantic search functionality uses embedding vectors from the all-MiniLM-L6-v2 model from sentence-transformers. Search results are ranked using cosine similarity with a default top-k of 5 results returned.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-007",
                "source_file": "tests/architecture.md",
                "page_number": 1,
                "chunk_text": "SecondBrain system architecture consists of five main components: CLI layer for user commands, Document Ingestor for parsing, Embedding Engine using sentence-transformers, Storage Layer with MongoDB, and Searcher for vector search. Data flows from document ingestion through chunking, embedding generation, storage, and semantic search.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-008",
                "source_file": "tests/cli.md",
                "page_number": 1,
                "chunk_text": "Available SecondBrain CLI commands include: secondbrain ingest for document ingestion, secondbrain search for semantic queries, secondbrain chat for interactive conversations, secondbrain ls to list documents, secondbrain delete to remove documents, secondbrain status for database statistics, and secondbrain health for system checks. Use -v or --verbose flag for detailed output.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-009",
                "source_file": "tests/errors.md",
                "page_number": 1,
                "chunk_text": "Common error handling: MongoDB connection errors occur when the connection URI is invalid or network connectivity fails. Embedding model loading failures require ensuring sentence-transformers is properly installed. When no documents match a search query, the system returns a fallback message indicating no relevant documents were found.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            {
                "chunk_id": "test-chunk-010",
                "source_file": "tests/defaults.md",
                "page_number": 1,
                "chunk_text": "Default configuration values: chunk_size equals 4096 tokens, chunk_overlap is 256 tokens, top_k returns 5 results, and the default embedding model is all-MiniLM-L6-v2 from sentence-transformers library.",
                "file_type": "markdown",
                "metadata": {},
                "ingested_at": datetime.now(UTC).isoformat(),
            },
        ]

        # Add embeddings to each chunk
        for chunk in test_chunks:
            chunk["embedding"] = embed_gen.generate(chunk["chunk_text"])

        # Insert test chunks
        chunks_collection.insert_many(test_chunks)
        embed_gen.close()
        client.close()

    except Exception as e:
        # Log but don't fail - tests will skip if seeding fails
        import logging

        logging.getLogger(__name__).debug(
            f"Failed to seed test data (MongoDB unavailable): {e}"
        )


@pytest.fixture(scope="function")
def require_mongo_documents():
    """Skip test if MongoDB has no documents."""
    if not _check_mongo_has_documents():
        pytest.skip("MongoDB has no documents - quantitative tests require data")


@pytest.fixture(scope="session", autouse=True)
def seed_test_data_session():
    """Seed test data at session start for all quantitative tests.

    Uses short timeout to avoid hanging when MongoDB is unavailable.
    Tests will skip gracefully if seeding fails.
    """
    _seed_test_data()


@pytest.fixture(scope="session")
def embedding_model() -> SentenceTransformer:
    """
    Load embedding model once per session.

    Uses the same model as the application for consistency.
    Cached at session scope to avoid reloading across tests.

    Returns:
        SentenceTransformer: Loaded embedding model
    """
    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture(scope="session")
def golden_datasets() -> dict[str, list[dict[str, Any]]]:
    """
    Load all available golden datasets from tests/data/golden_datasets/.

    Returns:
        dict mapping dataset name to list of test cases
    """
    datasets = {}

    if not GOLDEN_DATASETS_DIR.exists():
        return datasets

    for dataset_file in GOLDEN_DATASETS_DIR.glob("*.json"):
        dataset_name = dataset_file.stem
        try:
            with open(dataset_file, encoding="utf-8") as f:
                data = json.load(f)
                # Support both "test_cases" and "queries" formats
                test_cases = data.get("test_cases", data.get("queries", []))
                datasets[dataset_name] = test_cases
        except (OSError, json.JSONDecodeError) as e:
            pytest.fail(f"Failed to load golden dataset {dataset_name}: {e}")

    return datasets


@pytest.fixture
def sample_golden_queries() -> list[dict[str, Any]]:
    """
    Sample golden queries for testing (3-5 test cases).

    Returns:
        List of sample queries with expected answers and metadata
    """
    return [
        {
            "id": "sample-001",
            "query": "What is the default chunk size in SecondBrain?",
            "expected_answer": "The default chunk size is 4096 tokens.",
            "expected_concepts": ["chunk", "size", "4096", "default"],
            "forbidden_concepts": ["memory", "buffer", "streaming"],
            "relevant_chunk_ids": ["chunk-001", "chunk-002"],
        },
        {
            "id": "sample-002",
            "query": "How do I configure MongoDB connection URI?",
            "expected_answer": "Set the SECONDBRAIN_MONGO_URI environment variable.",
            "expected_concepts": ["MongoDB", "URI", "configuration", "environment"],
            "forbidden_concepts": ["MySQL", "PostgreSQL", "SQLite"],
            "relevant_chunk_ids": ["chunk-010", "chunk-011"],
        },
        {
            "id": "sample-003",
            "query": "What document formats are supported?",
            "expected_answer": "PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio.",
            "expected_concepts": ["PDF", "DOCX", "formats", "supported"],
            "forbidden_concepts": ["TXT", "RTF", "ODT"],
            "relevant_chunk_ids": ["chunk-020"],
        },
        {
            "id": "sample-004",
            "query": "How to enable circuit breaker?",
            "expected_answer": "Set SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true.",
            "expected_concepts": ["circuit", "breaker", "enabled", "configuration"],
            "forbidden_concepts": ["disabled", "off", "MySQL"],
            "relevant_chunk_ids": ["chunk-030", "chunk-031"],
        },
        {
            "id": "sample-005",
            "query": "What is the purpose of the Ingestor class?",
            "expected_answer": "The Ingestor class handles multi-format document parsing and chunking.",
            "expected_concepts": ["Ingestor", "document", "parsing", "chunking"],
            "forbidden_concepts": ["search", "query", "embedding"],
            "relevant_chunk_ids": ["chunk-040"],
        },
    ]


def load_golden_dataset(dataset_name: str) -> list[dict[str, Any]]:
    """
    Load a specific golden dataset by name.

    Args:
        dataset_name: Name of the dataset (without .json extension)

    Returns:
        List of test cases from the dataset

    Raises:
        FileNotFoundError: If dataset file doesn't exist
        json.JSONDecodeError: If dataset file is invalid JSON
    """
    dataset_path = GOLDEN_DATASETS_DIR / f"{dataset_name}.json"

    if not dataset_path.exists():
        raise FileNotFoundError(f"Golden dataset not found: {dataset_path}")

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    # Support both "test_cases" and "queries" formats
    return data.get("test_cases", data.get("queries", []))


def cosine_similarity(
    query: str, answer: str, model: SentenceTransformer | None = None
) -> float:
    """
    Calculate cosine similarity between query and answer embeddings.

    Args:
        query: Query text
        answer: Answer text
        model: Optional pre-loaded embedding model (loads default if None)

    Returns:
        Cosine similarity score (range: -1 to 1)
    """
    if model is None:
        model = SentenceTransformer("all-MiniLM-L6-v2")

    # Encode both texts
    query_embedding = model.encode(query, convert_to_numpy=True)
    answer_embedding = model.encode(answer, convert_to_numpy=True)

    # Ensure 2D for sklearn
    query_embedding = query_embedding.reshape(1, -1)
    answer_embedding = answer_embedding.reshape(1, -1)

    # Calculate cosine similarity
    similarity = sklearn_cosine_similarity(query_embedding, answer_embedding)[0][0]

    return float(similarity)


def calculate_precision_at_k(
    results: list[dict[str, Any]],
    relevant_ids: set[str] | list[str],
    k: int,
) -> float:
    """
    Calculate precision at K for search results.

    Precision@K = (Number of relevant results in top K) / K

    Args:
        results: List of search result dicts with 'id' or 'chunk_id' key
        relevant_ids: Set or list of relevant document/chunk IDs
        k: Number of top results to consider

    Returns:
        Precision@K score (range: 0.0 to 1.0)
    """
    if not results or k <= 0:
        return 0.0

    # Normalize relevant_ids to set for O(1) lookup
    if isinstance(relevant_ids, list):
        relevant_ids = set(relevant_ids)

    # Get top K results
    top_k_results = results[:k]

    # Count relevant results in top K
    relevant_count = sum(
        1
        for result in top_k_results
        if result.get("id") or result.get("chunk_id") in relevant_ids
    )

    return relevant_count / k


def calculate_recall_at_k(
    results: list[dict[str, Any]],
    relevant_ids: set[str] | list[str],
    k: int,
) -> float:
    """
    Calculate recall at K for search results.

    Recall@K = (Number of relevant results in top K) / (Total relevant results)

    Args:
        results: List of search result dicts with 'id' or 'chunk_id' key
        relevant_ids: Set or list of relevant document/chunk IDs
        k: Number of top results to consider

    Returns:
        Recall@K score (range: 0.0 to 1.0)
        Returns 0.0 if there are no relevant documents
    """
    if not results or k <= 0:
        return 0.0

    # Normalize relevant_ids to set
    if isinstance(relevant_ids, list):
        relevant_ids = set(relevant_ids)

    if not relevant_ids:
        return 0.0

    # Get top K results
    top_k_results = results[:k]

    # Extract result IDs
    result_ids = {
        result.get("id") or result.get("chunk_id")
        for result in top_k_results
        if result.get("id") or result.get("chunk_id")
    }

    # Count relevant results in top K
    relevant_count = len(result_ids & relevant_ids)

    # Calculate recall
    return relevant_count / len(relevant_ids)


def calculate_map(
    results: list[dict[str, Any]],
    relevant_ids: set[str] | list[str],
) -> float:
    """
    Calculate Mean Average Precision (mAP) for search results.

    mAP = (1 / |relevant|) * sum(precision_at_each_relevant_item)

    Args:
        results: List of search result dicts with 'id' or 'chunk_id' key
        relevant_ids: Set or list of relevant document/chunk IDs

    Returns:
        Mean Average Precision score (range: 0.0 to 1.0)
    """
    if not results:
        return 0.0

    # Normalize relevant_ids to set
    if isinstance(relevant_ids, list):
        relevant_ids = set(relevant_ids)

    if not relevant_ids:
        return 0.0

    # Extract result IDs
    result_ids = [
        result.get("id") or result.get("chunk_id")
        for result in results
        if result.get("id") or result.get("chunk_id")
    ]

    # Calculate precision at each relevant item
    precisions = []
    relevant_found = 0

    for i, result_id in enumerate(result_ids, 1):
        if result_id in relevant_ids:
            relevant_found += 1
            precision_at_i = relevant_found / i
            precisions.append(precision_at_i)

    if not precisions:
        return 0.0

    # Mean Average Precision
    return sum(precisions) / len(relevant_ids)


def _check_ollama_available() -> bool:
    """Check if Ollama server is available.

    Returns:
        True if Ollama is running and responsive, False otherwise.
    """
    try:
        from secondbrain.rag.providers.ollama import OllamaLLMProvider

        provider = OllamaLLMProvider()
        return provider.health_check()
    except Exception:
        return False


def is_mock_llm_active() -> bool:
    """Check if mock LLM is currently active (Ollama unavailable)."""
    return not _check_ollama_available()


@pytest.fixture(scope="function", autouse=True)
def auto_skip_if_mock_llm(request):
    """Auto-skip tests requiring real LLM when mock LLM is active."""
    # Skip tests that need real LLM for meaningful results
    if is_mock_llm_active() and any(
        marker in request.keywords
        for marker in [
            "threshold",
            "rouge",
            "performance",
            "consistency",
            "semantic_similarity",
        ]
    ):
        pytest.skip("Skipped: mock LLM used, test requires real LLM")


def is_mock_llm(provider: Any) -> bool:
    """Check if provider is a MockLLMProvider instance."""
    return isinstance(provider, MockLLMProvider)


@pytest.fixture(scope="function")
def llm_provider():
    """Fixture that provides LLM provider with automatic fallback to mock.

    Tries to use OllamaLLMProvider first. If Ollama is unavailable,
    falls back to MockLLMProvider with deterministic responses.

    This ensures tests RUN rather than skip when Ollama is down.

    Returns:
        Either OllamaLLMProvider or MockLLMProvider instance.
    """
    from secondbrain.rag.providers.ollama import OllamaLLMProvider

    if _check_ollama_available():
        return OllamaLLMProvider()
    else:
        # Use mock provider with context-aware responses for better test realism
        return MockLLMProviderWithContext()


@pytest.fixture(scope="function")
def rag_pipeline_with_mock():
    """Fixture that provides RAGPipeline with automatic LLM fallback.

    Creates a RAGPipeline with Searcher and LLM provider that automatically
    falls back to mock when Ollama is unavailable.

    This ensures tests RUN rather than skip when Ollama is down.

    Returns:
        RAGPipeline instance with working LLM provider.
    """
    from secondbrain.rag import RAGPipeline
    from secondbrain.rag.providers.ollama import OllamaLLMProvider
    from secondbrain.search import Searcher

    searcher = Searcher()

    if _check_ollama_available():
        llm_provider = OllamaLLMProvider()
    else:
        # Use mock provider with context-aware responses
        llm_provider = MockLLMProviderWithContext()

    pipeline = RAGPipeline(searcher=searcher, llm_provider=llm_provider, top_k=3)

    yield pipeline

    searcher.close()


def calculate_ndcg(
    results: list[dict[str, Any]],
    relevant_ids: set[str] | list[str],
    k: int | None = None,
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain (nDCG) at K.

    nDCG@K = DCG@K / IDCG@K

    Args:
        results: List of search result dicts with 'id' or 'chunk_id' key
        relevant_ids: Set or list of relevant document/chunk IDs
        k: Number of top results to consider (None = all results)

    Returns:
        nDCG score (range: 0.0 to 1.0)
    """
    if not results:
        return 0.0

    # Normalize relevant_ids to set
    if isinstance(relevant_ids, list):
        relevant_ids = set(relevant_ids)

    if not relevant_ids:
        return 0.0

    # Extract result IDs
    result_ids = [
        result.get("id") or result.get("chunk_id")
        for result in results
        if result.get("id") or result.get("chunk_id")
    ]

    if k:
        result_ids = result_ids[:k]

    # Calculate DCG
    dcg = 0.0
    for i, result_id in enumerate(result_ids, 1):
        relevance = 1.0 if result_id in relevant_ids else 0.0
        dcg += relevance / math.log2(i + 1)

    # Calculate IDCG (ideal DCG)
    ideal_relevances = sorted(
        [1.0] * len(relevant_ids) + [0.0] * (len(result_ids) - len(relevant_ids)),
        reverse=True,
    )
    idcg = sum(rel / math.log2(i + 1) for i, rel in enumerate(ideal_relevances, 1))

    if idcg == 0:
        return 0.0

    return dcg / idcg
