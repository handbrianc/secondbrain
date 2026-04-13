"""
Quantitative testing module.

This module provides exports for shared utilities and fixtures used in
quantitative testing of the RAG pipeline.

Exports:
    - cosine_similarity: Calculate cosine similarity between texts
    - calculate_precision_at_k: Precision@K metric
    - calculate_recall_at_k: Recall@K metric
    - calculate_map: Mean Average Precision metric
    - calculate_ndcg: Normalized Discounted Cumulative Gain metric
    - load_golden_dataset: Load golden dataset by name
    - embedding_model: Session-scoped embedding model fixture
    - golden_datasets: Session-scoped dataset loader fixture
    - sample_golden_queries: Sample golden queries fixture
"""

from .conftest import (
    calculate_map,
    calculate_ndcg,
    calculate_precision_at_k,
    calculate_recall_at_k,
    cosine_similarity,
    load_golden_dataset,
)

__all__ = [
    "calculate_map",
    "calculate_ndcg",
    "calculate_precision_at_k",
    "calculate_recall_at_k",
    "cosine_similarity",
    "load_golden_dataset",
]
