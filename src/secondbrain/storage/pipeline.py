"""MongoDB search pipeline builder for local vector search.

This module provides functions to build MongoDB aggregation pipelines
for vector similarity search using manual cosine similarity calculation.
"""

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

    Uses manual cosine similarity calculation via MongoDB aggregation
    operators. This approach works with MongoDB Community Edition without
    requiring Atlas Search.

    The pipeline:
    1. Filters documents by source/file type (optional)
    2. Calculates cosine similarity between query and document vectors
    3. Sorts by similarity score (descending)
    4. Returns top-k most similar documents

    Note: This is O(n) complexity as it scans all documents. Suitable for
    small to medium datasets (<100k documents). For larger datasets, consider
    specialized vector databases.

    Args:
        embedding: Query embedding vector.
        top_k: Number of results to return.
        source_filter: Filter by source file (prefix match).
        file_type_filter: Filter by file type.
        use_prefix_match: If True, use anchored regex for better performance.

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

    # Calculate query vector magnitude in Python (not in MongoDB)
    query_magnitude = math.sqrt(sum(x * x for x in embedding))
    embedding_dim = len(embedding)

    pipeline: list[dict[str, Any]] = []

    # Match stage (if filters exist)
    if query_filter:
        pipeline.append({"$match": query_filter})

    # Project stage with cosine similarity calculation
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

    # Final projection - keep only desired fields (inclusion mode)
    pipeline.append(
        {
            "$project": {
                "_id": 0,  # Exclude MongoDB's _id field
                "chunk_id": 1,
                "source_file": 1,
                "page_number": 1,
                "chunk_text": 1,
                "score": 1,
            }
        }
    )

    return pipeline
