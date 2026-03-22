"""LLM provider factory for creating local LLM providers.

Provides LLMProviderFactory class for creating provider instances
based on configuration.
"""

from secondbrain.config import Config
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.providers.ollama import OllamaLLMProvider


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
        # Default to Ollama for now
        # Future: support vLLM, llama.cpp, etc.
        return OllamaLLMProvider(
            host=config.ollama_host,
            model=config.llm_model,
            temperature=config.llm_temperature,
            timeout=config.llm_timeout,
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
