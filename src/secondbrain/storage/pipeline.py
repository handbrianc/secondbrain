"""MongoDB search pipeline builder."""

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
