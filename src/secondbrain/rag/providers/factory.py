"""LLM provider factory for creating local LLM providers.

Provides LLMProviderFactory class for creating provider instances
based on configuration.
"""

from __future__ import annotations

from secondbrain.config import Config
from secondbrain.rag.interfaces import LocalLLMProvider


class LLMProviderFactory:
    """Factory for creating LLM providers.

    Supports creating providers based on configuration settings.
    Supports OpenAI-compatible APIs and Anthropic Claude.
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
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
            )
        elif provider_type == "anthropic":
            from secondbrain.rag.providers.anthropic import AnthropicLLMProvider

            return AnthropicLLMProvider(
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
                timeout=config.llm_timeout,
            )
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider_type}. "
                f"Supported providers: openai, anthropic"
            )
