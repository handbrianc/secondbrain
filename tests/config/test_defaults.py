"""Tests for Config provider/model defaults and derived properties.

Asserts the real shipped defaults from the config mixins (llm.py,
embedding.py, chunking.py, processing.py, qdrant.py, sqlite.py, rag.py) and
the ``extensions_set`` helper property on ``Config``.

All tests run under the ``isolate_config_env`` fixture (no SECONDBRAIN_* env
vars, no dotenv in cwd), so defaults are read from the field definitions.
"""

from pathlib import Path

from secondbrain.config import Config


class TestLLMDefaults:
    """Defaults from config/llm.py."""

    def test_llm_provider_and_model(self):
        config = Config()

        assert config.llm_provider == "openai"
        assert config.llm_model == "gpt-4o-mini"

    def test_llm_generation_defaults(self):
        config = Config()

        assert config.llm_temperature == 0.3
        assert config.llm_top_p == 0.95
        assert config.llm_repetition_penalty == 1.0
        assert config.llm_reasoning_effort is None

    def test_llm_bounds_defaults(self):
        config = Config()

        assert config.llm_max_tokens == 384000
        assert config.llm_max_answer_chars == 24000
        assert config.llm_timeout == 120
        assert config.llm_stream_idle_timeout_seconds == 600

    def test_openai_credentials_default_unset(self):
        config = Config()

        assert config.openai_api_key is None
        assert config.openai_base_url is None


class TestEmbeddingDefaults:
    """Defaults from config/embedding.py."""

    def test_embedding_provider_and_model(self):
        config = Config()

        assert config.embedding_provider == "openai"
        assert config.embedding_model == "text-embedding-3-small"

    def test_embedding_dimensions(self):
        config = Config()

        assert config.embedding_dimensions == 1536

    def test_embedding_operation_defaults(self):
        config = Config()

        assert config.embedding_batch_size == 100
        assert config.embedding_timeout == 300
        assert config.embedding_cache_size == 1000
        assert config.embedding_dtype == "float32"
        assert config.embedding_storage_format == "array"

    def test_credentials_and_rate_limit_default_unset(self):
        config = Config()

        assert config.embedding_api_key is None
        assert config.embedding_api_base is None
        assert config.rate_limit_enabled is False


class TestSearchDefaults:
    """Search-related defaults (config/embedding.py + config/rag.py)."""

    def test_default_top_k(self):
        config = Config()

        assert config.default_top_k == 50


class TestChunkingDefaults:
    """Defaults from config/chunking.py."""

    def test_chunking_defaults(self):
        config = Config()

        assert config.chunk_size == 4096
        assert config.chunk_overlap == 50
        assert config.summarizer_mode == "concise"
        assert config.summary_depth == 1
        assert config.adaptive_chunking is False

    def test_supported_extensions_default(self):
        config = Config()

        assert "pdf" in config.supported_extensions
        assert "md" in config.supported_extensions
        assert "docx" in config.supported_extensions


class TestStorageDefaults:
    """Defaults from config/qdrant.py and config/sqlite.py."""

    def test_qdrant_defaults(self):
        config = Config()

        assert config.storage_backend == "qdrant"
        assert config.qdrant_url == "http://localhost:6333"
        assert config.qdrant_collection == "embeddings"
        assert config.qdrant_api_key is None

    def test_sqlite_default_path_expands_user(self):
        config = Config()

        assert config.sqlite_path == str(
            Path("~/.secondbrain/secondbrain.db").expanduser()
        )


class TestRagDefaults:
    """Defaults from config/rag.py."""

    def test_rag_pipeline_defaults(self):
        config = Config()

        assert config.rag_context_window == 5
        assert config.rag_max_retries == 3
        assert config.rag_llm_fallback_enabled is True

    def test_rag_threshold_defaults(self):
        config = Config()

        assert config.rag_min_similarity_threshold == 0.46
        # Scoped threshold defaults below the global threshold.
        assert config.rag_scoped_min_similarity_threshold == 0.20
        assert (
            config.rag_scoped_min_similarity_threshold
            < config.rag_min_similarity_threshold
        )

    def test_rag_context_size_defaults(self):
        config = Config()

        assert config.rag_max_context_chars == 16000
        assert config.rag_chunk_preview_chars == 1200

    def test_rag_system_prompt_default_mentions_context_only(self):
        config = Config()

        assert "context" in config.rag_system_prompt.lower()
        assert config.rag_system_prompt  # non-empty


class TestProcessingDefaults:
    """Defaults from config/processing.py."""

    def test_ingestion_defaults(self):
        config = Config()

        assert config.max_file_size_bytes == 100 * 1024 * 1024
        assert config.max_workers is None  # auto-detect
        assert config.ingest_pool == "process"
        assert config.streaming_enabled is True
        assert config.streaming_chunk_batch_size == 150

    def test_pdf_defaults(self):
        config = Config()

        assert config.pdf_accelerator_device == "auto"
        assert config.pdf_num_threads == 4
        assert config.pdf_ocr_enabled is False
        assert config.pdf_fast_text_enabled is True

    def test_compression_defaults(self):
        config = Config()

        assert config.text_compression_enabled is False
        assert config.text_compression_algorithm == "gzip"


class TestExtensionsSet:
    """Config.extensions_set: comma-list -> dotted extension set."""

    def test_default_extensions_are_dotted(self):
        config = Config()
        extensions = config.extensions_set

        assert ".pdf" in extensions
        assert ".md" in extensions
        assert ".txt" in extensions
        assert all(ext.startswith(".") for ext in extensions)

    def test_input_without_leading_dots_gets_dots(self):
        config = Config(supported_extensions="pdf,docx")

        assert config.extensions_set == {".pdf", ".docx"}

    def test_leading_dots_are_normalized_without_doubling(self):
        config = Config(supported_extensions=".md,.txt")

        assert config.extensions_set == {".md", ".txt"}

    def test_whitespace_around_entries_is_stripped(self):
        config = Config(supported_extensions=" pdf , docx ")

        assert config.extensions_set == {".pdf", ".docx"}

    def test_duplicates_collapse_into_set(self):
        config = Config(supported_extensions="pdf,pdf,docx")

        assert config.extensions_set == {".pdf", ".docx"}

    def test_empty_entries_are_dropped(self):
        config = Config(supported_extensions="pdf,,")

        assert config.extensions_set == {".pdf"}
