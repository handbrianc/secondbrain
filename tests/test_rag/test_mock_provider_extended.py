"""Extended tests for MockLLMProvider to improve coverage."""


import pytest

from secondbrain.rag.providers.mock import (
    MockLLMProvider,
    MockLLMProviderWithContext,
)


class TestMockLLMProviderAsync:
    """Test async methods of MockLLMProvider."""

    @pytest.mark.asyncio
    async def test_agenerate_returns_response(self):
        """Test async generate returns a response."""
        provider = MockLLMProvider()
        response = await provider.agenerate("Test prompt")

        assert response is not None
        assert "[MOCK]" in response

    @pytest.mark.asyncio
    async def test_agenerate_is_deterministic(self):
        """Test async generate is deterministic."""
        provider = MockLLMProvider()
        response1 = await provider.agenerate("Same prompt")
        response2 = await provider.agenerate("Same prompt")

        assert response1 == response2

    @pytest.mark.asyncio
    async def test_agenerate_respects_temperature(self):
        """Test async generate includes temperature in response."""
        provider = MockLLMProvider()
        response = await provider.agenerate("Test", temperature=0.5)

        assert "temperature: 0.5" in response


class TestMockLLMProviderChat:
    """Test chat method of MockLLMProvider."""

    def test_chat_with_user_messages(self):
        """Test chat with user messages."""
        provider = MockLLMProvider()
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        response = provider.chat(messages)

        assert "[MOCK]" in response
        assert "prompt_hash:" in response

    def test_chat_with_multiple_messages(self):
        """Test chat extracts last user message."""
        provider = MockLLMProvider(default_response="Default")
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ]
        response = provider.chat(messages)

        # Should extract "Second question" as the last user message
        assert "[MOCK]" in response
        assert "prompt_hash:" in response

    def test_chat_with_empty_messages(self):
        """Test chat with empty message list."""
        provider = MockLLMProvider()
        response = provider.chat([])

        assert "[MOCK]" in response
        assert "prompt_hash:" in response

    def test_chat_with_no_user_messages(self):
        """Test chat when no user messages present."""
        provider = MockLLMProvider()
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "assistant", "content": "Assistant response"},
        ]
        response = provider.chat(messages)

        assert "[MOCK]" in response

    def test_chat_respects_temperature(self):
        """Test chat includes temperature in response."""
        provider = MockLLMProvider()
        messages = [{"role": "user", "content": "Test"}]
        response = provider.chat(messages, temperature=0.8)

        assert "temperature: 0.8" in response

    def test_chat_respects_max_tokens(self):
        """Test chat includes max_tokens in response."""
        provider = MockLLMProvider()
        messages = [{"role": "user", "content": "Test"}]
        response = provider.chat(messages, max_tokens=500)

        assert "max_tokens: 500" in response


class TestMockLLMProviderHealthCheck:
    """Test health_check method of MockLLMProvider."""

    def test_health_check_always_returns_true(self):
        """Test health_check always returns True."""
        provider = MockLLMProvider()
        result = provider.health_check()

        assert result is True

    def test_health_check_with_custom_response(self):
        """Test health_check returns True even with custom config."""
        provider = MockLLMProvider(
            default_response="Custom",
            response_map={"test": "mapped"}
        )
        result = provider.health_check()

        assert result is True


class TestMockLLMProviderWithContext:
    """Test MockLLMProviderWithContext class."""

    def test_context_provider_initialization(self):
        """Test context provider initializes correctly."""
        provider = MockLLMProviderWithContext()

        assert provider is not None
        assert isinstance(provider._response_map, dict)
        assert len(provider._response_map) > 0

    def test_context_provider_a_b_comparison(self):
        """Test A/B comparison response pattern."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("Compare response A and B")

        assert "score_a" in response
        assert "score_b" in response
        assert "A is better" in response

    def test_context_provider_document_formats(self):
        """Test document formats query."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("what document formats supported")

        assert "PDF" in response
        assert "DOCX" in response

    def test_context_provider_chunk_size(self):
        """Test chunk size configuration query."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("what is chunk size")

        assert "4096" in response

    def test_context_provider_mongodb(self):
        """Test MongoDB configuration query."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("MongoDB connection")

        assert "MongoDB" in response
        assert "URI" in response

    def test_context_provider_circuit_breaker(self):
        """Test circuit breaker configuration query."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("circuit breaker protection")

        assert "circuit breaker" in response.lower()

    def test_context_provider_semantic_search(self):
        """Test semantic search query."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("semantic search")

        assert "embedding" in response.lower()
        assert "cosine similarity" in response.lower()

    def test_context_provider_default_values(self):
        """Test default values query."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("default values")

        assert "4096" in response
        assert "5" in response

    def test_context_provider_error_handling(self):
        """Test error handling query."""
        provider = MockLLMProviderWithContext()
        response = provider.generate("common errors")

        assert "error" in response.lower()

    def test_context_provider_health_check(self):
        """Test health_check returns True."""
        provider = MockLLMProviderWithContext()
        result = provider.health_check()

        assert result is True

    def test_context_provider_chat(self):
        """Test chat method works."""
        provider = MockLLMProviderWithContext()
        messages = [{"role": "user", "content": "test"}]
        response = provider.chat(messages)

        assert response is not None

    @pytest.mark.asyncio
    async def test_context_provider_agenerate(self):
        """Test async generate works."""
        provider = MockLLMProviderWithContext()
        response = await provider.agenerate("test prompt")

        assert response is not None
        assert len(response) > 0


class TestMockLLMProviderEdgeCases:
    """Test edge cases for MockLLMProvider."""

    def test_generate_with_unicode_prompt(self):
        """Test generate handles unicode prompts."""
        provider = MockLLMProvider()
        response = provider.generate("Hello 世界 🌍")

        assert "[MOCK]" in response

    def test_generate_with_very_long_prompt(self):
        """Test generate handles very long prompts."""
        provider = MockLLMProvider()
        long_prompt = "Test " * 1000
        response = provider.generate(long_prompt)

        assert "[MOCK]" in response

    def test_generate_with_special_characters(self):
        """Test generate handles special characters."""
        provider = MockLLMProvider()
        response = provider.generate("Test\n\t\r\n\"'\\<>")

        assert "[MOCK]" in response

    def test_response_map_longest_match_first(self):
        """Test response map matches longest pattern first."""
        response_map = {
            "short": "Short response",
            "longer match": "Longer response",
        }
        provider = MockLLMProvider(response_map=response_map)
        response = provider.generate("This is a longer match test")

        # Should match "longer match" not "short"
        assert "Longer response" in response

    def test_empty_response_map(self):
        """Test with empty response map."""
        provider = MockLLMProvider(response_map={})
        response = provider.generate("Test")

        assert "[MOCK]" in response

    def test_none_response_map(self):
        """Test with None response map."""
        provider = MockLLMProvider(response_map=None)
        response = provider.generate("Test")

        assert "[MOCK]" in response


class TestMockLLMProviderWithMaxTokens:
    """Test max_tokens parameter handling."""

    def test_generate_with_max_tokens(self):
        """Test generate includes max_tokens in response."""
        provider = MockLLMProvider()
        response = provider.generate("Test", max_tokens=1000)

        assert "max_tokens: 1000" in response

    def test_generate_with_none_max_tokens(self):
        """Test generate with None max_tokens."""
        provider = MockLLMProvider()
        response = provider.generate("Test", max_tokens=None)

        assert "max_tokens: None" in response
