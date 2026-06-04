"""LLM provider factory for creating LLM providers.

Provides LLMProviderFactory class for creating provider instances
based on configuration.
"""

from __future__ import annotations

from secondbrain.config import Config
from secondbrain.rag.interfaces import LocalLLMProvider


class LLMProviderFactory:
    """Factory for creating LLM providers.

    Provides LLMProviderFactory class for creating provider instances
    based on configuration.
    Currently supports OpenAI as the default provider.
    """

    @staticmethod
    def create_from_config(config: Config) -> LocalLLMProvider:
        """Create an LLM provider from project configuration.

        Args:
            config: Configuration instance containing LLM settings.

        Returns:
            Configured LocalLLMProvider instance.
        """
        provider_type = config.llm_provider.lower()

        if provider_type == "openai":
            from secondbrain.rag.providers.openai import OpenAILLMProvider

            return OpenAILLMProvider(
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
                timeout=config.llm_timeout,
                api_key=config.llm_api_key,  # Pass LLM API key
                base_url=config.embedding_api_base,  # Use embedding_api_base for LiteLLM proxy
            )
        elif provider_type == "anthropic":
            from secondbrain.rag.providers.anthropic import AnthropicLLMProvider

            return AnthropicLLMProvider(
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
                timeout=config.llm_timeout,
                api_key=config.llm_api_key,  # Pass LLM API key
            )
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider_type}. "
                f"Supported providers: openai, anthropic"
            )
