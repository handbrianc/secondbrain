"""MongoDB search pipeline builder."""

import math
from typing import Any


def build_search_pipeline(
    embedding: list[float],
    top_k: int,
    source_filter: str | None = None,
    file_type_filter: str | None = None,
    use_prefix_match: bool = True,
) -> list[dict[str, Any]]:
    """Build MongoDB aggregation pipeline for vector search.

    Uses anchored regex for source filtering to improve index performance.

    Args:
        embedding: Query embedding vector.
        top_k: Number of results to return.
        source_filter: Filter by source file.
        file_type_filter: Filter by file type.
        use_prefix_match: If True, use anchored regex for better index usage.

    Returns
    -------
        Aggregation pipeline for vector search.
    """
    query_filter: dict[str, Any] = {}
    if source_filter:
        if use_prefix_match:
            query_filter["source_file"] = {"$regex": f"^{source_filter}"}
        else:
            query_filter["source_file"] = {"$regex": source_filter}
    if file_type_filter:
        query_filter["file_type"] = file_type_filter

    pipeline: list[dict[str, Any]] = [
        {
            "$vectorSearch": {
                "queryVector": embedding,
                "path": "embedding",
                "numCandidates": top_k * 10,
                "limit": top_k,
                "index": "embedding_index",
            }
        },
    ]

    if query_filter:
        pipeline.append({"$match": query_filter})

    pipeline.extend(
        [
            {
                "$project": {
                    "chunk_id": 1,
                    "source_file": 1,
                    "page_number": 1,
                    "chunk_text": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
    )

    return pipeline


def build_fallback_search_pipeline(
    embedding: list[float],
    top_k: int,
    source_filter: str | None = None,
    file_type_filter: str | None = None,
    use_prefix_match: bool = True,
) -> list[dict[str, Any]]:
    """Build fallback aggregation pipeline for manual vector search.

    When Atlas Search is not available (local MongoDB), this pipeline
    retrieves all documents and calculates cosine similarity manually.

    Note: This is O(n) and may be slow for large datasets. Use only
    when Atlas Search is unavailable.

    Args:
        embedding: Query embedding vector.
        top_k: Number of results to return.
        source_filter: Filter by source file.
        file_type_filter: Filter by file type.
        use_prefix_match: If True, use anchored regex for better index usage.

    Returns
    -------
        Aggregation pipeline for fallback vector search.
    """
    query_filter: dict[str, Any] = {}
    if source_filter:
        if use_prefix_match:
            query_filter["source_file"] = {"$regex": f"^{source_filter}"}
        else:
            query_filter["source_file"] = {"$regex": source_filter}
    if file_type_filter:
        query_filter["file_type"] = file_type_filter

    # Calculate query vector magnitude in Python (not in MongoDB)
    query_magnitude = math.sqrt(sum(x * x for x in embedding))
    embedding_dim = len(embedding)

    pipeline: list[dict[str, Any]] = []

    # Match stage (if filters exist)
    if query_filter:
        pipeline.append({"$match": query_filter})

    # Project stage with cosine similarity calculation
    # Build the dot product calculation dynamically
    dot_product_in = []
    for i, val in enumerate(embedding):
        dot_product_in.append({"$multiply": [{"$arrayElemAt": ["$embedding", i]}, val]})

    magnitude_in = []
    for i in range(embedding_dim):
        magnitude_in.append(
            {
                "$multiply": [
                    {"$arrayElemAt": ["$embedding", i]},
                    {"$arrayElemAt": ["$embedding", i]},
                ]
            }
        )

    pipeline.append(
        {
            "$project": {
                "chunk_id": 1,
                "source_file": 1,
                "page_number": 1,
                "chunk_text": 1,
                "embedding": 1,
                "score": {
                    "$let": {
                        "vars": {
                            "doc_magnitude": {
                                "$sqrt": {
                                    "$reduce": {
                                        "input": {"$range": [0, embedding_dim]},
                                        "initialValue": 0,
                                        "in": {
                                            "$add": [
                                                "$$value",
                                                {
                                                    "$multiply": [
                                                        {
                                                            "$arrayElemAt": [
                                                                "$embedding",
                                                                "$$this",
                                                            ]
                                                        },
                                                        {
                                                            "$arrayElemAt": [
                                                                "$embedding",
                                                                "$$this",
                                                            ]
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                    }
                                }
                            },
                            "dot_product": {
                                "$reduce": {
                                    "input": {"$range": [0, embedding_dim]},
                                    "initialValue": 0,
                                    "in": {
                                        "$add": [
                                            "$$value",
                                            {
                                                "$multiply": [
                                                    {
                                                        "$arrayElemAt": [
                                                            "$embedding",
                                                            "$$this",
                                                        ]
                                                    },
                                                    {
                                                        "$arrayElemAt": [
                                                            embedding,
                                                            "$$this",
                                                        ]
                                                    },
                                                ]
                                            },
                                        ]
                                    },
                                }
                            },
                        },
                        "in": {
                            "$cond": [
                                {
                                    "$or": [
                                        {"$eq": ["$$doc_magnitude", 0]},
                                        {"$eq": [query_magnitude, 0]},
                                    ]
                                },
                                0,
                                {
                                    "$divide": [
                                        "$$dot_product",
                                        {
                                            "$multiply": [
                                                "$$doc_magnitude",
                                                query_magnitude,
                                            ]
                                        },
                                    ]
                                },
                            ]
                        },
                    }
                },
            }
        }
    )

    # Sort by score (descending)
    pipeline.append({"$sort": {"score": -1}})

    # Limit results
    pipeline.append({"$limit": top_k})

    # Final projection (remove embedding from output)
    pipeline.append(
        {
            "$project": {
                "chunk_id": 1,
                "source_file": 1,
                "page_number": 1,
                "chunk_text": 1,
                "score": 1,
                "embedding": 0,
            }
        }
    )

    return pipeline
