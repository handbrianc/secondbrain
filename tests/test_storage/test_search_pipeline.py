"""Tests for search pipeline construction."""

from secondbrain.storage import build_search_pipeline


class TestBuildSearchPipeline:
    """Tests for the build_search_pipeline function."""

    def test_basic_pipeline_no_filters(self) -> None:
        """Test basic pipeline without any filters."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(embedding=embedding, top_k=5)

        assert len(pipeline) == 2  # vectorSearch, project

        # First stage should be vectorSearch
        assert "$vectorSearch" in pipeline[0]
        vector_search = pipeline[0]["$vectorSearch"]
        assert vector_search["queryVector"] == embedding
        assert vector_search["path"] == "embedding"
        assert vector_search["numCandidates"] == 50  # top_k * 10
        assert vector_search["limit"] == 5
        assert vector_search["index"] == "embedding_index"

        # Last stage should be projection
        assert "$project" in pipeline[-1]
        project = pipeline[-1]["$project"]
        assert "chunk_id" in project
        assert "source_file" in project
        assert "page_number" in project
        assert "chunk_text" in project
        assert "score" in project

    def test_pipeline_with_source_filter(self) -> None:
        """Test pipeline with source file filter."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding, top_k=5, source_filter="document.pdf"
        )

        assert len(pipeline) == 3  # vectorSearch, match, project

        # Second stage should be match with source filter
        assert "$match" in pipeline[1]
        match = pipeline[1]["$match"]
        assert match["source_file"] == {"$regex": "document.pdf"}

    def test_pipeline_with_file_type_filter(self) -> None:
        """Test pipeline with file type filter."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding, top_k=5, file_type_filter="pdf"
        )

        assert len(pipeline) == 3  # vectorSearch, match, project

        # Second stage should be match with file type filter
        assert "$match" in pipeline[1]
        match = pipeline[1]["$match"]
        assert match["metadata.file_type"] == "pdf"

    def test_pipeline_with_both_filters(self) -> None:
        """Test pipeline with both source and file type filters."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=5,
            source_filter="report.pdf",
            file_type_filter="pdf",
        )

        assert len(pipeline) == 3  # vectorSearch, match, project

        # Second stage should be match with both filters
        assert "$match" in pipeline[1]
        match = pipeline[1]["$match"]
        assert match["source_file"] == {"$regex": "report.pdf"}
        assert match["metadata.file_type"] == "pdf"

    def test_pipeline_numcandidates_scaling(self) -> None:
        """Test that numCandidates scales with top_k."""
        embedding = [0.1] * 10

        for top_k in [5, 10, 20, 50]:
            pipeline = build_search_pipeline(embedding=embedding, top_k=top_k)
            vector_search = pipeline[0]["$vectorSearch"]
            assert vector_search["numCandidates"] == top_k * 10
            assert vector_search["limit"] == top_k

    def test_projection_includes_score(self) -> None:
        """Test that projection includes vectorSearchScore."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(embedding=embedding, top_k=5)

        project = pipeline[-1]["$project"]
        assert project["score"] == {"$meta": "vectorSearchScore"}

    def test_pipeline_order(self) -> None:
        """Test that pipeline stages are in correct order."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=5,
            source_filter="test.pdf",
        )

        # vectorSearch must be first
        assert "$vectorSearch" in pipeline[0]

        # match should come after vectorSearch
        assert "$match" in pipeline[1]

        # project should be last
        assert "$project" in pipeline[-1]

    def test_pipeline_with_different_top_k_values(self) -> None:
        """Test pipeline generation with various top_k values."""
        embedding = [0.1] * 10

        test_cases = [
            (1, 10, 1),
            (5, 50, 5),
            (10, 100, 10),
            (100, 1000, 100),
        ]

        for top_k, expected_candidates, expected_limit in test_cases:
            pipeline = build_search_pipeline(embedding=embedding, top_k=top_k)
            vector_search = pipeline[0]["$vectorSearch"]
            assert vector_search["numCandidates"] == expected_candidates
            assert vector_search["limit"] == expected_limit

    def test_pipeline_filter_regex_pattern(self) -> None:
        """Test that source filter uses regex pattern."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding, top_k=5, source_filter="partial"
        )

        match = pipeline[1]["$match"]
        assert match["source_file"] == {"$regex": "partial"}

    def test_pipeline_field_selection(self) -> None:
        """Test that projection selects only required fields."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(embedding=embedding, top_k=5)

        project = pipeline[-1]["$project"]

        # Should include these fields
        assert project["chunk_id"] == 1
        assert project["source_file"] == 1
        assert project["page_number"] == 1
        assert project["chunk_text"] == 1
        assert project["score"] == {"$meta": "vectorSearchScore"}

        # Should not include _id
        assert "_id" not in project
