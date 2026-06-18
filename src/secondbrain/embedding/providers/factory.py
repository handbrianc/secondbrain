"""Embedding provider factory for creating provider instances.

Provides EmbeddingProviderFactory class for creating provider instances
based on configuration, supporting local (sentence-transformers) and
OpenAI API-based embedding providers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from secondbrain.config import Config
from secondbrain.embedding.interfaces import EmbeddingProvider

if TYPE_CHECKING:
    from secondbrain.embedding.local import LocalEmbeddingProvider
    from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider


class EmbeddingProviderFactory:
    """Factory for creating embedding providers.

    Creates provider instances based on configuration settings.
    Supports local (sentence-transformers) and OpenAI providers.

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
            from secondbrain.embedding.local import LocalEmbeddingProvider

            return LocalEmbeddingProvider(model_name=config.embedding_model)

        elif provider_type == "openai":
            from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

            return OpenAIEmbeddingProvider(
                model=config.embedding_model,
                api_key=config.embedding_api_key,
                api_base=config.embedding_api_base,
                dimensions=config.embedding_dimensions,
            )

        else:
            raise ValueError(
                f"Unsupported embedding provider: {provider_type}. "
                f"Supported providers: local, openai"
            )

    @staticmethod
    def create_local(
        model_name: str | None = None,
    ) -> LocalEmbeddingProvider:
        """Create a local embedding provider.

        Args:
            model_name: Sentence-transformers model name (defaults to config).

        Returns:
            Configured LocalEmbeddingProvider instance.
        """
        from secondbrain.config import config
        from secondbrain.embedding.local import LocalEmbeddingProvider

        cfg = config()
        return LocalEmbeddingProvider(
            model_name=model_name or cfg.embedding_model,
        )

    @staticmethod
    def create_openai(
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        dimensions: int | None = None,
    ) -> OpenAIEmbeddingProvider:
        """Create an OpenAI embedding provider.

        Args:
            model: Model name (defaults to config).
            api_key: API key (defaults to config or env var).
            api_base: Base URL for OpenAI-compatible API (defaults to config).
            dimensions: Output dimensions (defaults to config).

        Returns:
            Configured OpenAIEmbeddingProvider instance.

        Raises:
            ValueError: If API key is not provided.
        """
        from secondbrain.config import config
        from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

        cfg = config()
        return OpenAIEmbeddingProvider(
            model=model or cfg.embedding_model,
            api_key=api_key or cfg.embedding_api_key,
            api_base=api_base or cfg.embedding_api_base,
            dimensions=dimensions or cfg.embedding_dimensions,
        )
