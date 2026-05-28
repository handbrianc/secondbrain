"""LLM provider factory for creating local LLM providers.

Provides LLMProviderFactory class for creating provider instances
based on configuration.
"""

from __future__ import annotations

from secondbrain.config import Config
from secondbrain.rag.interfaces import LocalLLMProvider


class LLMProviderFactory:
    """Factory for creating local LLM providers.

    Supports creating providers based on configuration settings.
    Currently supports Ollama as the default provider.
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

        if provider_type == "ollama":
            from secondbrain.rag.providers.ollama import OllamaLLMProvider

            return OllamaLLMProvider(
                host=config.ollama_host,
                model=config.llm_model,
                temperature=config.llm_temperature,
                timeout=config.llm_timeout,
            )
        elif provider_type == "openai":
            from secondbrain.rag.providers.openai import OpenAILLMProvider

            return OpenAILLMProvider(
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
                timeout=config.llm_timeout,
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
                f"Supported providers: ollama, openai, anthropic"
            )

    @staticmethod
    def create_ollama(
        host: str | None = None,
        model: str = "llama2",
        temperature: float = 0.7,
        timeout: int = 120,
    ) -> OllamaLLMProvider:
        """Create an Ollama LLM provider.

        Args:
            host: Ollama host URL (defaults to config value).
            model: Model name to use.
            temperature: Generation temperature.
            timeout: Request timeout in seconds.

        Returns:
            Configured OllamaLLMProvider instance.
        """
        from secondbrain.config import config
        from secondbrain.rag.providers.ollama import OllamaLLMProvider

        cfg = config()
        return OllamaLLMProvider(
            host=host if host is not None else cfg.ollama_host,
            model=model,
            temperature=temperature,
            timeout=timeout,
        )
