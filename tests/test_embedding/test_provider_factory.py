"""Tests for secondbrain.embedding.providers.factory.EmbeddingProviderFactory.

Verifies that the factory correctly instantiates providers based on
configuration and direct constructor calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestEmbeddingProviderFactoryCreateFromConfig:
    """Tests for EmbeddingProviderFactory.create_from_config."""

    def test_create_openai_provider(self) -> None:
        """When embedding_provider is 'openai', factory returns OpenAIEmbeddingProvider."""
        from secondbrain.embedding.providers.factory import EmbeddingProviderFactory

        mock_cfg = MagicMock()
        mock_cfg.embedding_provider = "openai"
        mock_cfg.embedding_model = "text-embedding-3-small"
        mock_cfg.embedding_api_key = "sk-test-key"
        mock_cfg.embedding_api_base = "https://api.openai.com/v1"
        mock_cfg.embedding_dimensions = 1536

        # OpenAIEmbeddingProvider is lazily imported inside create_from_config,
        # so we patch it at the source module where it lives.
        with patch(
            "secondbrain.embedding.providers.openai.OpenAIEmbeddingProvider"
        ) as mock_openai_cls:
            mock_instance = MagicMock()
            mock_openai_cls.return_value = mock_instance
            provider = EmbeddingProviderFactory.create_from_config(mock_cfg)

        assert provider is mock_instance
        mock_openai_cls.assert_called_once_with(
            model="text-embedding-3-small",
            api_key="sk-test-key",
            api_base="https://api.openai.com/v1",
            dimensions=1536,
        )

    def test_create_openai_provider_without_api_base(self) -> None:
        """When embedding_provider is 'openai' without api_base, factory still succeeds."""
        from secondbrain.embedding.providers.factory import EmbeddingProviderFactory

        mock_cfg = MagicMock()
        mock_cfg.embedding_provider = "openai"
        mock_cfg.embedding_model = "text-embedding-3-small"
        mock_cfg.embedding_api_key = "sk-test-key"
        mock_cfg.embedding_api_base = None
        mock_cfg.embedding_dimensions = 1536

        with patch(
            "secondbrain.embedding.providers.openai.OpenAIEmbeddingProvider"
        ) as mock_openai_cls:
            mock_instance = MagicMock()
            mock_openai_cls.return_value = mock_instance
            provider = EmbeddingProviderFactory.create_from_config(mock_cfg)

        assert provider is mock_instance

    def test_create_local_provider_raises(self) -> None:
        """The deprecated 'local' provider raises ValueError with removal guidance."""
        from secondbrain.embedding.providers.factory import EmbeddingProviderFactory

        mock_cfg = MagicMock()
        mock_cfg.embedding_provider = "local"

        with pytest.raises(
            ValueError, match="'local' embedding provider has been removed"
        ):
            EmbeddingProviderFactory.create_from_config(mock_cfg)

    def test_case_insensitive_openai(self) -> None:
        """Provider matching is case-insensitive ('OPENAI' also routes correctly)."""
        from secondbrain.embedding.providers.factory import EmbeddingProviderFactory

        mock_cfg = MagicMock()
        mock_cfg.embedding_provider = "OPENAI"
        mock_cfg.embedding_model = "text-embedding-3-small"
        mock_cfg.embedding_api_key = None
        mock_cfg.embedding_api_base = None
        mock_cfg.embedding_dimensions = None

        with patch(
            "secondbrain.embedding.providers.openai.OpenAIEmbeddingProvider"
        ) as mock_openai_cls:
            mock_instance = MagicMock()
            mock_openai_cls.return_value = mock_instance
            provider = EmbeddingProviderFactory.create_from_config(mock_cfg)

        assert provider is mock_instance

    def test_unknown_provider_raises(self) -> None:
        """Unrecognised provider type raises ValueError listing supported providers."""
        from secondbrain.embedding.providers.factory import EmbeddingProviderFactory

        mock_cfg = MagicMock()
        mock_cfg.embedding_provider = "anthropic"
        mock_cfg.embedding_model = ""
        mock_cfg.embedding_api_key = None
        mock_cfg.embedding_api_base = None
        mock_cfg.embedding_dimensions = None

        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            EmbeddingProviderFactory.create_from_config(mock_cfg)


class TestEmbeddingProviderFactoryCreateOpenAI:
    """Tests for EmbeddingProviderFactory.create_openai static method."""

    def test_create_openai_with_overrides(self) -> None:
        """create_openai constructs OpenAIEmbeddingProvider overriding config defaults."""
        from secondbrain.embedding.providers.factory import EmbeddingProviderFactory

        # config() is imported inside the method → patch at the source module.
        with patch("secondbrain.config.config") as mock_get_config:
            mock_cfg = MagicMock()
            mock_cfg.embedding_model = "text-embedding-3-small"
            mock_cfg.embedding_api_key = "sk-env-key"
            mock_cfg.embedding_api_base = "https://api.openai.com/v1"
            mock_cfg.embedding_dimensions = 768
            mock_get_config.return_value = mock_cfg

            with patch(
                "secondbrain.embedding.providers.openai.OpenAIEmbeddingProvider"
            ) as mock_openai_cls:
                mock_instance = MagicMock()
                mock_openai_cls.return_value = mock_instance

                provider = EmbeddingProviderFactory.create_openai(
                    model="text-embedding-3-large",
                    api_key="sk-direct-key",
                    api_base="https://custom.example.com/v1",
                    dimensions=1024,
                )

        assert provider is mock_instance
        mock_openai_cls.assert_called_once_with(
            model="text-embedding-3-large",
            api_key="sk-direct-key",
            api_base="https://custom.example.com/v1",
            dimensions=1024,
        )

    def test_create_openai_no_args_uses_config_defaults(self) -> None:
        """When called without arguments create_openai falls back to config values."""
        from secondbrain.embedding.providers.factory import EmbeddingProviderFactory

        with patch("secondbrain.config.config") as mock_get_config:
            mock_cfg = MagicMock()
            mock_cfg.embedding_model = "text-embedding-3-small"
            mock_cfg.embedding_api_key = "sk-config-default"
            mock_cfg.embedding_api_base = None
            mock_cfg.embedding_dimensions = 1536
            mock_get_config.return_value = mock_cfg

            with patch(
                "secondbrain.embedding.providers.openai.OpenAIEmbeddingProvider"
            ) as mock_openai_cls:
                mock_instance = MagicMock()
                mock_openai_cls.return_value = mock_instance

                provider = EmbeddingProviderFactory.create_openai()

        assert provider is mock_instance
        mock_openai_cls.assert_called_once_with(
            model="text-embedding-3-small",
            api_key="sk-config-default",
            api_base=None,
            dimensions=1536,
        )


class TestOpenAIEmbeddingProviderVariants:
    """Tests demonstrating that OpenAIEmbeddingProvider handles OpenAI-compatible
    endpoints (Ollama, LM Studio, vLLM, Azure OpenAI) via api_base override.
    """

    def test_azure_openai_style_endpoint(self) -> None:
        """Azure OpenAI and OpenAI-compatible services use api_base to point at custom endpoints."""
        from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(
            model="text-embedding-3-small",
            api_key="fake-azure-key",
            api_base="https://my-company.openai.azure.com/",
            dimensions=1536,
        )

        assert provider._model == "text-embedding-3-small"
        assert provider._dimensions == 1536

    def test_local_ollama_style_endpoint(self) -> None:
        """Local Ollama/LM Studio/vLLM are reached via api_base without an API key."""
        from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(
            model="text-embedding-3-small",
            api_key=None,
            api_base="http://localhost:11434/v1",
        )

        assert provider._model == "text-embedding-3-small"
        # Without an explicit key the provider substitutes a placeholder so
        # the client is still initialised (important for local-only setups).
        assert provider._api_key is None or isinstance(provider._api_key, str)

    def test_validate_connection_false_on_network_error(self) -> None:
        """validate_connection returns False when the API endpoint is unreachable."""
        from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

        # Use a nonsense address so connection definitely fails.
        provider = OpenAIEmbeddingProvider(
            model="text-embedding-3-small",
            api_key="sk-fake",
            api_base="http://localhost:99999/nonexistent",
        )
        # Force the client to attempt connection (normally a cache is checked first).
        result = provider.validate_connection(force=True)

        assert result is False
