"""Tests for Config validators (src/secondbrain/config/).

Each test targets the real validation rules: field validators declared in the
config mixins (llm.py, embedding.py, chunking.py, processing.py, qdrant.py,
sqlite.py, rag.py) plus the cross-field ``validate_config_values`` model
validator in ``__init__.py``. Cross-field rules only fire when both fields are
explicitly provided, so the tests set both.

All tests run under the ``isolate_config_env`` fixture (no SECONDBRAIN_* env
vars, no dotenv in cwd) so constructor kwargs are the only input source.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from secondbrain.config import Config


def make_config(**kwargs) -> Config:
    """Build a Config from explicit kwargs only (env/dotenv isolated)."""
    return Config(**kwargs)


class TestCrossFieldValidation:
    """Cross-field rules from validate_config_values (model validator)."""

    @pytest.mark.parametrize(
        ("chunk_size", "chunk_overlap"),
        [(100, 100), (50, 100), (10, 11)],
    )
    def test_chunk_overlap_ge_chunk_size_rejected(self, chunk_size, chunk_overlap):
        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            make_config(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def test_chunk_overlap_just_below_chunk_size_accepted(self):
        config = make_config(chunk_size=100, chunk_overlap=99)

        assert config.chunk_overlap == 99

    @pytest.mark.parametrize("dimensions", [0, -1, -384])
    def test_embedding_dimensions_must_be_positive(self, dimensions):
        with pytest.raises(ValueError, match="embedding_dimensions must be positive"):
            make_config(embedding_dimensions=dimensions)

    @pytest.mark.parametrize("top_k", [0, -1])
    def test_default_top_k_must_be_positive(self, top_k):
        with pytest.raises(ValueError, match="default_top_k must be positive"):
            make_config(default_top_k=top_k)

    @pytest.mark.parametrize("workers", [0, -1, -8])
    def test_max_workers_zero_or_negative_rejected(self, workers):
        with pytest.raises(ValueError, match="max_workers must be positive"):
            make_config(max_workers=workers)

    def test_max_workers_none_means_auto_detect(self):
        config = make_config(max_workers=None)

        assert config.max_workers is None

    def test_max_workers_positive_accepted(self):
        config = make_config(max_workers=4)

        assert config.max_workers == 4

    @pytest.mark.parametrize("cache_size", [-1, -100])
    def test_embedding_cache_size_negative_rejected(self, cache_size):
        with pytest.raises(
            ValueError, match="embedding_cache_size must be non-negative"
        ):
            make_config(embedding_cache_size=cache_size)

    def test_embedding_cache_size_zero_disables_cache(self):
        config = make_config(embedding_cache_size=0)

        assert config.embedding_cache_size == 0

    @pytest.mark.parametrize("batch_size", [0, -1, 101, 1000])
    def test_embedding_batch_size_out_of_range_rejected(self, batch_size):
        with pytest.raises(
            ValueError, match="embedding_batch_size must be between 1 and 100"
        ):
            make_config(embedding_batch_size=batch_size)

    @pytest.mark.parametrize("batch_size", [1, 100])
    def test_embedding_batch_size_boundaries_accepted(self, batch_size):
        config = make_config(embedding_batch_size=batch_size)

        assert config.embedding_batch_size == batch_size

    @pytest.mark.parametrize("batch_size", [0, -1, 201])
    def test_streaming_chunk_batch_size_out_of_range_rejected(self, batch_size):
        with pytest.raises(
            ValueError, match="streaming_chunk_batch_size must be between 1 and 200"
        ):
            make_config(streaming_chunk_batch_size=batch_size)

    @pytest.mark.parametrize("batch_size", [1, 200])
    def test_streaming_chunk_batch_size_boundaries_accepted(self, batch_size):
        config = make_config(streaming_chunk_batch_size=batch_size)

        assert config.streaming_chunk_batch_size == batch_size

    @pytest.mark.parametrize("dtype", ["float16", "int8", "double"])
    def test_embedding_dtype_invalid_rejected(self, dtype):
        with pytest.raises(ValueError, match="embedding_dtype must be"):
            make_config(embedding_dtype=dtype)

    @pytest.mark.parametrize("dtype", ["float32", "float64"])
    def test_embedding_dtype_valid_accepted(self, dtype):
        config = make_config(embedding_dtype=dtype)

        assert config.embedding_dtype == dtype

    @pytest.mark.parametrize("fmt", ["gzip", "hex", ""])
    def test_embedding_storage_format_invalid_rejected(self, fmt):
        with pytest.raises(ValueError, match="embedding_storage_format must be"):
            make_config(embedding_storage_format=fmt)

    def test_embedding_storage_format_binary_warns_deprecation(self):
        with pytest.warns(DeprecationWarning, match="binary.*deprecated"):
            config = make_config(embedding_storage_format="binary")

        assert config.embedding_storage_format == "binary"

    def test_embedding_storage_format_array_does_not_warn(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            config = make_config(embedding_storage_format="array")

        assert config.embedding_storage_format == "array"

    @pytest.mark.parametrize("algo", ["lzma", "snappy", ""])
    def test_text_compression_algorithm_invalid_rejected(self, algo):
        with pytest.raises(ValueError, match="text_compression_algorithm must be"):
            make_config(text_compression_algorithm=algo)

    @pytest.mark.parametrize("algo", ["gzip", "brotli", "zstd"])
    def test_text_compression_algorithm_valid_accepted(self, algo):
        config = make_config(text_compression_algorithm=algo)

        assert config.text_compression_algorithm == algo

    def test_rag_chunk_preview_ge_max_context_rejected(self):
        """preview=10000 (its own max) with max_context=1000 (its own min)."""
        with pytest.raises(
            ValueError,
            match="rag_chunk_preview_chars must be less than rag_max_context_chars",
        ):
            make_config(rag_chunk_preview_chars=10000, rag_max_context_chars=1000)

    def test_rag_chunk_preview_just_below_max_context_accepted(self):
        config = make_config(rag_chunk_preview_chars=999, rag_max_context_chars=1000)

        assert config.rag_chunk_preview_chars == 999


class TestLLMValidators:
    """Field validators from config/llm.py."""

    @pytest.mark.parametrize("temp", [-0.1, -1.0, 2.1, 3.0])
    def test_llm_temperature_out_of_range_rejected(self, temp):
        with pytest.raises(ValueError, match="llm_temperature must be between"):
            make_config(llm_temperature=temp)

    @pytest.mark.parametrize("temp", [0.0, 0.3, 1.0, 2.0])
    def test_llm_temperature_boundaries_accepted(self, temp):
        config = make_config(llm_temperature=temp)

        assert config.llm_temperature == temp

    @pytest.mark.parametrize("top_p", [-0.1, 1.1, 2.0])
    def test_llm_top_p_out_of_range_rejected(self, top_p):
        with pytest.raises(ValueError, match="llm_top_p must be between"):
            make_config(llm_top_p=top_p)

    @pytest.mark.parametrize("top_p", [0.0, 0.5, 1.0])
    def test_llm_top_p_boundaries_accepted(self, top_p):
        config = make_config(llm_top_p=top_p)

        assert config.llm_top_p == top_p

    @pytest.mark.parametrize("penalty", [0.0, 0.99, -1.0])
    def test_llm_repetition_penalty_below_one_rejected(self, penalty):
        with pytest.raises(ValueError, match=r"llm_repetition_penalty must be >= 1\.0"):
            make_config(llm_repetition_penalty=penalty)

    def test_llm_repetition_penalty_one_accepted(self):
        config = make_config(llm_repetition_penalty=1.0)

        assert config.llm_repetition_penalty == 1.0

    @pytest.mark.parametrize("effort", ["ultra", "maximum", "M A X I M U M"])
    def test_llm_reasoning_effort_invalid_rejected(self, effort):
        with pytest.raises(ValueError, match="llm_reasoning_effort must be one of"):
            make_config(llm_reasoning_effort=effort)

    @pytest.mark.parametrize(
        "effort", ["minimal", "low", "medium", "high", "LOW", " Medium "]
    )
    def test_llm_reasoning_effort_valid_normalized(self, effort):
        config = make_config(llm_reasoning_effort=effort)

        assert config.llm_reasoning_effort == effort.strip().lower()

    def test_llm_reasoning_effort_blank_treated_as_unset(self):
        config = make_config(llm_reasoning_effort="   ")

        assert config.llm_reasoning_effort is None

    def test_llm_reasoning_effort_none_omits_parameter(self):
        config = make_config(llm_reasoning_effort=None)

        assert config.llm_reasoning_effort is None

    @pytest.mark.parametrize("tokens", [0, -1])
    def test_llm_max_tokens_must_be_positive(self, tokens):
        with pytest.raises(ValueError, match="llm_max_tokens must be positive"):
            make_config(llm_max_tokens=tokens)

    def test_llm_max_tokens_positive_accepted(self):
        config = make_config(llm_max_tokens=4096)

        assert config.llm_max_tokens == 4096

    @pytest.mark.parametrize("chars", [-1, -1000])
    def test_llm_max_answer_chars_negative_rejected(self, chars):
        with pytest.raises(ValueError, match="llm_max_answer_chars must be >= 0"):
            make_config(llm_max_answer_chars=chars)

    def test_llm_max_answer_chars_zero_disables_bound(self):
        config = make_config(llm_max_answer_chars=0)

        assert config.llm_max_answer_chars == 0

    @pytest.mark.parametrize("timeout", [0, -5])
    def test_llm_timeout_must_be_positive(self, timeout):
        with pytest.raises(ValueError, match="llm_timeout must be positive"):
            make_config(llm_timeout=timeout)

    def test_llm_timeout_positive_accepted(self):
        config = make_config(llm_timeout=30)

        assert config.llm_timeout == 30

    @pytest.mark.parametrize("seconds", [-1, -600])
    def test_llm_stream_idle_timeout_negative_rejected(self, seconds):
        with pytest.raises(
            ValueError, match="llm_stream_idle_timeout_seconds must be >= 0"
        ):
            make_config(llm_stream_idle_timeout_seconds=seconds)

    def test_llm_stream_idle_timeout_zero_disables_bound(self):
        config = make_config(llm_stream_idle_timeout_seconds=0)

        assert config.llm_stream_idle_timeout_seconds == 0


class TestChunkingValidators:
    """Field validators from config/chunking.py."""

    @pytest.mark.parametrize("size", [0, -1, -4096])
    def test_chunk_size_must_be_positive(self, size):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            make_config(chunk_size=size)

    @pytest.mark.parametrize("size", [2, 100, 4096])
    def test_chunk_size_positive_accepted(self, size):
        config = make_config(chunk_size=size, chunk_overlap=0)

        assert config.chunk_size == size

    def test_chunk_size_one_collides_with_default_overlap(self):
        """chunk_size=1 violates overlap<size against the default overlap (50)."""
        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            make_config(chunk_size=1)

    @pytest.mark.parametrize("overlap", [-1, -50])
    def test_chunk_overlap_negative_rejected(self, overlap):
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            make_config(chunk_overlap=overlap)

    def test_chunk_overlap_zero_accepted(self):
        config = make_config(chunk_overlap=0)

        assert config.chunk_overlap == 0

    @pytest.mark.parametrize("depth", [0, 6])
    def test_summary_depth_out_of_range_rejected(self, depth):
        with pytest.raises(Exception):  # pydantic Field ge/le bound
            make_config(summary_depth=depth)

    def test_summary_depth_boundaries_accepted(self):
        assert make_config(summary_depth=1).summary_depth == 1
        assert make_config(summary_depth=5).summary_depth == 5

    @pytest.mark.parametrize("mode", ["brief", "verbose", ""])
    def test_summarizer_mode_invalid_rejected(self, mode):
        with pytest.raises(Exception):  # pydantic Literal validation
            make_config(summarizer_mode=mode)

    @pytest.mark.parametrize("mode", ["concise", "detailed", "chapter_only"])
    def test_summarizer_mode_valid_accepted(self, mode):
        config = make_config(summarizer_mode=mode)

        assert config.summarizer_mode == mode


class TestProcessingValidators:
    """Field validators from config/processing.py."""

    @pytest.mark.parametrize("pool", ["threadpool", "asyncio", ""])
    def test_ingest_pool_invalid_rejected(self, pool):
        with pytest.raises(ValueError, match="ingest_pool must be one of"):
            make_config(ingest_pool=pool)

    def test_ingest_pool_normalized_to_lowercase(self):
        config = make_config(ingest_pool="THREAD")

        assert config.ingest_pool == "thread"

    @pytest.mark.parametrize("threads", [0, -1])
    def test_pdf_num_threads_must_be_at_least_one(self, threads):
        with pytest.raises(ValueError, match="pdf_num_threads must be >= 1"):
            make_config(pdf_num_threads=threads)

    def test_pdf_num_threads_positive_accepted(self):
        config = make_config(pdf_num_threads=1)

        assert config.pdf_num_threads == 1

    @pytest.mark.parametrize("device", ["gpu", "tpu", ""])
    def test_pdf_accelerator_device_invalid_rejected(self, device):
        with pytest.raises(ValueError, match="pdf_accelerator_device must be one of"):
            make_config(pdf_accelerator_device=device)

    def test_pdf_accelerator_device_normalized_to_lowercase(self):
        config = make_config(pdf_accelerator_device="XPU")

        assert config.pdf_accelerator_device == "xpu"

    @pytest.mark.parametrize("processes", [-1, -100])
    def test_max_ingest_processes_negative_rejected(self, processes):
        with pytest.raises(ValueError, match="max_ingest_processes must be >= 0"):
            make_config(max_ingest_processes=processes)

    def test_max_ingest_processes_zero_means_unlimited(self):
        config = make_config(max_ingest_processes=0)

        assert config.max_ingest_processes == 0

    @pytest.mark.parametrize("batch_size", [0, -1])
    def test_pdf_layout_batch_size_must_be_at_least_one(self, batch_size):
        with pytest.raises(ValueError, match="pdf_layout_batch_size must be >= 1"):
            make_config(pdf_layout_batch_size=batch_size)

    @pytest.mark.parametrize("scale", [0.0, -1.0])
    def test_pdf_images_scale_must_be_positive(self, scale):
        with pytest.raises(ValueError, match="pdf_images_scale must be > 0"):
            make_config(pdf_images_scale=scale)

    @pytest.mark.parametrize("model", ["whisper_large_v3", "whisper", "gpt-4o"])
    def test_audio_asr_model_requires_s2t_preset(self, model):
        with pytest.raises(ValueError, match="audio_asr_model must be a WhisperS2T"):
            make_config(audio_asr_model=model)

    @pytest.mark.parametrize(
        "model", ["whisper_tiny_s2t", "whisper_large_v3_turbo_s2t", "WHISPER_TINY_S2T"]
    )
    def test_audio_asr_model_s2t_presets_accepted(self, model):
        config = make_config(audio_asr_model=model)

        assert config.audio_asr_model == model.lower()


class TestStorageValidators:
    """Field validators from config/qdrant.py and config/sqlite.py."""

    @pytest.mark.parametrize("backend", ["postgres", "weaviate", ""])
    def test_storage_backend_invalid_rejected(self, backend):
        with pytest.raises(ValueError, match="storage_backend must be one of"):
            make_config(storage_backend=backend)

    def test_storage_backend_normalized_to_lowercase(self):
        config = make_config(storage_backend="MOCK")

        assert config.storage_backend == "mock"

    def test_storage_backend_mock_accepted(self):
        config = make_config(storage_backend="mock")

        assert config.storage_backend == "mock"

    @pytest.mark.parametrize("path", ["", "   "])
    def test_sqlite_path_empty_rejected(self, path):
        with pytest.raises(ValueError, match="sqlite_path must be a non-empty path"):
            make_config(sqlite_path=path)

    def test_sqlite_path_expands_user(self):
        config = make_config(sqlite_path="~/secondbrain-test.db")

        assert config.sqlite_path == str(Path("~/secondbrain-test.db").expanduser())

    def test_sqlite_path_plain_relative_accepted(self):
        config = make_config(sqlite_path="data/conversations.db")

        assert config.sqlite_path == "data/conversations.db"


class TestRagValidators:
    """Field and model validators from config/rag.py."""

    @pytest.mark.parametrize("window", [0, -1])
    def test_rag_context_window_must_be_positive(self, window):
        with pytest.raises(ValueError, match="rag_context_window must be positive"):
            make_config(rag_context_window=window)

    def test_rag_context_window_positive_accepted(self):
        config = make_config(rag_context_window=1)

        assert config.rag_context_window == 1

    @pytest.mark.parametrize("chars", [999, 500001])
    def test_rag_max_context_chars_out_of_range_rejected(self, chars):
        """Rejected by the Field ge/le bounds (1000..500000)."""
        with pytest.raises(ValidationError):
            make_config(rag_max_context_chars=chars)

    def test_rag_max_context_chars_at_lower_bound_hits_cross_field_check(self):
        """max_context=1000 collides with the default preview (1200) >= 1000."""
        with pytest.raises(
            ValueError,
            match="rag_chunk_preview_chars must be less than rag_max_context_chars",
        ):
            make_config(rag_max_context_chars=1000)

    def test_rag_max_context_chars_boundaries_accepted(self):
        high = make_config(rag_max_context_chars=500000)

        assert high.rag_max_context_chars == 500000

        low = make_config(rag_max_context_chars=1000, rag_chunk_preview_chars=500)

        assert low.rag_max_context_chars == 1000

    @pytest.mark.parametrize("chars", [99, 10001])
    def test_rag_chunk_preview_chars_out_of_range_rejected(self, chars):
        """Rejected by the Field ge/le bounds (100..10000)."""
        with pytest.raises(ValidationError):
            make_config(rag_chunk_preview_chars=chars)

    @pytest.mark.parametrize("chars", [100, 1200, 10000])
    def test_rag_chunk_preview_chars_boundaries_accepted(self, chars):
        config = make_config(
            rag_chunk_preview_chars=chars, rag_max_context_chars=500000
        )

        assert config.rag_chunk_preview_chars == chars

    def test_scoped_threshold_defaults_below_global(self):
        """Default scoped threshold (0.20) < global default (0.46)."""
        config = make_config()

        assert config.rag_min_similarity_threshold == 0.46
        assert config.rag_scoped_min_similarity_threshold == 0.20

    def test_scoped_threshold_follows_lower_global_when_unset(self):
        """Unset scoped threshold tracks a lowered global threshold."""
        config = make_config(rag_min_similarity_threshold=0.1)

        assert config.rag_scoped_min_similarity_threshold == 0.1

    def test_explicit_scoped_threshold_at_or_above_global_rejected(self):
        with pytest.raises(
            ValueError,
            match="rag_scoped_min_similarity_threshold must be less than",
        ):
            make_config(
                rag_min_similarity_threshold=0.4,
                rag_scoped_min_similarity_threshold=0.4,
            )

    def test_explicit_scoped_threshold_below_global_accepted(self):
        config = make_config(
            rag_min_similarity_threshold=0.4,
            rag_scoped_min_similarity_threshold=0.2,
        )

        assert config.rag_scoped_min_similarity_threshold == 0.2

    def test_explicit_zero_scoped_with_zero_global_accepted(self):
        """Zero/zero is the documented exception to the below-global rule."""
        config = make_config(
            rag_min_similarity_threshold=0.0,
            rag_scoped_min_similarity_threshold=0.0,
        )

        assert config.rag_scoped_min_similarity_threshold == 0.0
