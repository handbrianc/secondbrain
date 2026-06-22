import re
from datetime import datetime
from typing import Any

import pytest


@pytest.mark.qualitative
@pytest.mark.hallucination
class TestCitationValidation:
    @pytest.mark.hallucination
    def test_citation_source_must_exist_in_chunks(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        test_cases = citation_templates.get("test_cases", [])

        for case in test_cases:
            input_data = case.get("input", {})
            source_type = input_data.get("type", "")

            if source_type in ("book", "journal", "pdf"):
                assert input_data.get("title"), (
                    f"Citation {case['id']} must have a title"
                )
                assert input_data.get("author") or input_data.get("authors"), (
                    f"Citation {case['id']} must have author(s)"
                )

    @pytest.mark.hallucination
    def test_citation_page_numbers_must_be_valid(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        test_cases = citation_templates.get("test_cases", [])

        for case in test_cases:
            input_data = case.get("input", {})

            if "pages" in input_data:
                pages = input_data["pages"]

                if isinstance(pages, str):
                    assert re.match(r"^\d+(-\d+)?$", pages), (
                        f"Citation {case['id']} has invalid page format: {pages}"
                    )
                elif isinstance(pages, int):
                    assert pages > 0, (
                        f"Citation {case['id']} has invalid page number: {pages}"
                    )

    @pytest.mark.hallucination
    def test_citation_document_references_must_be_complete(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        required_fields_by_type = {
            "book": ["title", "year", "publisher"],
            "journal": ["title", "year", "journal"],
            "webpage": ["title", "url"],
            "pdf": ["title", "url"],
        }

        author_required_by_type = {
            "book": True,
            "journal": True,
            "webpage": False,
            "pdf": False,
        }

        test_cases = citation_templates.get("test_cases", [])

        for case in test_cases:
            input_data = case.get("input", {})
            source_type = input_data.get("type", "")

            if source_type in required_fields_by_type:
                required = required_fields_by_type[source_type]
                for field in required:
                    assert field in input_data, (
                        f"Citation {case['id']} missing required field: {field}"
                    )

                if author_required_by_type.get(source_type, False):
                    has_author = "author" in input_data or (
                        "authors" in input_data
                        and len(input_data.get("authors", [])) > 0
                    )
                    assert has_author, f"Citation {case['id']} must have author(s)"
                    assert has_author, f"Citation {case['id']} must have author(s)"

    @pytest.mark.hallucination
    def test_citation_no_fabricated_authors(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        test_cases = citation_templates.get("test_cases", [])

        for case in test_cases:
            input_data = case.get("input", {})

            authors = input_data.get("authors", [])
            if not authors:
                authors = (
                    [input_data.get("author", "")] if input_data.get("author") else []
                )

            for author in authors:
                assert author and len(author.strip()) > 0, (
                    f"Citation {case['id']} has empty author name"
                )

                assert not re.match(r"^Test.*User$", author, re.IGNORECASE), (
                    f"Citation {case['id']} has fabricated author: {author}"
                )

                assert not re.match(r"^Example.*Name$", author, re.IGNORECASE), (
                    f"Citation {case['id']} has placeholder author: {author}"
                )

    @pytest.mark.hallucination
    def test_citation_urls_must_be_valid_format(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        url_pattern = re.compile(
            r"^https?://"
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
            r"localhost|"
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
            r"(?::\d+)?"
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        test_cases = citation_templates.get("test_cases", [])

        for case in test_cases:
            input_data = case.get("input", {})

            if "url" in input_data:
                url = input_data["url"]
                assert url_pattern.match(url), (
                    f"Citation {case['id']} has invalid URL format: {url}"
                )

    @pytest.mark.hallucination
    def test_citation_year_must_be_reasonable(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        current_year = datetime.now().year
        min_reasonable_year = 1450

        test_cases = citation_templates.get("test_cases", [])

        for case in test_cases:
            input_data = case.get("input", {})

            if "year" in input_data:
                year = input_data["year"]
                assert isinstance(year, int), (
                    f"Citation {case['id']} year must be integer"
                )
                assert min_reasonable_year <= year <= current_year + 1, (
                    f"Citation {case['id']} has unreasonable year: {year}"
                )

    @pytest.mark.hallucination
    def test_citation_no_duplicate_sources(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        test_cases = citation_templates.get("test_cases", [])

        source_keys = {}
        for case in test_cases:
            input_data = case.get("input", {})
            title = input_data.get("title", "")
            author = input_data.get(
                "author",
                input_data.get("authors", [""])[0] if input_data.get("authors") else "",
            )

            if title and author:
                source_key = f"{title}:{author}"
                assert source_key not in source_keys, (
                    f"Duplicate source found: {source_key} "
                    f"(first in {source_keys[source_key]}, now in {case['id']})"
                )
                source_keys[source_key] = case["id"]

    @pytest.mark.hallucination
    def test_citation_format_matches_expected_style(
        self,
        citation_templates: dict[str, Any],
    ) -> None:
        test_cases = citation_templates.get("test_cases", [])

        for case in test_cases:
            expected = case.get("expected", {})
            input_data = case.get("input", {})

            if "apa" in expected:
                apa_format = expected["apa"]
                assert isinstance(apa_format, str), "APA format must be a string"
                assert "(" in apa_format and ")" in apa_format, (
                    f"APA format {case['id']} should contain parentheses for year"
                )

            if "mla" in expected:
                mla_format = expected["mla"]
                assert isinstance(mla_format, str), "MLA format must be a string"

            if "ieee" in expected:
                ieee_format = expected["ieee"]
                assert isinstance(ieee_format, str), "IEEE format must be a string"
                assert ieee_format.startswith("["), (
                    f"IEEE format {case['id']} should start with bracket"
                )


@pytest.mark.qualitative
@pytest.mark.hallucination
class TestFeatureInvention:
    def test_detects_invented_api_endpoints(self) -> None:
        actual_endpoints = {
            "/api/search",
            "/api/ingest",
            "/api/chat",
            "/api/health",
            "/api/status",
            "/api/documents",
            "/api/documents/{id}",
        }

        claimed_endpoints = {
            "/api/search",
            "/api/ingest",
            "/api/analytics",
            "/api/export",
        }

        fabricated = [ep for ep in claimed_endpoints if ep not in actual_endpoints]

        assert len(fabricated) == 2, (
            f"Should detect 2 fabricated endpoints: {fabricated}"
        )
        assert "/api/analytics" in fabricated
        assert "/api/export" in fabricated

    def test_detects_invented_config_options(self) -> None:
        actual_config_options = {
            "SECONDBRAIN_MONGO_URI",
            "SECONDBRAIN_LOCAL_EMBEDDING_MODEL",
            "SECONDBRAIN_CHUNK_SIZE",
            "SECONDBRAIN_MAX_WORKERS",
            "SECONDBRAIN_RATE_LIMIT_ENABLED",
            "SECONDBRAIN_CIRCUIT_BREAKER_ENABLED",
            "SECONDBRAIN_LOG_LEVEL",
            "SECONDBRAIN_LOG_FORMAT",
        }

        claimed_config = {
            "SECONDBRAIN_MONGO_URI",
            "SECONDBRAIN_CHUNK_SIZE",
            "SECONDBRAIN_SECRET_KEY",
            "SECONDBRAIN_API_TOKEN",
        }

        fabricated = [opt for opt in claimed_config if opt not in actual_config_options]

        assert len(fabricated) == 2, (
            f"Should detect 2 fabricated config options: {fabricated}"
        )
        assert "SECONDBRAIN_SECRET_KEY" in fabricated
        assert "SECONDBRAIN_API_TOKEN" in fabricated

    def test_detects_invented_cli_commands(self) -> None:
        actual_commands = {
            "ingest",
            "search",
            "chat",
            "ls",
            "health",
            "status",
        }

        claimed_commands = {
            "ingest",
            "search",
            "export",
            "backup",
            "sync",
        }

        fabricated = [cmd for cmd in claimed_commands if cmd not in actual_commands]

        assert len(fabricated) == 3, (
            f"Should detect 3 fabricated commands: {fabricated}"
        )
        assert "export" in fabricated
        assert "backup" in fabricated
        assert "sync" in fabricated

    def test_detects_invented_api_parameters(self) -> None:
        actual_search_params = {
            "query",
            "top_k",
            "source_filter",
            "file_type_filter",
        }

        claimed_params = {
            "query",
            "top_k",
            "max_results",
            "filter_type",
        }

        fabricated = [p for p in claimed_params if p not in actual_search_params]

        assert len(fabricated) == 2, f"Should detect 2 fabricated params: {fabricated}"
        assert "max_results" in fabricated
        assert "filter_type" in fabricated

    def test_detects_invented_error_codes(self) -> None:
        actual_errors = {
            "DocumentNotFoundError",
            "SearchError",
            "ConfigurationError",
            "EmbeddingError",
            "StorageError",
            "ValidationError",
        }

        claimed_errors = {
            "DocumentNotFoundError",
            "SearchError",
            "DatabaseConnectionError",
            "ModelError",
        }

        fabricated = [e for e in claimed_errors if e not in actual_errors]

        assert len(fabricated) == 2, f"Should detect 2 fabricated errors: {fabricated}"
        assert "DatabaseConnectionError" in fabricated
        assert "ModelError" in fabricated

    def test_detects_invented_library_versions(self) -> None:
        min_versions = {
            "click": "8.1.0",
            "pymongo": "4.6.0",
            "motor": "3.0.0",
            "rich": "14.0.0",
            "pydantic": "2.0.0",
        }

        claimed_versions = {
            "click": "8.1.0",
            "pymongo": "4.6.0",
            "motor": "1.0.0",
            "rich": "14.0.0",
        }

        violations = []
        for lib, version in claimed_versions.items():
            if lib in min_versions:
                min_ver = min_versions[lib]
                if version < min_ver:
                    violations.append((lib, version, min_ver))

        assert len(violations) == 1, f"Should detect 1 version violation: {violations}"
        assert violations[0][0] == "motor"
        assert violations[0][1] == "1.0.0"

    def test_detects_invented_integration_capabilities(self) -> None:
        actual_integrations = {
            "MongoDB",
            "OpenAI",
            "Anthropic",
            "docling",
        }

        claimed_integrations = {
            "MongoDB",
            "OpenAI",
            "Anthropic",
            "Pinecone",
            "Weaviate",
            "docling",
        }

        fabricated = [i for i in claimed_integrations if i not in actual_integrations]

        assert len(fabricated) == 2, (
            f"Should detect 2 fabricated integrations: {fabricated}"
        )
        assert "Pinecone" in fabricated
        assert "Weaviate" in fabricated


@pytest.mark.qualitative
@pytest.mark.hallucination
class TestGroundedness:
    def test_all_claims_must_have_source_context(self) -> None:
        response_with_sources = {
            "answer": "MongoDB supports vector search.",
            "sources": [
                {
                    "chunk_id": "doc1_chunk3",
                    "snippet": "MongoDB 7.0+ includes vector search...",
                },
            ],
        }

        response_without_sources = {
            "answer": "MongoDB supports vector search.",
            "sources": [],
        }

        assert len(response_with_sources["sources"]) > 0, (
            "Response must include source citations"
        )
        assert response_with_sources["sources"][0].get("chunk_id"), (
            "Each source must have chunk_id"
        )

    def test_no_external_knowledge_without_citation(self) -> None:
        retrieved_context = "MongoDB supports vector search through Atlas."

        response_from_context = {
            "claim": "MongoDB supports vector search.",
            "supported_by_context": True,
            "context_match": retrieved_context,
        }

        response_from_external = {
            "claim": "MongoDB was founded in 2007.",
            "supported_by_context": False,
            "reason": "Information from external knowledge",
        }

        assert response_from_context["supported_by_context"], (
            "Claims from context must be marked as supported"
        )
        assert not response_from_external["supported_by_context"], (
            "External knowledge must be flagged"
        )

    def test_claim_to_context_mapping_is_accurate(self) -> None:
        context = """
        SecondBrain is a local document intelligence CLI tool.
        It uses OpenAI-compatible embeddings.
        MongoDB stores the vector data.
        The system supports PDF, DOCX, and HTML formats.
        """

        claims_with_context = [
            ("SecondBrain is a CLI tool", True),
            ("Uses OpenAI-compatible embeddings", True),
            ("MongoDB stores vectors", True),
            ("Supports PDF format", True),
            ("Supports XML format", False),
            ("Uses PostgreSQL", False),
        ]

        for claim, should_be_supported in claims_with_context:
            is_supported = any(
                claim.lower() in context.lower().replace("\n", " ") for _ in [1]
            )

            if not should_be_supported:
                assert not is_supported or claim not in context, (
                    f"Claim '{claim}' should not be supported by context"
                )

    def test_no_hallucinated_statistics(self) -> None:
        context = "Testing shows 95% accuracy on benchmark datasets."

        supported_statistic = {
            "claim": "95% accuracy",
            "source": context,
            "verified": True,
        }

        hallucinated_statistic = {
            "claim": "99.9% accuracy",
            "source": None,
            "verified": False,
        }

        assert supported_statistic["verified"], (
            "Statistics from context must be verified"
        )
        assert not hallucinated_statistic["verified"], (
            "Unsubstantiated statistics must be flagged"
        )

    def test_context_completeness_check(self) -> None:
        minimal_context = "MongoDB is a database."

        claim = "MongoDB supports vector search with cosine similarity."

        is_sufficient = claim.lower() in minimal_context.lower()

        assert not is_sufficient, "Minimal context should not support detailed claim"

        complete_context = """
        MongoDB 7.0+ supports vector search using cosine similarity.
        The vectorSearch stage enables approximate nearest neighbor search.
        """

        is_sufficient = (
            "vector search" in complete_context.lower()
            and "cosine similarity" in complete_context.lower()
        )

        assert is_sufficient, "Complete context should support the claim"

    def test_no_contradictory_claims_within_response(self) -> None:
        consistent_response = {
            "claims": [
                "MongoDB is a document database.",
                "MongoDB uses BSON for data storage.",
                "MongoDB supports horizontal scaling via sharding.",
            ],
        }

        contradictory_response = {
            "claims": [
                "MongoDB is a relational database.",
                "MongoDB is a document database.",
            ],
        }

        relational = any(
            "relational" in c.lower() for c in consistent_response["claims"]
        )
        document = any("document" in c.lower() for c in consistent_response["claims"])

        assert not (relational and document), (
            "Consistent response should not contradict"
        )

        rel_count = sum(
            1 for c in contradictory_response["claims"] if "relational" in c.lower()
        )
        doc_count = sum(
            1 for c in contradictory_response["claims"] if "document" in c.lower()
        )

        assert rel_count > 0 and doc_count > 0, (
            "Contradictory response should be detected"
        )


@pytest.mark.qualitative
@pytest.mark.hallucination
class TestFaithfulness:
    def test_no_contradiction_with_source(self) -> None:
        source_text = "Python 3.11 was released in October 2022."

        faithful_answer = "Python 3.11 was released in October 2022."
        contradictory_answer = "Python 3.11 was released in 2023."

        assert source_text.lower() == faithful_answer.lower(), (
            "Faithful answer should match source"
        )
        assert source_text.lower() != contradictory_answer.lower(), (
            "Contradictory answer should differ from source"
        )

    def test_semantic_equivalence_preserved(self) -> None:
        source = "The system processes documents in parallel using multiple workers."

        valid_paraphrases = [
            "Documents are processed in parallel with multiple workers.",
            "Multiple workers enable parallel document processing.",
        ]

        contradictory_paraphrases = [
            "Documents are processed sequentially, one at a time.",
            "Single-threaded processing is used for documents.",
        ]

        for paraphrase in valid_paraphrases:
            has_parallel = "parallel" in paraphrase.lower()
            has_workers = "worker" in paraphrase.lower()
            has_documents = "document" in paraphrase.lower()

            assert has_parallel and has_workers and has_documents, (
                f"Paraphrase should preserve key semantics: {paraphrase}"
            )

        for paraphrase in contradictory_paraphrases:
            has_sequential = (
                "sequential" in paraphrase.lower() or "single" in paraphrase.lower()
            )

            assert has_sequential, f"Paraphrase contradicts source: {paraphrase}"

    def test_no_addition_of_unsupported_details(self) -> None:
        source = "The CLI supports semantic search over documents."

        faithful_response = "The CLI supports semantic search over documents."

        hallucinated_response = (
            "The CLI supports semantic search over documents with 99% accuracy "
            "using the all-MiniLM-L6-v2 model."
        )

        assert "99% accuracy" not in faithful_response, (
            "Faithful response should not add unsupported statistics"
        )

        has_unsupported_detail = (
            "99% accuracy" in hallucinated_response and "99% accuracy" not in source
        )

        assert has_unsupported_detail, "Hallucinated response adds unsupported details"

    def test_maintains_original_scope_and_boundaries(self) -> None:
        source = "SecondBrain supports PDF, DOCX, and HTML document formats."

        faithful_scope = "SecondBrain supports PDF, DOCX, and HTML formats."

        overgeneralized = "SecondBrain supports all major document formats including PDF, DOCX, HTML, RTF, and TXT."

        assert "RTF" not in faithful_scope and "TXT" not in faithful_scope, (
            "Faithful scope should not add unsupported formats"
        )

        unsupported_formats = ["RTF", "TXT"]
        has_overgeneralization = any(
            fmt in overgeneralized for fmt in unsupported_formats
        )

        assert has_overgeneralization, (
            "Overgeneralized response includes unsupported formats"
        )
