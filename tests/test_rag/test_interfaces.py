"""Tests for RAG provider interfaces.

Tests the LocalLLMProvider protocol to ensure all implementations
conform to the expected interface.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.rag.interfaces import LocalLLMProvider


class TestLocalLLMProviderProtocol:
    """Tests for LocalLLMProvider protocol compliance."""

    def test_protocol_requires_generate_method(self):
        """Protocol should require generate method."""

        # A class without generate should not be considered a valid implementation
        class BadImplementation:
            async def agenerate(self, prompt: str) -> str:
                return "test"

            def health_check(self) -> bool:
                return True

        # Check that it's not a valid implementation
        assert not isinstance(BadImplementation(), LocalLLMProvider)

    def test_protocol_requires_agenerate_method(self):
        """Protocol should require agenerate method."""

        class BadImplementation:
            def generate(self, prompt: str) -> str:
                return "test"

            def health_check(self) -> bool:
                return True

        assert not isinstance(BadImplementation(), LocalLLMProvider)

    def test_protocol_requires_health_check_method(self):
        """Protocol should require health_check method."""

        class BadImplementation:
            def generate(self, prompt: str) -> str:
                return "test"

            async def agenerate(self, prompt: str) -> str:
                return "test"

        assert not isinstance(BadImplementation(), LocalLLMProvider)

    def test_valid_implementation_has_all_methods(self):
        """A valid implementation should have all required methods."""

        class GoodImplementation:
            def generate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            async def agenerate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            def health_check(self) -> bool:
                return True

        # Check that it's a valid implementation
        assert isinstance(GoodImplementation(), LocalLLMProvider)

    def test_generate_signature(self):
        """generate method should have correct signature."""

        class TestImplementation:
            def generate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            async def agenerate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            def health_check(self) -> bool:
                return True

        impl = TestImplementation()
        result = impl.generate("test prompt")
        assert result == "test"

    def test_generate_with_parameters(self):
        """generate should accept temperature and max_tokens parameters."""

        class TestImplementation:
            def generate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return f"prompt={prompt}, temp={temperature}, max={max_tokens}"

            async def agenerate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            def health_check(self) -> bool:
                return True

        impl = TestImplementation()
        result = impl.generate("hello", temperature=0.9, max_tokens=1000)
        assert "hello" in result
        assert "0.9" in result
        assert "1000" in result

    def test_agenerate_is_async(self):
        """agenerate should be an async method."""
        import asyncio

        class TestImplementation:
            def generate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            async def agenerate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "async result"

            def health_check(self) -> bool:
                return True

        impl = TestImplementation()
        result = asyncio.run(impl.agenerate("test"))
        assert result == "async result"

    def test_health_check_returns_bool(self):
        """health_check should return a boolean."""

        class TestImplementation:
            def generate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            async def agenerate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "test"

            def health_check(self) -> bool:
                return True

        impl = TestImplementation()
        result = impl.health_check()
        assert isinstance(result, bool)

    def test_mock_provider_compliance(self):
        """Mock provider should be usable as LocalLLMProvider."""
        mock_provider = MagicMock(spec=LocalLLMProvider)
        mock_provider.generate.return_value = "mock response"
        mock_provider.agenerate.return_value = "async mock response"
        mock_provider.health_check.return_value = True

        # Verify methods work
        assert mock_provider.generate("test") == "mock response"
        assert mock_provider.health_check() is True

    def test_protocol_is_runtime_checkable(self):
        """Protocol should support isinstance checks."""
        import inspect

        from typing import Protocol

        # Check that LocalLLMProvider is a Protocol
        assert inspect.isclass(LocalLLMProvider)
        assert hasattr(LocalLLMProvider, "__protocol_attrs__")


class TestProtocolUsage:
    """Tests for using LocalLLMProvider in practice."""

    def test_can_use_as_type_hint(self):
        """Protocol can be used as a type hint."""
        from typing import Callable

        def use_provider(provider: LocalLLMProvider) -> str:
            return provider.generate("test")

        class TestProvider:
            def generate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return f"response to: {prompt}"

            async def agenerate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return "async"

            def health_check(self) -> bool:
                return True

        provider = TestProvider()
        result = use_provider(provider)
        assert "response to" in result

    def test_can_use_in_generic(self):
        """Protocol can be used in generic types."""
        from typing import Generic, TypeVar

        T = TypeVar("T", bound=LocalLLMProvider)

        class ProviderWrapper(Generic[T]):
            def __init__(self, provider: T):
                self.provider = provider

            def query(self, prompt: str) -> str:
                return self.provider.generate(prompt)

        class TestProvider:
            def generate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return prompt

            async def agenerate(
                self,
                prompt: str,
                temperature: float = 0.7,
                max_tokens: int = 4096,
            ) -> str:
                return prompt

            def health_check(self) -> bool:
                return True

        provider = TestProvider()
        wrapper = ProviderWrapper(provider)
        result = wrapper.query("hello")
        assert result == "hello"
