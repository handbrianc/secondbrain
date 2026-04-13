"""
Shared fixtures and utilities for quantitative testing.

This module provides:
- Session-scoped embedding model fixture
- Golden dataset loading fixtures
- Sample golden query fixtures
- Helper functions for metrics calculation (cosine similarity, precision/recall@K)
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
GOLDEN_DATASETS_DIR = PROJECT_ROOT / "tests" / "data" / "golden_datasets"


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
            with open(dataset_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Support both "test_cases" and "queries" formats
                test_cases = data.get("test_cases", data.get("queries", []))
                datasets[dataset_name] = test_cases
        except (json.JSONDecodeError, IOError) as e:
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

    with open(dataset_path, "r", encoding="utf-8") as f:
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
