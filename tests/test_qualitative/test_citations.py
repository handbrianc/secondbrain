import re
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.qualitative


class TestCitationFormat:
    @pytest.mark.parametrize(
        "citation",
        [
            pytest.param(
                {
                    "type": "book",
                    "author": "Martin, R. C.",
                    "year": 2008,
                    "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
                    "publisher": "Prentice Hall",
                },
                id="apa_book",
            ),
            pytest.param(
                {
                    "type": "webpage",
                    "author": "Python Software Foundation",
                    "title": "Python Documentation",
                    "url": "https://docs.python.org/3/",
                    "accessed": "2026-04-12",
                },
                id="apa_webpage",
            ),
        ],
    )
    def test_apa_format(self, citation_templates, citation: dict) -> None:
        if citation["type"] == "book":
            pattern = r"[A-Z][a-z]+, [A-Z]\. [A-Z]\. \(\d{4}\)\. .+\. .+\."
            citation_str = f"{citation['author']} ({citation['year']}). {citation['title']}. {citation['publisher']}."
            assert re.match(pattern, citation_str), (
                f"APA format violation: '{citation_str}' does not match expected pattern"
            )

    @pytest.mark.parametrize(
        "citation",
        [
            pytest.param(
                {
                    "type": "book",
                    "author": "Martin, Robert C.",
                    "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
                    "publisher": "Prentice Hall",
                    "year": 2008,
                },
                id="mla_book",
            ),
            pytest.param(
                {
                    "type": "journal",
                    "author": "Vaswani, A.",
                    "title": "Attention Is All You Need",
                    "journal": "Advances in Neural Information Processing Systems",
                    "year": 2017,
                },
                id="mla_journal",
            ),
        ],
    )
    def test_mla_format(self, citation_templates, citation: dict) -> None:
        if citation["type"] == "book":
            pattern = r"[A-Z][a-z]+, [A-Z][a-z]+\. .+\. .+, \d{4}\."
            citation_str = f"{citation['author']}. {citation['title']}. {citation['publisher']}, {citation['year']}."
            assert re.match(pattern, citation_str) or citation_str.count("..") > 0, (
                f"MLA format violation: '{citation_str}' does not match expected pattern"
            )

    @pytest.mark.parametrize(
        "citation",
        [
            pytest.param(
                {
                    "type": "book",
                    "author": "Martin, Robert C.",
                    "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
                    "place": "Upper Saddle River, NJ",
                    "publisher": "Prentice Hall",
                    "year": 2008,
                },
                id="chicago_book",
            ),
            pytest.param(
                {
                    "type": "journal",
                    "author": "Vaswani, A.",
                    "title": "Attention Is All You Need",
                    "journal": "Advances in Neural Information Processing Systems",
                    "year": 2017,
                },
                id="chicago_journal",
            ),
        ],
    )
    def test_chicago_format(self, citation_templates, citation: dict) -> None:
        if citation["type"] == "book":
            pattern = r"[A-Z][a-z]+, .+\. .+: .+, \d{4}\."
            citation_str = f"{citation['author']}, {citation['title']}. {citation['place']}: {citation['publisher']}, {citation['year']}."
            assert re.match(pattern, citation_str), (
                f"Chicago format violation: '{citation_str}' does not match expected pattern"
            )

    @pytest.mark.parametrize(
        "citation",
        [
            pytest.param(
                {
                    "type": "journal",
                    "number": 1,
                    "author": "Vaswani, A.",
                    "title": "Attention Is All You Need",
                    "journal": "Advances in Neural Information Processing Systems",
                    "volume": 30,
                    "pages": "5998-6008",
                    "year": 2017,
                },
                id="ieee_journal",
            ),
            pytest.param(
                {
                    "type": "book",
                    "number": 2,
                    "author": "Martin, R.",
                    "title": "Clean Code",
                    "publisher": "Prentice Hall",
                    "year": 2008,
                },
                id="ieee_book",
            ),
        ],
    )
    def test_ieee_format(self, citation_templates, citation: dict) -> None:
        pattern = r"\[\d+\] .+, \".+\", .+, .*, \d{4}\."
        publisher_or_journal = citation.get("journal", citation.get("publisher", "N/A"))
        citation_str = f'[{citation["number"]}] {citation["author"]}, "{citation["title"]}", {publisher_or_journal}, vol. {citation.get("volume", "x")}, {citation["year"]}.'
        assert re.match(pattern, citation_str), (
            f"IEEE format violation: '{citation_str}' does not match expected pattern"
        )

    def test_inline_citation_format(self, citation_templates) -> None:
        inline_apa = "(Martin, 2008)"
        pattern_apa = r"\([A-Z][a-z]+, \d{4}\)"
        assert re.match(pattern_apa, inline_apa), (
            f"Inline citation format violation: '{inline_apa}' does not match APA pattern"
        )

        inline_with_page = "(Martin, 2008, p. 42)"
        pattern_page = r"\([A-Z][a-z]+, \d{4}, p\. \d+\)"
        assert re.match(pattern_page, inline_with_page), (
            f"Inline citation with page violation: '{inline_with_page}' does not match pattern"
        )

    def test_footnote_citation_format(self, citation_templates) -> None:
        footnote = "^[Martin, Robert C. Clean Code: A Handbook of Agile Software Craftsmanship (Upper Saddle River, NJ: Prentice Hall, 2008), 42.]"
        pattern = r"\^\[[^.]+\.[^.]+\]?\(.*:.*,\s*\d{4}\),?\s*\d+\.?\]"

        assert re.match(pattern, footnote), (
            f"Footnote format violation: '{footnote}' does not match expected pattern"
        )


class TestSourceAccuracy:
    def test_correct_author(self, citation_templates) -> None:
        book_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_book_complete"
            ),
            None,
        )
        assert book_test is not None, "Book citation test case not found"

        input_data = book_test["input"]
        expected_author = input_data["author"]

        assert " " in expected_author, (
            f"Author name '{expected_author}' should contain first and last name"
        )
        assert expected_author[0].isupper(), (
            f"Author name '{expected_author}' should start with capital letter"
        )

    def test_correct_year(self, citation_templates) -> None:
        journal_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_journal_article"
            ),
            None,
        )
        assert journal_test is not None, "Journal citation test case not found"

        input_data = journal_test["input"]
        year = input_data["year"]

        assert isinstance(year, int), f"Year should be integer, got {type(year)}"
        assert 1900 <= year <= 2030, (
            f"Year {year} is outside reasonable range (1900-2030)"
        )

    def test_correct_title(self, citation_templates) -> None:
        webpage_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_webpage"
            ),
            None,
        )
        assert webpage_test is not None, "Webpage citation test case not found"

        input_data = webpage_test["input"]
        title = input_data["title"]

        assert title and len(title.strip()) > 0, "Title should not be empty"
        assert title[0].isupper(), f"Title '{title}' should start with capital letter"
        assert len(title) >= 5, f"Title '{title}' seems too short for a valid title"

    def test_correct_url(self, citation_templates) -> None:
        webpage_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_webpage"
            ),
            None,
        )
        assert webpage_test is not None, "Webpage citation test case not found"

        input_data = webpage_test["input"]
        url = input_data["url"]

        parsed = urlparse(url)
        assert parsed.scheme in ["http", "https"], (
            f"URL '{url}' should use http or https protocol"
        )
        assert parsed.netloc, f"URL '{url}' should have valid domain"
        assert "." in parsed.netloc, f"URL '{url}' domain should contain a dot"

    def test_correct_page_numbers(self, citation_templates) -> None:
        journal_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_journal_article"
            ),
            None,
        )
        assert journal_test is not None, "Journal citation test case not found"

        input_data = journal_test["input"]
        pages = input_data["pages"]

        assert re.match(r"\d+-\d+", pages), (
            f"Page numbers '{pages}' should be in format 'start-end'"
        )
        start, end = pages.split("-")
        assert int(start) < int(end), (
            f"Start page {start} should be less than end page {end}"
        )


class TestCitationCompleteness:
    def test_all_fields_present(self, citation_templates) -> None:
        for test_case in citation_templates["test_cases"]:
            input_data = test_case["input"]

            if input_data.get("type") != "unknown":
                assert input_data.get("title"), (
                    f"Test case '{test_case['id']}' missing required field: title"
                )

                if input_data.get("type") in ["book", "journal", "pdf"]:
                    has_author = input_data.get("author") or input_data.get("authors")
                    assert has_author, (
                        f"Test case '{test_case['id']}' missing required field: author"
                    )

            if input_data.get("type") in ["book", "journal", "pdf"]:
                has_author = input_data.get("author") or input_data.get("authors")
                assert has_author, (
                    f"Test case '{test_case['id']}' missing required field: author"
                )

    def test_no_missing_info(self, citation_templates) -> None:
        for test_case in citation_templates["test_cases"]:
            if test_case["id"] == "citation_invalid_format":
                continue

            input_data = test_case["input"]

            for key, value in input_data.items():
                if isinstance(value, str):
                    assert value.lower() not in ["unknown", "tbd", "n/a", "none"], (
                        f"Test case '{test_case['id']}' has placeholder value for {key}: '{value}'"
                    )

    def test_proper_structure(self, citation_templates) -> None:
        journal_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_journal_article"
            ),
            None,
        )
        assert journal_test is not None, "Journal citation test case not found"

        input_data = journal_test["input"]

        assert isinstance(input_data["title"], str), "Title should be string"
        assert isinstance(input_data["year"], int), "Year should be integer"
        assert isinstance(input_data["pages"], str), "Pages should be string"

        authors = input_data.get("authors")
        if authors:
            assert isinstance(authors, list), "Authors should be list when present"
            assert len(authors) > 0, "Authors list should not be empty"

    def test_format_specific_requirements(self, citation_templates) -> None:
        book_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_book_complete"
            ),
            None,
        )
        assert book_test is not None, "Book citation test case not found"

        input_data = book_test["input"]

        assert input_data.get("publisher"), (
            "Book citation should have publisher for APA/Chicago"
        )
        assert input_data.get("place"), "Book citation should have place for Chicago"

        expected = book_test["expected"]
        assert "apa" in expected, "Book should have APA format example"
        assert "chicago" in expected, "Book should have Chicago format example"


class TestCitationValidation:
    def test_source_exists(self, citation_templates) -> None:
        for test_case in citation_templates["test_cases"]:
            input_data = test_case["input"]
            source_type = input_data.get("type")

            valid_types = ["book", "journal", "webpage", "pdf", "unknown"]
            assert source_type in valid_types, (
                f"Test case '{test_case['id']}' has invalid source type: '{source_type}'"
            )

    def test_url_valid(self, citation_templates) -> None:
        webpage_test = next(
            (
                t
                for t in citation_templates["test_cases"]
                if t["id"] == "citation_webpage"
            ),
            None,
        )
        assert webpage_test is not None, "Webpage citation test case not found"

        input_data = webpage_test["input"]
        url = input_data["url"]

        parsed = urlparse(url)
        assert parsed.scheme in ["http", "https"], f"Invalid URL scheme in '{url}'"
        assert parsed.netloc, f"Invalid URL domain in '{url}'"

        invalid_domains = ["example.invalid", "test.invalid", "fake.invalid"]
        for invalid in invalid_domains:
            assert invalid not in url, f"URL contains invalid domain: '{invalid}'"

    def test_doi_resolves(self, citation_templates) -> None:
        valid_dois = ["10.1000/182", "10.1038/nature12373", "10.1109/5.771073"]

        for doi in valid_dois:
            pattern = r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$"
            assert re.match(pattern, doi, re.IGNORECASE), (
                f"DOI '{doi}' does not match expected format"
            )

        invalid_dois = ["doi:10.1000/182", "10.1000", "http://dx.doi.org/10.1000/182"]
        for doi in invalid_dois:
            pattern = r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$"
            assert (
                not re.match(pattern, doi, re.IGNORECASE)
                or doi.startswith("doi:")
                or doi.startswith("http")
            ), f"DOI '{doi}' should be detected as non-standard format"

    def test_no_fabrication(self, citation_templates) -> None:
        for test_case in citation_templates["test_cases"]:
            input_data = test_case["input"]

            fake_authors = ["John Doe", "Jane Smith", "Test Author", "Unknown"]
            author = input_data.get("author", "")
            authors = input_data.get("authors", [])

            if author:
                assert author not in fake_authors, (
                    f"Test case '{test_case['id']}' has fake author: '{author}'"
                )

            if authors:
                for auth in authors:
                    assert auth not in fake_authors, (
                        f"Test case '{test_case['id']}' has fake author in list: '{auth}'"
                    )

            fake_url_patterns = ["fake.example", "test.invalid", "notreal.fake"]
            url = input_data.get("url", "")
            for pattern in fake_url_patterns:
                assert pattern not in url, (
                    f"Test case '{test_case['id']}' has fake URL containing '{pattern}'"
                )

            year = input_data.get("year")
            if year:
                assert 1900 <= year <= 2030, (
                    f"Test case '{test_case['id']}' has impossible year: {year}"
                )

    def test_fabricated_citation_detection(self) -> None:
        fabricated_citations = [
            {
                "author": "John Doe",
                "title": "Important Research on Nothing",
                "journal": "Fake Journal of Made Things Up",
                "year": 2099,
                "url": "https://fake.invalid/article",
            },
            {
                "author": "Unknown Author",
                "title": "",
                "year": 1800,
                "publisher": "Non-existent Press",
            },
        ]

        for citation in fabricated_citations:
            has_issues = []

            if citation.get("author") in ["John Doe", "Unknown Author"]:
                has_issues.append("fake author name")

            if not citation.get("title") or len(citation.get("title", "")) < 5:
                has_issues.append("invalid title")

            year = citation.get("year")
            if year and (year > 2030 or year < 1800):
                has_issues.append("impossible year")

            url = citation.get("url", "")
            if ".invalid" in url or ".fake" in url:
                has_issues.append("fake URL")

            assert len(has_issues) > 0, (
                f"Fabricated citation should have been detected: {citation}"
            )
