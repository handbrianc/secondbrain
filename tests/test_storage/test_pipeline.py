"""Tests for ``secondbrain.storage.pipeline.build_search_pipeline``.

Covers the MongoDB aggregation-pipeline builder: filter handling, cosine
similarity projection, sort/limit stages, and regex-injection escaping.
"""

from __future__ import annotations

from secondbrain.storage.pipeline import build_search_pipeline


def test_basic_pipeline_shape() -> None:
    pipeline = build_search_pipeline([0.0, 1.0], top_k=5)
    assert isinstance(pipeline, list)
    assert "$project" in pipeline[0]
    assert pipeline[1] == {"$sort": {"score": -1}}
    assert {"$limit": 5} in pipeline
    assert pipeline[-1] == {
        "$project": {
            "_id": 0,
            "chunk_id": 1,
            "source_file": 1,
            "page_number": 1,
            "chunk_text": 1,
            "element_type": 1,
            "chunk_role": 1,
            "score": 1,
        }
    }


def test_source_filter_prefix_match() -> None:
    pipeline = build_search_pipeline([1.0], top_k=3, source_filter="docs")
    assert pipeline[0] == {"$match": {"source_file": {"$regex": "^docs"}}}


def test_source_filter_no_prefix() -> None:
    pipeline = build_search_pipeline(
        [1.0], top_k=3, source_filter="docs", use_prefix_match=False
    )
    assert pipeline[0] == {"$match": {"source_file": {"$regex": "docs"}}}


def test_file_type_filter() -> None:
    pipeline = build_search_pipeline([1.0], top_k=3, file_type_filter="pdf")
    assert pipeline[0] == {"$match": {"file_type": "pdf"}}


def test_regex_injection_is_escaped() -> None:
    pipeline = build_search_pipeline([1.0], top_k=3, source_filter="a.b")
    regex = pipeline[0]["$match"]["source_file"]["$regex"]
    assert regex == "^a\\.b"


def test_embedding_dim_drives_range() -> None:
    pipeline = build_search_pipeline([0.0, 1.0, 2.0, 3.0], top_k=1)
    project = pipeline[0]["$project"]
    score = project["score"]
    reduce_input = score["$let"]["vars"]["dot_product"]["$reduce"]["input"]
    assert reduce_input == {"$range": [0, 4]}


def test_all_filters_combined() -> None:
    pipeline = build_search_pipeline(
        [1.0, 2.0],
        top_k=10,
        source_filter="reports",
        file_type_filter="docx",
        use_prefix_match=False,
    )
    assert pipeline[0] == {
        "$match": {
            "source_file": {"$regex": "reports"},
            "file_type": "docx",
        }
    }
