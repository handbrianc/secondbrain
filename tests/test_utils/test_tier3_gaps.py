"""Tier-3 coverage: factory branches, validators, and small stragglers."""

import logging

import pytest
from pydantic import ValidationError

from secondbrain.types import _validate_chunk_info, _validate_search_result
from secondbrain.utils.rate_limiter import SharedRateLimiter


class TestLLMProviderFactoryAnthropic:
    """Anthropic branch + unsupported-provider error in LLMProviderFactory."""

    def test_create_anthropic_provider_from_config(self):
        from unittest.mock import MagicMock, patch

        from secondbrain.rag.providers.factory import LLMProviderFactory

        cfg = MagicMock()
        cfg.llm_provider = "anthropic"
        cfg.llm_model = "claude-3"
        cfg.llm_temperature = 0.2
        cfg.llm_top_p = 0.9
        cfg.llm_max_tokens = 512
        cfg.llm_timeout = 30

        with patch(
            "secondbrain.rag.providers.anthropic.AnthropicLLMProvider"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            provider = LLMProviderFactory.create_from_config(cfg)

        assert provider is mock_cls.return_value
        mock_cls.assert_called_once_with(
            model="claude-3",
            temperature=0.2,
            top_p=0.9,
            max_tokens=512,
            timeout=30,
        )

    def test_create_unsupported_llm_provider_raises(self):
        from unittest.mock import MagicMock

        from secondbrain.rag.providers.factory import LLMProviderFactory

        cfg = MagicMock()
        cfg.llm_provider = "banana"

        with pytest.raises(ValueError, match="Unsupported LLM provider: banana"):
            LLMProviderFactory.create_from_config(cfg)


class TestTypedDictValidators:
    """Runtime validation gates in secondbrain.types."""

    def test_validate_chunk_info_passes_through_valid(self):
        d = {"chunk_id": "c1", "source_file": "a.pdf", "chunk_text": "x", "page_number": 1}
        assert _validate_chunk_info(d) is d

    @pytest.mark.parametrize("missing", ["chunk_id", "source_file", "chunk_text", "page_number"])
    def test_validate_chunk_info_rejects_missing_key(self, missing: str):
        d = {"chunk_id": "c1", "source_file": "a.pdf", "chunk_text": "x", "page_number": 1}
        del d[missing]
        with pytest.raises(TypeError, match="missing required key"):
            _validate_chunk_info(d)

    def test_validate_search_result_passes_through_valid(self):
        d = {"chunk_id": "c1", "source_file": "a.pdf", "chunk_text": "x", "page_number": 2, "score": 0.9}
        assert _validate_search_result(d) is d

    @pytest.mark.parametrize(
        "missing", ["chunk_id", "source_file", "chunk_text", "page_number"]
    )
    def test_validate_search_result_rejects_missing_key(self, missing: str):
        d = {"chunk_id": "c1", "source_file": "a.pdf", "chunk_text": "x", "page_number": 2}
        del d[missing]
        with pytest.raises(TypeError, match="missing required key"):
            _validate_search_result(d)


class TestConfigValidators:
    """Error branches of config field validators."""

    def _cfg(self, **overrides):
        from secondbrain.config import Config

        base = {"openai_api_key": "k"}
        base.update(overrides)
        return Config(**base)

    def test_chunk_size_must_be_positive(self):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            self._cfg(chunk_size=0)

    def test_chunk_overlap_must_be_non_negative(self):
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            self._cfg(chunk_overlap=-1)

    def test_llm_top_p_bounds(self):
        with pytest.raises(ValueError, match="llm_top_p must be between"):
            self._cfg(llm_top_p=1.5)

    def test_llm_repetition_penalty_lower_bound(self):
        with pytest.raises(ValueError, match=r"llm_repetition_penalty must be >= 1\.0"):
            self._cfg(llm_repetition_penalty=0.5)

    def test_llm_reasoning_effort_blank_is_unset(self):
        assert self._cfg(llm_reasoning_effort="  ").llm_reasoning_effort is None

    def test_llm_reasoning_effort_invalid_raises(self):
        with pytest.raises(ValueError, match="llm_reasoning_effort must be one of"):
            self._cfg(llm_reasoning_effort="turbo")

    def test_llm_max_tokens_positive(self):
        with pytest.raises(ValueError, match="llm_max_tokens must be positive"):
            self._cfg(llm_max_tokens=0)

    def test_llm_max_answer_chars_non_negative(self):
        with pytest.raises(ValueError, match="llm_max_answer_chars must be >= 0"):
            self._cfg(llm_max_answer_chars=-1)

    def test_llm_timeout_positive(self):
        with pytest.raises(ValueError, match="llm_timeout must be positive"):
            self._cfg(llm_timeout=0)

    def test_llm_stream_idle_timeout_non_negative(self):
        with pytest.raises(
            ValueError, match="llm_stream_idle_timeout_seconds must be >= 0"
        ):
            self._cfg(llm_stream_idle_timeout_seconds=-1)

    def test_embedding_cache_size_non_negative(self):
        with pytest.raises(ValueError, match="embedding_cache_size must be non-negative"):
            self._cfg(embedding_cache_size=-1)

    def test_embedding_batch_size_bounds(self):
        with pytest.raises(
            ValueError, match="embedding_batch_size must be between 1 and 100"
        ):
            self._cfg(embedding_batch_size=101)

    def test_cross_field_validations(self):
        with pytest.raises(ValueError, match="chunk_overlap must be less than"):
            self._cfg(chunk_size=10, chunk_overlap=10)
        with pytest.raises(ValueError, match="embedding_dimensions must be positive"):
            self._cfg(embedding_dimensions=0)
        with pytest.raises(ValueError, match="default_top_k must be positive"):
            self._cfg(default_top_k=0)
        with pytest.raises(ValueError, match="max_workers must be positive"):
            self._cfg(max_workers=0)
        with pytest.raises(ValueError, match="rag_chunk_preview_chars must be less"):
            self._cfg(rag_chunk_preview_chars=10000, rag_max_context_chars=10000)

    def test_binary_storage_format_warns_deprecation(self):
        with pytest.warns(DeprecationWarning, match="embedding_storage_format"):
            self._cfg(embedding_storage_format="binary")

    def test_storage_backend_validation(self):
        with pytest.raises(ValueError, match="storage_backend must be one of"):
            self._cfg(storage_backend="redis")

    def test_rag_context_window_positive(self):
        with pytest.raises(ValueError, match="rag_context_window must be positive"):
            self._cfg(rag_context_window=0)

    def test_rag_max_context_chars_bounds(self):
        with pytest.raises(ValidationError):
            self._cfg(rag_max_context_chars=999)
        with pytest.raises(ValidationError):
            self._cfg(rag_max_context_chars=500001)

    def test_rag_chunk_preview_chars_bounds(self):
        with pytest.raises(ValidationError):
            self._cfg(rag_chunk_preview_chars=50)
        with pytest.raises(ValidationError):
            self._cfg(rag_chunk_preview_chars=10001)

    def test_sqlite_path_empty_rejected_and_expands_home(self):
        with pytest.raises(ValueError, match="non-empty path"):
            self._cfg(sqlite_path="   ")
        assert "~" not in self._cfg(sqlite_path="~/x.db").sqlite_path

    def test_streaming_chunk_batch_size_bounds(self):
        with pytest.raises(
            ValueError, match="streaming_chunk_batch_size must be between 1 and 200"
        ):
            self._cfg(streaming_chunk_batch_size=0)

    def test_extensions_set_normalizes(self):
        cfg = self._cfg(supported_extensions="pdf, .docx, md")
        assert cfg.extensions_set == {".pdf", ".docx", ".md"}


class TestRateLimiterTimeout:
    """wait_and_acquire timeout path."""

    def test_wait_and_acquire_times_out(self):
        limiter = SharedRateLimiter(max_requests=1, window_seconds=10)
        assert limiter.acquire() is True

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("secondbrain.utils.rate_limiter.time.monotonic", lambda: 0.0)
            mp.setattr("secondbrain.utils.rate_limiter.time.sleep", lambda s: None)
            assert limiter.wait_and_acquire(timeout=0.0) is False


class TestLoggerWarnings:
    """Processor storage-failure warning path (lines 354-361)."""

    def test_existing_text_hashes_storage_failure_returns_empty(
        self, monkeypatch, caplog
    ):
        from secondbrain.document import processor

        def _boom():
            raise RuntimeError("storage down")

        monkeypatch.setattr(
            "secondbrain.storage.StorageFactory.create_from_config", _boom
        )

        with caplog.at_level(logging.WARNING):
            result = processor._existing_text_hashes(["h1", "h2"])

        assert result == set()
        assert "storage down" in caplog.text
