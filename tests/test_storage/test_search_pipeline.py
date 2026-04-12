"""Tests for search pipeline construction."""

from secondbrain.storage import build_search_pipeline


class TestBuildSearchPipeline:
    """Tests for the build_search_pipeline function."""

    def test_basic_pipeline_no_filters(self) -> None:
        """Test basic pipeline without any filters."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(embedding=embedding, top_k=5)

        # Pipeline should have 4 stages: project (with score), sort, limit, project (final)
        assert len(pipeline) == 4

        # First stage should be projection with score calculation
        assert "$project" in pipeline[0]
        project = pipeline[0]["$project"]
        assert "score" in project  # Score calculation via $let

        # Second stage should be sort by score
        assert "$sort" in pipeline[1]
        assert pipeline[1]["$sort"]["score"] == -1

        # Third stage should be limit
        assert "$limit" in pipeline[2]
        assert pipeline[2]["$limit"] == 5

        # Last stage should be final projection
        assert "$project" in pipeline[-1]
        final_project = pipeline[-1]["$project"]
        assert "chunk_id" in final_project
        assert "source_file" in final_project
        assert "page_number" in final_project
        assert "chunk_text" in final_project
        assert "score" in final_project
        assert (
            final_project.get("_id") == 0
        )  # _id should be explicitly excluded (set to 0)

    def test_pipeline_with_source_filter(self) -> None:
        """Test pipeline with source file filter."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding, top_k=5, source_filter="document.pdf"
        )

        # Pipeline should have 5 stages: match, project (with score), sort, limit, project (final)
        assert len(pipeline) == 5

        # First stage should be match with source filter (anchored regex)
        assert "$match" in pipeline[0]
        match = pipeline[0]["$match"]
        assert match["source_file"] == {"$regex": "^document.pdf"}

    def test_pipeline_with_file_type_filter(self) -> None:
        """Test pipeline with file type filter."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding, top_k=5, file_type_filter="pdf"
        )

        # Pipeline should have 5 stages: match, project (with score), sort, limit, project (final)
        assert len(pipeline) == 5

        # First stage should be match with file type filter
        assert "$match" in pipeline[0]
        match = pipeline[0]["$match"]
        assert match["file_type"] == "pdf"

    def test_pipeline_with_both_filters(self) -> None:
        """Test pipeline with both source and file type filters."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=5,
            source_filter="report.pdf",
            file_type_filter="pdf",
        )

        # Pipeline should have 5 stages: match, project (with score), sort, limit, project (final)
        assert len(pipeline) == 5

        # First stage should be match with both filters (anchored regex)
        assert "$match" in pipeline[0]
        match = pipeline[0]["$match"]
        assert match["source_file"] == {"$regex": "^report.pdf"}
        assert match["file_type"] == "pdf"

    def test_pipeline_numcandidates_scaling(self) -> None:
        """Test that limit scales with top_k."""
        embedding = [0.1] * 10

        for top_k in [5, 10, 20, 50]:
            pipeline = build_search_pipeline(embedding=embedding, top_k=top_k)
            # Third stage is $limit
            assert pipeline[2]["$limit"] == top_k

    def test_projection_includes_score(self) -> None:
        """Test that projection includes score."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(embedding=embedding, top_k=5)

        # First project stage has score calculation
        project = pipeline[0]["$project"]
        assert "score" in project

        # Final project stage includes score
        final_project = pipeline[-1]["$project"]
        assert "score" in final_project

    def test_pipeline_order(self) -> None:
        """Test that pipeline stages are in correct order."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=5,
            source_filter="test.pdf",
        )

        # match should be first (when filters exist)
        assert "$match" in pipeline[0]

        # project (with score) should be second
        assert "$project" in pipeline[1]

        # sort should be third
        assert "$sort" in pipeline[2]

        # limit should be fourth
        assert "$limit" in pipeline[3]

        # project (final) should be last
        assert "$project" in pipeline[-1]

    def test_pipeline_with_different_top_k_values(self) -> None:
        """Test pipeline generation with various top_k values."""
        embedding = [0.1] * 10

        test_cases = [1, 5, 10, 100]

        for top_k in test_cases:
            pipeline = build_search_pipeline(embedding=embedding, top_k=top_k)
            # Third stage is $limit
            assert pipeline[2]["$limit"] == top_k

    def test_pipeline_filter_regex_pattern(self) -> None:
        """Test that source filter uses anchored regex pattern."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(
            embedding=embedding, top_k=5, source_filter="partial"
        )

        # First stage is match (when filter exists)
        match = pipeline[0]["$match"]
        # Default behavior uses anchored regex for better index performance
        assert match["source_file"] == {"$regex": "^partial"}

    def test_pipeline_field_selection(self) -> None:
        """Test that projection selects only required fields."""
        embedding = [0.1] * 10
        pipeline = build_search_pipeline(embedding=embedding, top_k=5)

        # Final project stage
        project = pipeline[-1]["$project"]

        # Should include these fields
        assert project["chunk_id"] == 1
        assert project["source_file"] == 1
        assert project["page_number"] == 1
        assert project["chunk_text"] == 1
        assert project["score"] == 1

        # Should explicitly exclude _id (set to 0)
        assert project.get("_id") == 0
