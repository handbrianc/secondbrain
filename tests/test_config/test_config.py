"""Tests for configuration module."""

import pytest

from secondbrain.config import Config, get_config


class TestConfigExtensionsSet:
    """Parameterized tests for Config.extensions_set variations."""

    @pytest.mark.parametrize(
        "extensions_input, expected_len, expected_members",
        [
            (None, 24, None),
            ("pdf", 1, [".pdf"]),
            ("pdf,docx", 2, [".pdf", ".docx"]),
            ("", 0, []),
            ("pdf,pdf", 1, [".pdf"]),
            ("pdf, docx", 2, [".pdf", ".docx"]),
        ],
    )
    def test_extensions_set_parametrized(
        self, extensions_input, expected_len, expected_members
    ):
        """Test extensions_set with various configuration inputs using parametrization."""
        if extensions_input is None:
            config = Config()
        else:
            config = Config(supported_extensions=extensions_input)

        extensions = config.extensions_set

        assert isinstance(extensions, set)
        assert len(extensions) == expected_len

        if expected_members is not None:
            for member in expected_members:
                assert member in extensions


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
            model="custom-model:latest",
            chunk_size=2048,
            chunk_overlap=100,
            default_top_k=10,
            embedding_dimensions=384,
        )

        assert config.mongo_uri == "mongodb://custom:27017"
        assert config.mongo_db == "custom_db"
        assert config.mongo_collection == "custom_collection"
        assert config.model == "custom-model:latest"
        assert config.chunk_size == 2048
        assert config.chunk_overlap == 100
        assert config.default_top_k == 10
        assert config.embedding_dimensions == 384

    @pytest.mark.parametrize(
        "updates, expected",
        [
            ({"mongo_uri": "http://invalid:27017"}, "mongo_uri must start"),
            (
                {"chunk_size": 100, "chunk_overlap": 100},
                "chunk_overlap must be less than",
            ),
            ({"chunk_overlap": -10}, "chunk_overlap must be non-negative"),
            ({"embedding_dimensions": 0}, "embedding_dimensions must be positive"),
            ({"default_top_k": 0}, "default_top_k must be positive"),
            ({"chunk_size": 0}, "chunk_size must be positive"),
        ],
    )
    def test_config_validation_errors(self, updates, expected) -> None:
        """Test that config validation raises errors for invalid values."""
        base = {
            "mongo_uri": "mongodb://localhost:27017",
            "chunk_size": 64,
            "chunk_overlap": 16,
            "embedding_dimensions": 128,
            "default_top_k": 8,
        }
        config_kwargs = {**base, **updates}
        with pytest.raises(ValueError, match=expected):
            Config(**config_kwargs)

    def test_get_config_reloads_after_cache_clear(self) -> None:
        """Test get_config can reload after cache clear."""
        get_config.cache_clear()

        config1 = get_config()
        get_config.cache_clear()

        config2 = get_config()
        assert config1 is not config2

    def test_config_validation_chunk_size(self) -> None:
        """Test chunk_size must be positive."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            Config(chunk_size=0)

    def test_embedding_cache_size_validation_valid(self) -> None:
        """Test valid embedding_cache_size values."""
        # Test default value
        config = Config(
            mongo_uri="mongodb://localhost:27017",
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
        )
        assert config.embedding_cache_size == 1000

        # Test custom values
        config = Config(
            mongo_uri="mongodb://localhost:27017",
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_cache_size=500,
        )
        assert config.embedding_cache_size == 500

        # Test zero (disables cache)
        config = Config(
            mongo_uri="mongodb://localhost:27017",
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_cache_size=0,
        )
        assert config.embedding_cache_size == 0

    def test_embedding_cache_size_validation_invalid(self) -> None:
        """Test embedding_cache_size validation for negative values."""
        with pytest.raises(
            ValueError, match="embedding_cache_size must be non-negative"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_cache_size=-1,
            )

    def test_embedding_batch_size_validation_valid(self) -> None:
        """Test valid embedding_batch_size values."""
        # Test default value
        config = Config(
            mongo_uri="mongodb://localhost:27017",
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
        )
        assert config.embedding_batch_size == 20

        # Test custom values
        config = Config(
            mongo_uri="mongodb://localhost:27017",
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_batch_size=50,
        )
        assert config.embedding_batch_size == 50

        # Test boundary values
        config = Config(
            mongo_uri="mongodb://localhost:27017",
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_batch_size=1,
        )
        assert config.embedding_batch_size == 1

        config = Config(
            mongo_uri="mongodb://localhost:27017",
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_batch_size=100,
        )
        assert config.embedding_batch_size == 100

    def test_embedding_batch_size_validation_invalid(self) -> None:
        """Test embedding_batch_size validation for invalid values."""
        # Test zero
        with pytest.raises(
            ValueError, match="embedding_batch_size must be between 1 and 100"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_batch_size=0,
            )

        # Test negative
        with pytest.raises(
            ValueError, match="embedding_batch_size must be between 1 and 100"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_batch_size=-5,
            )

        # Test too large
        with pytest.raises(
            ValueError, match="embedding_batch_size must be between 1 and 100"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_batch_size=101,
            )
