"""Unit tests for the ``summarize`` CLI command and its formatters."""

import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli.summarize import (
    _format_chapter_summary,
    _format_section_summary,
)


def _chapter_result(summary: str = "text") -> SimpleNamespace:
    return SimpleNamespace(
        chapter_id=3,
        chapter_title="Chapter 3",
        summary=summary,
        chunk_count=2,
        token_budget_used=100,
    )


def _section_result(summary: str = "text") -> SimpleNamespace:
    return SimpleNamespace(
        section_id="3.9",
        section_title="Section 3.9",
        summary=summary,
        belongs_to_chapter=3,
        token_budget_used=100,
    )


class TestFormatChapterSummary:
    def test_default_title_renders_plain_heading(self) -> None:
        out = _format_chapter_summary(_chapter_result("body"), tokens_used=100)
        assert "[bold cyan]Chapter 3[/bold cyan]" in out
        assert "Chapter 3:" not in out
        assert "body" in out

    def test_custom_title_renders_heading_with_title(self) -> None:
        result = _chapter_result()
        result.chapter_title = "Backpropagation"
        out = _format_chapter_summary(result, tokens_used=100)
        assert "[bold cyan]Chapter 3: Backpropagation[/bold cyan]" in out

    def test_tokens_and_chunks_rendered(self) -> None:
        out = _format_chapter_summary(_chapter_result(), tokens_used=77)
        assert "Chunks processed: 2" in out
        assert "Tokens used: 77" in out


class TestFormatSectionSummary:
    def test_renders_section_heading_chapter_and_tokens(self) -> None:
        out = _format_section_summary(_section_result("section body"), 55)
        assert "Section 3.9: Section 3.9" in out
        assert "Part of Chapter 3" in out
        assert "section body" in out
        assert "Tokens used: 55" in out


def _factory_patches():
    """Patch the three factories at their source modules."""
    return (
        patch(
            "secondbrain.rag.providers.LLMProviderFactory.create_from_config",
            return_value=MagicMock(),
        ),
        patch(
            "secondbrain.embedding.EmbeddingProviderFactory.create_from_config",
            return_value=MagicMock(),
        ),
        patch("secondbrain.storage.StorageFactory.create_from_config"),
    )


class TestSummarizeCommand:
    def _invoke(self, args):
        from secondbrain.cli import cli

        return CliRunner().invoke(cli, ["summarize", *args])

    def test_by_section_without_chapter_exits_1(self) -> None:
        result = self._invoke(["--by-section"])
        assert result.exit_code == 1
        assert "requires --chapter" in result.output

    def test_section_id_without_by_section_exits_1(self) -> None:
        result = self._invoke(["--chapter", "2", "--section-id", "2.1"])
        assert result.exit_code == 1
        assert "requires --by-section" in result.output

    def test_neither_chapter_nor_by_section_exits_1(self) -> None:
        result = self._invoke([])
        assert result.exit_code == 1
        assert "Must specify --chapter or use --by-section" in result.output

    def test_chapter_happy_path(self) -> None:
        mock_config = MagicMock()
        mock_config.llm_max_tokens = 512
        mock_config.llm_model = "test-model"
        mock_config.rag_max_context_chars = 16000
        chapter = _chapter_result("A fine summary.")
        with ExitStack() as stack:
            stack.enter_context(
                patch("secondbrain.cli.summarize.config", return_value=mock_config)
            )
            mock_summ_cls = stack.enter_context(
                patch("secondbrain.document.summarizer.Summarizer")
            )
            for factory_patch in _factory_patches():
                stack.enter_context(factory_patch)
            mock_summ_cls.return_value.summarize_by_chapter = AsyncMock(
                return_value=chapter
            )
            result = self._invoke(["--chapter", "3"])

        assert result.exit_code == 0
        assert "A fine summary." in result.output
        assert "Chapter 3" in result.output
        assert "Chunks processed: 2" in result.output
        assert "Tokens used: 100" in result.output

    def test_section_happy_path(self) -> None:
        mock_config = MagicMock()
        mock_config.llm_max_tokens = 512
        mock_config.llm_model = None
        mock_config.rag_max_context_chars = 16000
        section = _section_result("Section text.")
        with ExitStack() as stack:
            stack.enter_context(
                patch("secondbrain.cli.summarize.config", return_value=mock_config)
            )
            mock_summ_cls = stack.enter_context(
                patch("secondbrain.document.summarizer.Summarizer")
            )
            for factory_patch in _factory_patches():
                stack.enter_context(factory_patch)
            mock_summ_cls.return_value.summarize_by_section = AsyncMock(
                return_value=section
            )
            result = self._invoke(["--chapter", "3", "--by-section", "-s", "3.9"])

        assert result.exit_code == 0
        assert "Section text." in result.output
        assert "Section 3.9" in result.output
        assert "Part of Chapter 3" in result.output

    def test_empty_summary_reports_no_content(self) -> None:
        mock_config = MagicMock()
        mock_config.llm_max_tokens = 512
        mock_config.llm_model = None
        mock_config.rag_max_context_chars = 16000
        with ExitStack() as stack:
            stack.enter_context(
                patch("secondbrain.cli.summarize.config", return_value=mock_config)
            )
            mock_summ_cls = stack.enter_context(
                patch("secondbrain.document.summarizer.Summarizer")
            )
            for factory_patch in _factory_patches():
                stack.enter_context(factory_patch)
            mock_summ_cls.return_value.summarize_by_chapter = AsyncMock(
                return_value=_chapter_result(summary="")
            )
            result = self._invoke(["--chapter", "9"])

        assert result.exit_code == 0
        assert "No content found" in result.output

    def test_summarizer_wired_from_config_values(self) -> None:
        mock_config = MagicMock()
        mock_config.llm_max_tokens = 1024
        mock_config.llm_model = "m"
        mock_config.rag_max_context_chars = 8000
        with ExitStack() as stack:
            stack.enter_context(
                patch("secondbrain.cli.summarize.config", return_value=mock_config)
            )
            mock_summ_cls = stack.enter_context(
                patch("secondbrain.document.summarizer.Summarizer")
            )
            for factory_patch in _factory_patches():
                stack.enter_context(factory_patch)
            mock_summ_cls.return_value.summarize_by_chapter = AsyncMock(
                return_value=_chapter_result()
            )
            result = self._invoke(["--chapter", "1"])

        assert result.exit_code == 0
        kwargs = mock_summ_cls.call_args[1]
        assert kwargs["max_summary_tokens"] == 1024
        assert kwargs["summary_model"] == "m"
        assert kwargs["max_input_chars"] == 8000

    def test_storage_closed_after_run(self) -> None:
        mock_config = MagicMock()
        mock_config.llm_max_tokens = 512
        mock_config.llm_model = None
        mock_config.rag_max_context_chars = 16000
        storage = MagicMock()
        llm_patch, emb_patch, sto_patch = _factory_patches()
        with ExitStack() as stack:
            stack.enter_context(
                patch("secondbrain.cli.summarize.config", return_value=mock_config)
            )
            mock_summ_cls = stack.enter_context(
                patch("secondbrain.document.summarizer.Summarizer")
            )
            stack.enter_context(llm_patch)
            stack.enter_context(emb_patch)
            mock_storage_factory = stack.enter_context(sto_patch)
            mock_storage_factory.return_value = storage
            mock_summ_cls.return_value.summarize_by_chapter = AsyncMock(
                return_value=_chapter_result()
            )
            result = self._invoke(["--chapter", "1"])

        assert result.exit_code == 0
        storage.close.assert_called_once()


def test_async_run_uses_asyncio_run() -> None:
    """The command body runs via ``asyncio.run`` (regression guard)."""
    import secondbrain.cli.summarize as mod

    mock_config = MagicMock()
    mock_config.llm_max_tokens = 512
    mock_config.llm_model = None
    mock_config.rag_max_context_chars = 16000
    with ExitStack() as stack:
        stack.enter_context(
            patch("secondbrain.cli.summarize.config", return_value=mock_config)
        )
        mock_summ_cls = stack.enter_context(
            patch("secondbrain.document.summarizer.Summarizer")
        )
        stack.enter_context(patch("asyncio.run", wraps=asyncio.run))
        for factory_patch in _factory_patches():
            stack.enter_context(factory_patch)
        mock_summ_cls.return_value.summarize_by_chapter = AsyncMock(
            return_value=_chapter_result()
        )
        result = CliRunner().invoke(mod.cli, ["summarize", "--chapter", "1"])

    assert result.exit_code == 0
    mock_summ_cls.return_value.summarize_by_chapter.assert_awaited_once()
