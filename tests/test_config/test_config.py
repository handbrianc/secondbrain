"""Tests for configuration module."""

import pytest

from secondbrain.config import Config, get_config

# Get test config
_test_config = Config()


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
                "SECONDBRAIN_MONGO_URI": _test_config.mongo_uri,
                "SECONDBRAIN_MONGO_DB": "secondbrain_test",
                "SECONDBRAIN_MONGO_COLLECTION": "embeddings_test",
                "SECONDBRAIN_LOCAL_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
                "SECONDBRAIN_CHUNK_SIZE": "4096",
                "SECONDBRAIN_CHUNK_OVERLAP": "50",
                "SECONDBRAIN_DEFAULT_TOP_K": "5",
                "SECONDBRAIN_EMBEDDING_DIMENSIONS": "768",
            },
            clear=True,
        ):
            get_config.cache_clear()
            config = Config()

            assert config.mongo_uri == _test_config.mongo_uri
            assert config.mongo_db == "secondbrain_test"
            assert config.mongo_collection == "embeddings_test"
            assert config.local_embedding_model == "all-MiniLM-L6-v2"
            assert config.chunk_size == 4096
            assert config.chunk_overlap == 50
            assert config.default_top_k == 5
            assert config.embedding_dimensions == 768

    def test_custom_config_values(self) -> None:
        """Test custom configuration values."""
        config = Config(
            mongo_uri=_test_config.mongo_uri,
            mongo_db="custom_db",
            mongo_collection="custom_collection",
            local_embedding_model="custom-model:latest",
            chunk_size=2048,
            chunk_overlap=100,
            default_top_k=10,
            embedding_dimensions=384,
        )

        assert config.mongo_uri == _test_config.mongo_uri
        assert config.mongo_db == "custom_db"
        assert config.mongo_collection == "custom_collection"
        assert config.local_embedding_model == "custom-model:latest"
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
            "mongo_uri": _test_config.mongo_uri,
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
            mongo_uri=_test_config.mongo_uri,
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
        )
        assert config.embedding_cache_size == 1000

        # Test custom values
        config = Config(
            mongo_uri=_test_config.mongo_uri,
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_cache_size=500,
        )
        assert config.embedding_cache_size == 500

        # Test zero (disables cache)
        config = Config(
            mongo_uri=_test_config.mongo_uri,
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
                mongo_uri=_test_config.mongo_uri,
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
            mongo_uri=_test_config.mongo_uri,
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
        )
        assert config.embedding_batch_size == 20

        # Test custom values
        config = Config(
            mongo_uri=_test_config.mongo_uri,
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_batch_size=50,
        )
        assert config.embedding_batch_size == 50

        # Test boundary values
        config = Config(
            mongo_uri=_test_config.mongo_uri,
            chunk_size=64,
            chunk_overlap=16,
            embedding_dimensions=128,
            default_top_k=8,
            embedding_batch_size=1,
        )
        assert config.embedding_batch_size == 1

        config = Config(
            mongo_uri=_test_config.mongo_uri,
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
                mongo_uri=_test_config.mongo_uri,
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
                mongo_uri=_test_config.mongo_uri,
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
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_batch_size=101,
            )


class TestPreloadEnv:
    """Tests for preload_env function."""

    def test_preload_env_no_env_file(self, tmp_path, monkeypatch) -> None:
        """Test preload_env when no .env file exists."""
        import os

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from secondbrain.config import preload_env

        # Should not raise
        preload_env()


    def test_preload_env_test_env_with_env_test(self, tmp_path, monkeypatch) -> None:
        """Test preload_env in test mode loads from .env.test."""
        import os

        env_test = tmp_path / ".env.test"
        env_test.write_text("TEST_VAR=test_value\n")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")

        from secondbrain.config import preload_env

        preload_env()

        assert os.getenv("TEST_VAR") == "test_value"


    def test_preload_env_production_with_env(self, tmp_path, monkeypatch) -> None:
        """Test preload_env in production mode loads from .env."""
        import os

        env_file = tmp_path / ".env"
        env_file.write_text("PROD_VAR=prod_value\n")

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from secondbrain.config import preload_env

        preload_env()

        assert os.getenv("PROD_VAR") == "prod_value"


    def test_preload_env_test_overrides_existing(self, tmp_path, monkeypatch) -> None:
        """Test that test mode overrides existing environment variables."""
        import os

        env_test = tmp_path / ".env.test"
        env_test.write_text("OVERRIDE_VAR=new_value\n")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")
        monkeypatch.setenv("OVERRIDE_VAR", "old_value")

        from secondbrain.config import preload_env

        preload_env()

        assert os.getenv("OVERRIDE_VAR") == "new_value"


    def test_preload_env_production_ignores_existing(self, tmp_path, monkeypatch) -> None:
        """Test that production mode doesn't override existing environment variables."""
        import os

        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_VAR=file_value\n")

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("EXISTING_VAR", "env_value")

        from secondbrain.config import preload_env

        preload_env()

        # Should keep env value, not file value
        assert os.getenv("EXISTING_VAR") == "env_value"


    def test_preload_env_handles_comments_and_quotes(self, tmp_path, monkeypatch) -> None:
        """Test that preload_env correctly handles comments and quotes."""
        import os

        env_test = tmp_path / ".env.test"
        env_test.write_text(
            'QUOTED_VAR="quoted value" # inline comment\n'
            "SINGLE_QUOTED='single quoted'\n"
            "COMMENT_VAR=value # this is a comment\n"
        )

        # Change to temp directory
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")

        from secondbrain.config import preload_env

        preload_env()

        assert os.getenv("QUOTED_VAR") == "quoted value"
        assert os.getenv("SINGLE_QUOTED") == "single quoted"
        assert os.getenv("COMMENT_VAR") == "value"


class TestValidateMongoUri:
    """Tests for _validate_mongo_uri function."""

    def test_validate_mongo_uri_valid(self) -> None:
        """Test valid MongoDB URIs are accepted."""
        from secondbrain.config import _validate_mongo_uri

        # Test mongodb://
        result = _validate_mongo_uri("mongodb://localhost:27017/test")
        assert result == "mongodb://localhost:27017/test"

        # Test mongodb+srv://
        result = _validate_mongo_uri("mongodb+srv://cluster.mongodb.net/test")
        assert result == "mongodb+srv://cluster.mongodb.net/test"


    def test_validate_mongo_uri_invalid(self) -> None:
        """Test invalid MongoDB URIs raise ValueError."""
        from secondbrain.config import _validate_mongo_uri

        with pytest.raises(
            ValueError, match="mongo_uri must start with 'mongodb://"
        ):
            _validate_mongo_uri("http://localhost:27017/test")

        with pytest.raises(
            ValueError, match="mongo_uri must start with 'mongodb://"
        ):
            _validate_mongo_uri("postgres://localhost/test")


class TestConfigModelValidator:
    """Tests for Config model_validator settings."""

    def test_model_validator_no_env_file(self, tmp_path, monkeypatch) -> None:
        """Test model_validator when no .env file exists."""
        from secondbrain.config import Config

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        # Config should use defaults when no .env file
        config = Config(mongo_uri=_test_config.mongo_uri)
        assert config.mongo_db == "secondbrain_test"
        assert config.mongo_collection == "embeddings_test"

    def test_model_validator_test_env_defaults(self, tmp_path, monkeypatch) -> None:
        """Test model_validator sets test defaults in test environment."""
        from secondbrain.config import Config

        # Create .env.test but don't set mongo_db/collection
        env_test = tmp_path / ".env.test"
        env_test.write_text("SECONDBRAIN_LOCAL_EMBEDDING_MODEL=test_model\n")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")

        # Config should use test defaults for mongo_db and mongo_collection
        config = Config(mongo_uri=_test_config.mongo_uri)
        assert config.mongo_db == "secondbrain_test"
        assert config.mongo_collection == "embeddings_test"


class TestConfigAdditionalValidations:
    """Tests for additional model_validator validations."""

    def test_max_workers_zero(self) -> None:
        """Test max_workers validation with zero value."""
        with pytest.raises(ValueError, match="max_workers must be positive when set"):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                max_workers=0,
            )

    def test_streaming_chunk_batch_size_zero(self) -> None:
        """Test streaming_chunk_batch_size validation with zero value."""
        with pytest.raises(
            ValueError, match="streaming_chunk_batch_size must be between 1 and 200"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                streaming_chunk_batch_size=0,
            )

    def test_streaming_chunk_batch_size_too_large(self) -> None:
        """Test streaming_chunk_batch_size validation with value > 200."""
        with pytest.raises(
            ValueError, match="streaming_chunk_batch_size must be between 1 and 200"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                streaming_chunk_batch_size=201,
            )

    def test_embedding_dtype_invalid(self) -> None:
        """Test embedding_dtype validation with invalid value."""
        with pytest.raises(
            ValueError, match="embedding_dtype must be 'float32' or 'float64'"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_dtype="float16",
            )

    def test_embedding_storage_format_invalid(self) -> None:
        """Test embedding_storage_format validation with invalid value."""
        with pytest.raises(
            ValueError, match="embedding_storage_format must be 'binary' or 'array'"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_storage_format="invalid",
            )

    def test_text_compression_algorithm_invalid(self) -> None:
        """Test text_compression_algorithm validation with invalid value."""
        with pytest.raises(
            ValueError, match="text_compression_algorithm must be 'gzip', 'brotli', or 'zstd'"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                text_compression_algorithm="invalid",
            )



class TestConfigFunction:
    """Tests for config() convenience wrapper."""

    def test_config_convenience_wrapper(self) -> None:
        """Test that config() returns a Config instance."""
        from secondbrain.config import config

        result = config()
        assert isinstance(result, Config)


class TestConfigFieldValidators:
    """Tests for Config field validators."""

    def test_validate_chunk_size_zero(self, tmp_path, monkeypatch) -> None:
        """Test chunk_size validation with zero value."""
        from secondbrain.config import Config

        with pytest.raises(ValueError, match="chunk_size must be positive"):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=0,
            )


    def test_validate_chunk_overlap_negative(self, tmp_path, monkeypatch) -> None:
        """Test chunk_overlap validation with negative value."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="chunk_overlap must be non-negative"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=-1,
            )


    def test_validate_embedding_cache_size_negative(self, tmp_path, monkeypatch) -> None:
        """Test embedding_cache_size validation with negative value."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="embedding_cache_size must be non-negative"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_cache_size=-1,
            )


    def test_validate_embedding_batch_size_zero(self, tmp_path, monkeypatch) -> None:
        """Test embedding_batch_size validation with zero value."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="embedding_batch_size must be between 1 and 100"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_batch_size=0,
            )


    def test_validate_streaming_chunk_batch_size_zero(self, tmp_path, monkeypatch) -> None:
        """Test streaming_chunk_batch_size validation with zero value."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="streaming_chunk_batch_size must be between 1 and 200"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                streaming_chunk_batch_size=0,
            )


    def test_validate_llm_temperature_negative(self, tmp_path, monkeypatch) -> None:
        """Test llm_temperature validation with negative value."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="llm_temperature must be between 0.0 and 2.0"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                llm_temperature=-0.1,
            )


    def test_validate_llm_temperature_too_high(self, tmp_path, monkeypatch) -> None:
        """Test llm_temperature validation with value > 2.0."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="llm_temperature must be between 0.0 and 2.0"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                llm_temperature=2.1,
            )


    def test_validate_llm_max_tokens_zero(self, tmp_path, monkeypatch) -> None:
        """Test llm_max_tokens validation with zero value."""
        from secondbrain.config import Config

        with pytest.raises(ValueError, match="llm_max_tokens must be positive"):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                llm_max_tokens=0,
            )


    def test_validate_llm_timeout_zero(self, tmp_path, monkeypatch) -> None:
        """Test llm_timeout validation with zero value."""
        from secondbrain.config import Config

        with pytest.raises(ValueError, match="llm_timeout must be positive"):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                llm_timeout=0,
            )


    def test_validate_rag_context_window_zero(self, tmp_path, monkeypatch) -> None:
        """Test rag_context_window validation with zero value."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="rag_context_window must be positive"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                rag_context_window=0,
            )


class TestConfigModelValidatorAdditional:
    """Tests for Config model_validator additional validations."""

    def test_validate_chunk_overlap_less_than_chunk_size(self, tmp_path, monkeypatch) -> None:
        """Test chunk_overlap must be less than chunk_size."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=32,
                chunk_overlap=64,  # greater than chunk_size
            )


    def test_validate_embedding_dimensions_positive(self, tmp_path, monkeypatch) -> None:
        """Test embedding_dimensions must be positive."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="embedding_dimensions must be positive"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=-1,
                default_top_k=8,
            )


    def test_validate_default_top_k_positive(self, tmp_path, monkeypatch) -> None:
        """Test default_top_k must be positive."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="default_top_k must be positive"
        ):
            Config(
                mongo_uri=_test_config.mongo_uri,
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=0,
            )


    def test_validate_max_workers_positive(self, tmp_path, monkeypatch) -> None:
        """Test max_workers must be positive when set."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="max_workers must be positive when set"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017/test",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                max_workers=0,
            )


    def test_validate_embedding_cache_size_non_negative(self, tmp_path, monkeypatch) -> None:
        """Test embedding_cache_size must be non-negative in model validator."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="embedding_cache_size must be non-negative"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017/test",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_cache_size=-1,
            )


    def test_validate_embedding_batch_size_range(self, tmp_path, monkeypatch) -> None:
        """Test embedding_batch_size must be between 1 and 100 in model validator."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="embedding_batch_size must be between 1 and 100"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017/test",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_batch_size=101,
            )


    def test_validate_streaming_chunk_batch_size_range(self, tmp_path, monkeypatch) -> None:
        """Test streaming_chunk_batch_size must be between 1 and 200 in model validator."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="streaming_chunk_batch_size must be between 1 and 200"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017/test",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                streaming_chunk_batch_size=201,
            )


    def test_validate_embedding_dtype(self, tmp_path, monkeypatch) -> None:
        """Test embedding_dtype must be float32 or float64."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="embedding_dtype must be 'float32' or 'float64'"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017/test",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_dtype="float16",
            )


    def test_validate_embedding_storage_format(self, tmp_path, monkeypatch) -> None:
        """Test embedding_storage_format must be binary or array."""
        from secondbrain.config import Config

        with pytest.raises(
            ValueError, match="embedding_storage_format must be 'binary' or 'array'"
        ):
            Config(
                mongo_uri="mongodb://localhost:27017/test",
                chunk_size=64,
                chunk_overlap=16,
                embedding_dimensions=128,
                default_top_k=8,
                embedding_storage_format="text",
            )


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_returns_config_instance(self, tmp_path, monkeypatch) -> None:
        """Test get_config returns a Config instance."""
        import os

        monkeypatch.setenv("SECONDBRAIN_MONGO_URI", _test_config.mongo_uri)
        monkeypatch.setenv("SECONDBRAIN_MONGO_DB", "secondbrain_test")
        monkeypatch.setenv("SECONDBRAIN_MONGO_COLLECTION", "embeddings_test")
        monkeypatch.setenv("SECONDBRAIN_LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        monkeypatch.setenv("SECONDBRAIN_CHUNK_SIZE", "4096")
        monkeypatch.setenv("SECONDBRAIN_CHUNK_OVERLAP", "50")
        monkeypatch.setenv("SECONDBRAIN_DEFAULT_TOP_K", "5")
        monkeypatch.setenv("SECONDBRAIN_EMBEDDING_DIMENSIONS", "768")

        from secondbrain.config import get_config

        get_config.cache_clear()
        config = get_config()

        assert isinstance(config, Config)
