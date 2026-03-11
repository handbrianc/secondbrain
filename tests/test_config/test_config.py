"""Tests for configuration module."""

import pytest

from secondbrain.config import Config, get_config


class TestConfigExtensionsSet:
    """Tests for Config.extensions_set property."""

    def test_extensions_set_returns_self(self, session_config: Config) -> None:
        """Test extensions_set returns a set."""
        extensions = session_config.extensions_set
        assert isinstance(extensions, set)

    def test_extensions_set_contains_dots(self, session_config: Config) -> None:
        """Test extensions contain leading dots."""
        extensions = session_config.extensions_set

        for ext in extensions:
            assert ext.startswith(".")

    def test_extensions_set_contains_expected_extensions(
        self, session_config: Config
    ) -> None:
        """Test extensions_set contains standard expected extensions."""
        extensions = session_config.extensions_set

        expected = {
            ".pdf",
            ".docx",
            ".pptx",
            ".xlsx",
            ".html",
            ".htm",
            ".md",
            ".txt",
            ".asciidoc",
            ".adoc",
            ".tex",
            ".csv",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".tif",
            ".bmp",
            ".webp",
            ".wav",
            ".mp3",
            ".vtt",
            ".xml",
            ".json",
        }
        assert extensions == expected

    def test_extensions_set_case_preserves(self) -> None:
        """Test extensions preserve case from configured string."""
        # Create config with mixed case extensions
        config = Config(supported_extensions="PDF,Docx,md")
        extensions = config.extensions_set

        assert ".PDF" in extensions
        assert ".Docx" in extensions
        assert ".md" in extensions

    def test_extensions_set_empty_string(self) -> None:
        """Test extensions_set handles empty string."""
        config = Config(supported_extensions="")
        extensions = config.extensions_set
        assert len(extensions) == 0

    def test_extensions_set_whitespace_handling(self) -> None:
        """Test extensions_set handles whitespace around extensions."""
        config = Config(supported_extensions="pdf, docx, md")
        extensions = config.extensions_set

        assert ".pdf" in extensions
        assert ".docx" in extensions
        assert ".md" in extensions

    def test_extensions_set_custom_extensions(self) -> None:
        """Test extensions_set with custom extensions."""
        config = Config(supported_extensions="custom1,custom2")
        extensions = config.extensions_set

        assert ".custom1" in extensions
        assert ".custom2" in extensions
        assert ".pdf" not in extensions


class TestConfig:
    """Tests for Config class."""

    def test_default_config_values(self) -> None:
        """Test default configuration values."""
        # Patch environment variables to use defaults
        import os
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {
                "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
                "SECONDBRAIN_MONGO_DB": "secondbrain",
                "SECONDBRAIN_MONGO_COLLECTION": "embeddings",
                "SECONDBRAIN_OLLAMA_URL": "http://localhost:11434",
                "SECONDBRAIN_MODEL": "embeddinggemma:latest",
                "SECONDBRAIN_CHUNK_SIZE": "4096",
                "SECONDBRAIN_CHUNK_OVERLAP": "50",
                "SECONDBRAIN_DEFAULT_TOP_K": "5",
                "SECONDBRAIN_EMBEDDING_DIMENSIONS": "768",
            },
            clear=True,
        ):
            get_config.cache_clear()
            config = Config()

            assert config.mongo_uri == "mongodb://localhost:27017"
            assert config.mongo_db == "secondbrain"
            assert config.mongo_collection == "embeddings"
            assert config.ollama_url == "http://localhost:11434"
            assert config.model == "embeddinggemma:latest"
            assert config.chunk_size == 4096
            assert config.chunk_overlap == 50
            assert config.default_top_k == 5
            assert config.embedding_dimensions == 768

    def test_custom_config_values(self) -> None:
        """Test custom configuration values."""
        config = Config(
            mongo_uri="mongodb://custom:27017",
            mongo_db="custom_db",
            mongo_collection="custom_collection",
            ollama_url="http://custom:11434",
            model="custom-model:latest",
            chunk_size=2048,
            chunk_overlap=100,
            default_top_k=10,
            embedding_dimensions=384,
        )

        assert config.mongo_uri == "mongodb://custom:27017"
        assert config.mongo_db == "custom_db"
        assert config.mongo_collection == "custom_collection"
        assert config.ollama_url == "http://custom:11434"
        assert config.model == "custom-model:latest"
        assert config.chunk_size == 2048
        assert config.chunk_overlap == 100
        assert config.default_top_k == 10
        assert config.embedding_dimensions == 384

    def test_config_validation_mongo_uri(self) -> None:
        """Test MongoDB URI validation."""
        with pytest.raises(ValueError, match="mongo_uri must start"):
            Config(mongo_uri="http://invalid:27017")

    def test_config_validation_ollama_url(self) -> None:
        """Test Ollama URL validation."""
        with pytest.raises(ValueError, match="ollama_url must be a valid URL"):
            Config(ollama_url="not-a-url")

    def test_config_validation_chunk_overlap_ge_chunk_size(self) -> None:
        """Test chunk_overlap must be less than chunk_size."""
        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            Config(chunk_size=100, chunk_overlap=100)

    def test_config_validation_chunk_overlap_negative(self) -> None:
        """Test chunk_overlap must be non-negative."""
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            Config(chunk_overlap=-10)

    def test_config_validation_embedding_dimensions(self) -> None:
        """Test embedding_dimensions must be positive."""
        with pytest.raises(ValueError, match="embedding_dimensions must be positive"):
            Config(embedding_dimensions=0)

    def test_config_validation_top_k(self) -> None:
        """Test default_top_k must be positive."""
        with pytest.raises(ValueError, match="default_top_k must be positive"):
            Config(default_top_k=0)

    def test_get_config_cache(self) -> None:
        """Test get_config returns cached instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_get_config_reloads_after_cache_clear(self) -> None:
        """Test get_config can reload after cache clear."""
        get_config.cache_clear()

        config1 = get_config()
        get_config.cache_clear()

        config2 = get_config()
        assert config1 is not config2

    def test_config_validation_ollama_url_scheme(self) -> None:
        """Test ollama_url must use http or https scheme."""
        with pytest.raises(
            ValueError, match="ollama_url must use http or https scheme"
        ):
            Config(ollama_url="ftp://invalid:11434")

    def test_config_validation_chunk_size(self) -> None:
        """Test chunk_size must be positive."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            Config(chunk_size=0)
