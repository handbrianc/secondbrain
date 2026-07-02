"""Embedding provider factory for creating provider instances.

Provides EmbeddingProviderFactory class for creating provider instances
based on configuration, supporting OpenAI API-based embedding providers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from secondbrain.config import Config
from secondbrain.embedding.interfaces import EmbeddingProvider

if TYPE_CHECKING:
    from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider


class EmbeddingProviderFactory:
    """Factory for creating embedding providers.

    Creates provider instances based on configuration settings.
    Supports OpenAI and OpenAI-compatible providers.

    Example:
        >>> from secondbrain.config import config
        >>> from secondbrain.embedding import EmbeddingProviderFactory
        >>> cfg = config()
        >>> provider = EmbeddingProviderFactory.create_from_config(cfg)
    """

    @staticmethod
    def create_from_config(config: Config) -> EmbeddingProvider:
        """Create an embedding provider from project configuration.

        Args:
            config: Configuration instance containing embedding settings.

        Returns:
            Configured EmbeddingProvider instance.

        Raises:
            ValueError: If provider type is unsupported or API key missing.
        """
        provider_type = config.embedding_provider.lower()

        if provider_type == "local":
            raise ValueError(
                "The 'local' embedding provider has been removed. "
                "Use embedding_provider='openai' and configure a compatible API "
                "(e.g., SECONDBRAIN_OPENAI_BASE_URL for Ollama, LM Studio, vLLM)."
            )

        if provider_type == "openai":
            from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

            return cast(
                EmbeddingProvider,
                OpenAIEmbeddingProvider(
                    model=config.embedding_model,
                    api_key=config.embedding_api_key,
                    api_base=config.embedding_api_base,
                    dimensions=config.embedding_dimensions,
                ),
            )

        raise ValueError(
            f"Unsupported embedding provider: {provider_type}. "
            f"Supported providers: openai"
        )

    @staticmethod
    def create_openai(
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        dimensions: int | None = None,
    ) -> OpenAIEmbeddingProvider:
        """Create an OpenAI-compatible embedding provider.

        Args:
            model: Model name (defaults to config).
            api_key: API key (defaults to config or env var).
            api_base: Base URL for OpenAI-compatible API (defaults to config).
            dimensions: Output dimensions (defaults to config).

        Returns:
            Configured OpenAIEmbeddingProvider instance.
        """
        from secondbrain.config import config as _get_config
        from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

        cfg = _get_config()
        return OpenAIEmbeddingProvider(
            model=model or cfg.embedding_model,
            api_key=api_key or cfg.embedding_api_key,
            api_base=api_base or cfg.embedding_api_base,
            dimensions=dimensions or cfg.embedding_dimensions,
        )
