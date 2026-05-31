"""Tests for MockLLMProvider."""

import pytest

from secondbrain.rag.providers.mock import MockLLMProvider


class TestMockLLMProviderInit:
    """Test MockLLMProvider initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        provider = MockLLMProvider()

        assert provider._default_response == "This is a mock response generated for testing purposes."
        assert provider._response_map == {}

    def test_init_with_custom_default_response(self):
        """Test initialization with custom default response."""
        provider = MockLLMProvider(default_response="Custom mock response")

        assert provider._default_response == "Custom mock response"

    def test_init_with_response_map(self):
        """Test initialization with response mapping."""
        response_map = {
            "hello": "Hi there!",
            "goodbye": "See you later!",
        }
        provider = MockLLMProvider(response_map=response_map)

        assert provider._response_map == response_map

    def test_init_with_both_parameters(self):
        """Test initialization with both default and response map."""
        provider = MockLLMProvider(
            default_response="Default",
            response_map={"test": "mapped"}
        )

        assert provider._default_response == "Default"
        assert provider._response_map == {"test": "mapped"}


class TestMockLLMProviderGenerate:
    """Test MockLLMProvider.generate() method."""

    def test_generate_returns_deterministic_response(self):
        """Test that generate returns a deterministic response."""
        provider = MockLLMProvider()

        response1 = provider.generate("Test prompt")
        response2 = provider.generate("Test prompt")

        assert response1 == response2
        assert "[MOCK]" in response1

    def test_generate_includes_prompt_hash(self):
        """Test that generate includes prompt hash in response."""
        provider = MockLLMProvider()

        response = provider.generate("Test prompt")

        assert "prompt_hash:" in response
        # Hash should be 8 characters
        assert len(response.split("prompt_hash:")[1].split(",")[0].strip()) == 8

    def test_generate_ignores_temperature(self):
        """Test that generate ignores temperature parameter."""
        provider = MockLLMProvider()

        response1 = provider.generate("Test", temperature=0.0)
        response2 = provider.generate("Test", temperature=1.0)

        # Responses should differ only in temperature value shown
        assert "temperature: 0.0" in response1
        assert "temperature: 1.0" in response2

    def test_generate_ignores_max_tokens(self):
        """Test that generate ignores max_tokens parameter."""
        provider = MockLLMProvider()

        response1 = provider.generate("Test", max_tokens=10)
        response2 = provider.generate("Test", max_tokens=100)

        assert "max_tokens: 10" in response1
        assert "max_tokens: 100" in response2

    def test_generate_uses_response_map_first(self):
        """Test that response map takes precedence over default."""
        provider = MockLLMProvider(
            default_response="Default",
            response_map={"hello": "Hello response"}
        )

        response = provider.generate("Say hello to me")

        assert response == "Hello response"
        assert "[MOCK]" not in response  # Mapped responses don't have prefix

    def test_generate_first_match_wins(self):
        """Test that first matching pattern wins in response map."""
        provider = MockLLMProvider(
            response_map={
                "hello": "First match",
                "hello world": "Second match"
            }
        )

        response = provider.generate("Say hello world")

        assert response == "First match"

    def test_generate_with_empty_prompt(self):
        """Test generate with empty prompt."""
        provider = MockLLMProvider()

        response = provider.generate("")

        assert "[MOCK]" in response
        assert "prompt_hash:" in response

    def test_generate_with_multiline_prompt(self):
        """Test generate with multiline prompt."""
        provider = MockLLMProvider()

        prompt = """Line 1
Line 2
Line 3"""

        response = provider.generate(prompt)

        assert "[MOCK]" in response
        assert "prompt_hash:" in response


class TestMockLLMProviderAGenerate:
    """Test MockLLMProvider.agenerate() method."""

    @pytest.mark.asyncio
    async def test_agenerate_returns_deterministic_response(self):
        """Test that agenerate returns a deterministic response."""
        provider = MockLLMProvider()

        response1 = await provider.agenerate("Test prompt")
        response2 = await provider.agenerate("Test prompt")

        assert response1 == response2
        assert "[MOCK]" in response1

    @pytest.mark.asyncio
    async def test_agenerate_uses_response_map(self):
        """Test that agenerate uses response map."""
        provider = MockLLMProvider(
            response_map={"test": "Mapped async response"}
        )

        response = await provider.agenerate("This is a test")

        assert response == "Mapped async response"

    @pytest.mark.asyncio
    async def test_agenerate_with_parameters(self):
        """Test agenerate with temperature and max_tokens."""
        provider = MockLLMProvider()

        response = await provider.agenerate(
            "Test",
            temperature=0.7,
            max_tokens=50
        )

        assert "temperature: 0.7" in response
        assert "max_tokens: 50" in response


class TestMockLLMProviderDeterminism:
    """Test determinism of MockLLMProvider."""

    def test_same_prompt_same_response(self):
        """Test that same prompt always produces same response."""
        provider = MockLLMProvider()

        responses = [provider.generate("Same prompt") for _ in range(10)]

        assert len(set(responses)) == 1  # All identical

    def test_different_prompt_different_hash(self):
        """Test that different prompts produce different hashes."""
        provider = MockLLMProvider()

        response1 = provider.generate("Prompt A")
        response2 = provider.generate("Prompt B")

        # Extract hashes
        hash1 = response1.split("prompt_hash:")[1].split(",")[0].strip()
        hash2 = response2.split("prompt_hash:")[1].split(",")[0].strip()

        assert hash1 != hash2

    def test_response_includes_all_parameters(self):
        """Test that response includes all passed parameters."""
        provider = MockLLMProvider()

        response = provider.generate("Test", temperature=0.5, max_tokens=100)

        assert "temperature: 0.5" in response
        assert "max_tokens: 100" in response


class TestMockLLMProviderEdgeCases:
    """Test edge cases for MockLLMProvider."""

    def test_response_map_with_empty_string_key(self):
        """Test response map with empty string as key."""
        provider = MockLLMProvider(
            default_response="Default",
            response_map={"": "Empty key response"}
        )

        # Empty string is in all strings, so should match
        response = provider.generate("Any prompt")

        assert response == "Empty key response"

    def test_unicode_in_prompt(self):
        """Test handling of unicode in prompts."""
        provider = MockLLMProvider()

        response = provider.generate("Hello 世界 🌍")

        assert "[MOCK]" in response
        assert "prompt_hash:" in response

    def test_very_long_prompt(self):
        """Test handling of very long prompts."""
        provider = MockLLMProvider()

        long_prompt = "x" * 10000
        response = provider.generate(long_prompt)

        assert "[MOCK]" in response
        assert "prompt_hash:" in response

    def test_special_characters_in_prompt(self):
        """Test handling of special characters in prompts."""
        provider = MockLLMProvider()

        response = provider.generate("Test\n\t\r\"'\\")

        assert "[MOCK]" in response
        assert "prompt_hash:" in response


class TestMockLLMProviderHealthCheck:
    """Test MockLLMProvider.health_check() method."""

    def test_health_check_always_returns_true(self):
        """Test that health_check always returns True for mock."""
        provider = MockLLMProvider()

        result = provider.health_check()

        assert result is True

    def test_health_check_with_custom_response(self):
        """Test that health_check returns True even with custom configuration."""
        provider = MockLLMProvider(
            default_response="Custom",
            response_map={"test": "mapped"}
        )

        result = provider.health_check()

        assert result is True


class TestMockLLMProviderChat:
    """Test MockLLMProvider.chat() method."""

    def test_chat_returns_deterministic_response(self):
        """Test that chat returns a deterministic response."""
        provider = MockLLMProvider()

        messages = [{"role": "user", "content": "Hello"}]
        response1 = provider.chat(messages)
        response2 = provider.chat(messages)

        assert response1 == response2
        assert "[MOCK]" in response1

    def test_chat_includes_prompt_hash(self):
        """Test that chat includes prompt hash in response."""
        provider = MockLLMProvider()

        messages = [{"role": "user", "content": "Test message"}]
        response = provider.chat(messages)

        assert "prompt_hash:" in response
        # Hash should be 8 characters
        assert len(response.split("prompt_hash:")[1].split(",")[0].strip()) == 8

    def test_chat_ignores_temperature(self):
        """Test that chat ignores temperature parameter."""
        provider = MockLLMProvider()

        messages = [{"role": "user", "content": "Test"}]
        response1 = provider.chat(messages, temperature=0.0)
        response2 = provider.chat(messages, temperature=1.0)

        assert "temperature: 0.0" in response1
        assert "temperature: 1.0" in response2

    def test_chat_ignores_max_tokens(self):
        """Test that chat ignores max_tokens parameter."""
        provider = MockLLMProvider()

        messages = [{"role": "user", "content": "Test"}]
        response1 = provider.chat(messages, max_tokens=10)
        response2 = provider.chat(messages, max_tokens=100)

        assert "max_tokens: 10" in response1
        assert "max_tokens: 100" in response2

    def test_chat_uses_response_map(self):
        """Test that chat uses response map when pattern matches."""
        provider = MockLLMProvider(
            default_response="Default",
            response_map={"hello": "Hello response"}
        )

        messages = [{"role": "user", "content": "Say hello"}]
        response = provider.chat(messages)

        assert response == "Hello response"

    def test_chat_with_multiple_messages(self):
        """Test that chat uses the last user message."""
        provider = MockLLMProvider()

        messages = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Second message"}
        ]

        response = provider.chat(messages)

        # Should use "Second message" as the prompt
        assert "prompt_hash:" in response
        # The hash should be different from just "First message"
        response_first = provider.chat([{"role": "user", "content": "First message"}])
        assert response != response_first

    def test_chat_with_empty_messages(self):
        """Test chat with empty messages list."""
        provider = MockLLMProvider()

        messages = []
        response = provider.chat(messages)

        assert "[MOCK]" in response
        assert "prompt_hash:" in response

    def test_chat_with_no_user_message(self):
        """Test chat when no user message is present."""
        provider = MockLLMProvider()

        messages = [
            {"role": "assistant", "content": "Previous response"},
            {"role": "system", "content": "System instruction"}
        ]

        response = provider.chat(messages)

        # Should handle empty prompt gracefully
        assert "[MOCK]" in response

    def test_chat_with_multiple_user_messages(self):
        """Test chat extracts the last user message when multiple exist."""
        provider = MockLLMProvider()

        messages = [
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
            {"role": "user", "content": "Third"}
        ]

        response = provider.chat(messages)

        # Should use "Third" as the prompt (last user message)
        assert "prompt_hash:" in response
