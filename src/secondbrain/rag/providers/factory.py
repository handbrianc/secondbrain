"""LLM provider factory for creating local LLM providers.

Provides LLMProviderFactory class for creating provider instances
based on configuration.
"""

from secondbrain.config import Config
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.providers.ollama import OllamaLLMProvider
from secondbrain.rag.providers.openai import OpenAILLMProvider


class LLMProviderFactory:
    """Factory for creating local LLM providers.

    Supports creating providers based on configuration settings.
    Currently supports Ollama as the default provider.
    """

    @staticmethod
    def create_from_config(config: Config) -> LocalLLMProvider:
        """Create a provider from configuration.

        Args:
            config: Configuration instance with provider settings.

        Returns:
            Configured LocalLLMProvider instance.

        Raises:
            ValueError: If provider type is not recognized.
        """
        provider_type = config.llm_provider.lower()

        if provider_type == "ollama":
            return OllamaLLMProvider(
                host=config.ollama_host,
                model=config.llm_model,
                temperature=config.llm_temperature,
                timeout=config.llm_timeout,
            )
        elif provider_type == "openai":
            return OpenAILLMProvider(
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
                timeout=config.llm_timeout,
            )
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider_type}. "
                f"Supported providers: ollama, openai"
            )

    @staticmethod
    def create_ollama(
        host: str = "http://localhost:11434",
        model: str = "llama2",
        temperature: float = 0.7,
        timeout: int = 120,
    ) -> OllamaLLMProvider:
        """Create an Ollama provider with explicit parameters.

        Args:
            host: Ollama server URL.
            model: Model name to use.
            temperature: Default temperature for generation.
            timeout: HTTP timeout in seconds.

        Returns:
            Configured OllamaLLMProvider instance.
        """
        return OllamaLLMProvider(
            host=host,
            model=model,
            temperature=temperature,
            timeout=timeout,
        )
