"""Tests for RAG interfaces to improve coverage."""



from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.providers.mock import MockLLMProvider


class TestLocalLLMProviderProtocol:
    """Test LocalLLMProvider protocol definition."""

    def test_protocol_has_generate_method(self):
        """Test protocol defines generate method."""
        assert hasattr(LocalLLMProvider, 'generate')

    def test_protocol_has_agenerate_method(self):
        """Test protocol defines agenerate method."""
        assert hasattr(LocalLLMProvider, 'agenerate')

    def test_protocol_has_health_check_method(self):
        """Test protocol defines health_check method."""
        assert hasattr(LocalLLMProvider, 'health_check')

    def test_protocol_implemented_by_mock_provider(self):
        """Test that MockLLMProvider implements the protocol."""
        provider = MockLLMProvider()

        result = provider.generate("test prompt")
        assert isinstance(result, str)

        import asyncio
        result = asyncio.run(provider.agenerate("test prompt"))
        assert isinstance(result, str)

        result = provider.health_check()
        assert isinstance(result, bool)


class TestProtocolDocumentation:
    """Test protocol documentation and type hints."""

    def test_generate_has_docstring(self):
        """Test generate method has documentation."""
        assert LocalLLMProvider.generate.__doc__ is not None

    def test_agenerate_has_docstring(self):
        """Test agenerate method has documentation."""
        assert LocalLLMProvider.agenerate.__doc__ is not None

    def test_health_check_has_docstring(self):
        """Test health_check method has documentation."""
        assert LocalLLMProvider.health_check.__doc__ is not None


class TestProtocolSignature:
    """Test protocol method signatures."""

    def test_generate_signature(self):
        """Test generate method signature."""
        import inspect
        sig = inspect.signature(LocalLLMProvider.generate)
        params = list(sig.parameters.keys())

        assert 'self' in params
        assert 'prompt' in params
        assert 'temperature' in params
        assert 'max_tokens' in params

    def test_agenerate_signature(self):
        """Test agenerate method signature."""
        import inspect
        sig = inspect.signature(LocalLLMProvider.agenerate)
        params = list(sig.parameters.keys())

        assert 'self' in params
        assert 'prompt' in params
        assert 'temperature' in params
        assert 'max_tokens' in params

    def test_health_check_signature(self):
        """Test health_check method signature."""
        import inspect
        sig = inspect.signature(LocalLLMProvider.health_check)
        params = list(sig.parameters.keys())

        assert 'self' in params
        assert len(params) == 1  # Only self
