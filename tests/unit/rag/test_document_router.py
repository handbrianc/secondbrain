"""Unit tests for DocumentRouter fuzzy document name matching.

Tests cover:
- Name normalization (stripping extensions, lowercasing)
- Fuzzy matching against known document names
- Source file resolution
- Caching behavior
- Edge cases (empty query, no match, single token)
"""

from unittest.mock import MagicMock

from secondbrain.rag.document_router import (
    DocumentRouter,
    _build_known_names,
    _jaccard_similarity,
    _normalize_name,
    _title_tokens,
)


class TestNormalizeName:
    """_normalize_name utility tests."""

    def test_lowercases(self) -> None:
        assert _normalize_name("VirtualBox User Manual") == "virtualbox user manual"

    def test_strips_pdf_extension(self) -> None:
        assert _normalize_name("UserManual.pdf") == "usermanual"

    def test_strips_docx_extension(self) -> None:
        assert _normalize_name("Guide.docx") == "guide"

    def test_replaces_underscores(self) -> None:
        assert _normalize_name("virtual_box_manual") == "virtual box manual"

    def test_replaces_hyphens(self) -> None:
        assert _normalize_name("virtual-box-manual") == "virtual box manual"

    def test_collapses_whitespace(self) -> None:
        assert _normalize_name("  virtual   box  ") == "virtual box"

    def test_strips_txt_extension(self) -> None:
        assert _normalize_name("readme.txt") == "readme"

    def test_strips_md_extension(self) -> None:
        assert _normalize_name("README.md") == "readme"

    def test_handles_mixed_case_with_extension(self) -> None:
        result = _normalize_name("Virtual Box User Manual.PDF")
        assert result == "virtual box user manual"


class TestBuildKnownNames:
    """_build_known_names registry construction tests."""

    def test_builds_registry_from_paths(self) -> None:
        source_files = [
            "/Users/test/docs/VirtualBox_UserManual.pdf",
            "/Users/test/docs/Proxmox_VE_Guide.pdf",
        ]
        registry = _build_known_names(source_files)
        assert "virtualbox usermanual" in registry
        assert "proxmox ve guide" in registry

    def test_registers_short_alias(self) -> None:
        source_files = ["/path/to/MyDocument.pdf"]
        registry = _build_known_names(source_files)
        # The normalized name (no ext)
        assert "mydocument" in registry
        # The basename (no ext) as short alias
        assert "MyDocument" not in registry  # not lowered
        assert "mydocument" in registry  # already captured above

    def test_empty_input_returns_empty(self) -> None:
        assert _build_known_names([]) == {}


class TestTitleTokens:
    """_title_tokens TOC-artifact cleaning."""

    def test_strips_leader_dots(self) -> None:
        result = _title_tokens("Oracle VirtualBox User Manual ....... 5")
        assert "virtualbox" in result
        assert "oracle" in result
        # The page number and dotted-leader tokens must not survive.
        assert not any("." in t for t in result)
        assert not any(t.isdigit() for t in result)

    def test_strips_trailing_punctuation(self) -> None:
        result = _title_tokens("Introducing Proxmox VE 9.1: Overview")
        assert "proxmox" in result
        assert "overview" in result

    def test_drops_short_tokens(self) -> None:
        result = _title_tokens("a very long title xyz")
        assert "xyz" not in result  # len 3 < min_len 4
        assert "long" in result


class TestJaccardSimilarity:
    """Jaccard similarity computation tests."""

    def test_exact_match(self) -> None:
        s = _jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"})
        assert s == 1.0

    def test_no_overlap(self) -> None:
        s = _jaccard_similarity({"a", "b"}, {"c", "d"})
        assert s == 0.0

    def test_partial_overlap(self) -> None:
        s = _jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        # intersection = {b,c}=2, union = {a,b,c,d}=4, j = 2/4 = 0.5
        assert s == 0.5

    def test_empty_sets(self) -> None:
        assert _jaccard_similarity(set(), {"a"}) == 0.0
        assert _jaccard_similarity({"a"}, set()) == 0.0

    def test_subset(self) -> None:
        s = _jaccard_similarity({"a", "b"}, {"a", "b", "c", "d"})
        # intersection = 2, union = 4
        assert s == 0.5


class TestDocumentRouter:
    """DocumentRouter end-to-end tests."""

    def test_known_names_injected(self) -> None:
        """Router uses injected known_names without hitting storage."""
        known = {
            "virtual box user manual": "/docs/VirtualBox.pdf",
            "proxmox ve guide": "/docs/Proxmox.pdf",
        }
        router = DocumentRouter(known_names=known)

        result = router.extract_document_name("tell me about virtual box user manual")
        assert result == "virtual box user manual"

    def test_resolve_source_file(self) -> None:
        known = {
            "virtual box user manual": "/docs/VirtualBox.pdf",
        }
        router = DocumentRouter(known_names=known)

        source = router.resolve_source_file("virtual box user manual")
        assert source == "/docs/VirtualBox.pdf"

    def test_resolve_none_returns_none(self) -> None:
        router = DocumentRouter(known_names={"doc": "/path"})
        assert router.resolve_source_file(None) is None

    def test_no_match_returns_none(self) -> None:
        known = {"proxmox ve guide": "/docs/Proxmox.pdf"}
        router = DocumentRouter(known_names=known)

        result = router.extract_document_name("what is python")
        assert result is None

    def test_fuzzy_match_virtualbox_variants(self) -> None:
        """Multiple query variants should match the same doc."""
        known = {
            "virtual box user manual": "/docs/VirtualBox.pdf",
        }
        router = DocumentRouter(known_names=known)

        # Common variants
        assert router.extract_document_name("virtualbox") is not None
        assert router.extract_document_name("virtual box") is not None
        assert router.extract_document_name("Virtual Box User Manual") is not None

    def test_fuzzy_match_proxmox(self) -> None:
        known = {
            "proxmox ve guide": "/docs/Proxmox.pdf",
        }
        router = DocumentRouter(known_names=known)

        assert router.extract_document_name("proxmox") is not None
        assert router.extract_document_name("proxmox guide") is not None

    def test_single_token_alias_matches_embedded_in_sentence(self) -> None:
        """A clean single-token alias is resolved when buried in a sentence.

        Regression: a dotted TOC-leader alias ("virtualbox......") was only
        matchable as a whole query — never inside "summarize the virtualbox
        user guide by chapter" — so the source filter fell through to None.
        A clean "virtualbox" alias must match via containment.
        """
        known = {
            "virtualbox": "/docs/UserManual.pdf",
        }
        router = DocumentRouter(known_names=known)

        assert (
            router.extract_document_name("summarize the virtualbox user guide by chapter")
            == "virtualbox"
        )

    def test_specific_doc_beats_generic_shared_token(self) -> None:
        """A specific named document wins over a generic shared filename token.

        Regression: "based on the pandascookbook what is the best way to learn
        pandas?" resolved to the "learn" token (a component of
        "...machinelearningwithpytorchandscikit-learn.pdf") instead of the
        explicitly named "pandascookbook", because containment picked the
        first among equal-token-count candidates.  The more specific (longer)
        name must win.
        """
        known = {
            "pandascookbook": "/AI Books/pandascookbook_thirdedition.pdf",
            "machine learning with pytorch and scikit learn": (
                "/AI Books/machinelearningwithpytorchandscikit-learn.pdf"
            ),
            # _build_known_names-style token alias shared by many filenames
            "learn": "/AI Books/machinelearningwithpytorchandscikit-learn.pdf",
        }
        router = DocumentRouter(known_names=known)

        result = router.extract_document_name(
            "based on the pandascookbook what is the best way to learn pandas?"
        )
        assert result == "pandascookbook", f"got {result!r}"

    def test_default_threshold(self) -> None:
        """Very low overlap should not match."""
        known = {
            "the quick brown fox": "/docs/fox.pdf",
        }
        router = DocumentRouter(known_names=known)

        result = router.extract_document_name("completely unrelated topic")
        assert result is None

    def test_list_available_documents(self) -> None:
        known = {
            "doc alpha": "/a/alpha.pdf",
            "doc beta": "/b/beta.pdf",
        }
        router = DocumentRouter(known_names=known)

        docs = router.list_available_documents()
        assert len(docs) == 2
        names = [d["name"] for d in docs]
        assert "doc alpha" in names
        assert "doc beta" in names

    def test_invalidate_cache(self) -> None:
        """After invalidation, a storage-backed router re-queries."""
        mock_storage = MagicMock()
        mock_storage.list_source_files.return_value = [
            "/path/to/DocumentA.pdf",
        ]
        router = DocumentRouter(storage=mock_storage)

        # First call — queries storage
        result1 = router.extract_document_name("document a")
        assert result1 is not None
        assert mock_storage.list_source_files.call_count == 1

        # Invalidate and add a new doc
        router.invalidate_cache()
        mock_storage.list_source_files.return_value = [
            "/path/to/DocumentA.pdf",
            "/path/to/DocumentB.pdf",
        ]

        # Second call — re-queries storage
        result2 = router.extract_document_name("document b")
        assert result2 is not None
        assert mock_storage.list_source_files.call_count == 2

    def test_empty_query_returns_none(self) -> None:
        router = DocumentRouter(known_names={"doc": "/path"})
        assert router.extract_document_name("") is None
        assert router.extract_document_name("   ") is None

    def test_caches_registry(self) -> None:
        """Registry is cached and storage is not queried repeatedly."""
        mock_storage = MagicMock()
        mock_storage.list_source_files.return_value = [
            "/path/to/TestDoc.pdf",
        ]
        router = DocumentRouter(storage=mock_storage)

        router.extract_document_name("test doc")
        router.extract_document_name("test doc again")
        router.extract_document_name("what about test doc")

        # Should only query storage once (within TTL)
        assert mock_storage.list_source_files.call_count == 1


class TestContainmentResolution:
    """A short document name fully present in a verbose query must resolve.

    Regression: "summarize index.html by chapter" failed to resolve the source
    because Jaccard penalised the short name among many query words (0.25 < 0.3)
    and the substring fallback rejected names shorter than 6 chars.  The
    containment phase matches a name whose every token appears in the query.
    """

    def test_short_filename_in_verbose_query(self) -> None:
        router = DocumentRouter(known_names={"index": "/data/index.html"})
        assert router.extract_document_name("summarize index by chapter") == "index"

    def test_filename_with_extension_mid_query(self) -> None:
        router = DocumentRouter(known_names={"index": "/data/index.html"})
        assert (
            router.extract_document_name("summarize index.html by chapter") == "index"
        )

    def test_source_scoped_when_named_in_verbose_query(self) -> None:
        router = DocumentRouter(
            known_names={
                "index": "/data/index.html",
                "ai business book": "/data/ai_book.pdf",
            }
        )
        name = router.extract_document_name("summarize index.html by chapter")
        assert router.resolve_source_file(name) == "/data/index.html"

    def test_generic_single_token_not_scoped(self) -> None:
        """A generic token like 'guide' must not scope on its own."""
        router = DocumentRouter(
            known_names={
                "guide": "/g/guide.pdf",
                "proxmox ve guide": "/p/proxmox.pdf",
            }
        )
        result = router.extract_document_name(
            "what can you tell me about the guide for this project"
        )
        assert result is None

    def test_pptx_with_hyphens_roundtrips(self) -> None:
        """Extract + resolve round-trip for a hyphenated .pptx name."""
        sources = ["/d/Claude for Daily Work - Instructor Training.pptx"]
        reg = _build_known_names(sources)
        router = DocumentRouter(known_names=reg)
        name = router.extract_document_name("Claude for Daily Work - Instructor Training")
        assert router.resolve_source_file(name) == (
            "/d/Claude for Daily Work - Instructor Training.pptx"
        )


