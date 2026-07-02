"""Extended tests for OpenAI LLM Provider."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.rag.providers.openai import OpenAILLMProvider


class TestOpenAILLMProviderInit:
    """Test OpenAILLMProvider initialization."""

    def test_init_requires_api_key(self, monkeypatch):
        """Test initialization fails without API key."""
        monkeypatch.delenv("SECONDBRAIN_LLM_API_KEY", raising=False)
        monkeypatch.delenv("SECONDBRAIN_OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OpenAI API key"):
            OpenAILLMProvider(api_key=None)

    def test_init_uses_env_var_api_key(self, monkeypatch):
        """Test initialization uses environment variable for API key."""
        monkeypatch.setenv("SECONDBRAIN_OPENAI_API_KEY", "test-key-123")
        monkeypatch.delenv("SECONDBRAIN_LLM_API_KEY", raising=False)
        provider = OpenAILLMProvider()

        assert provider._api_key == "test-key-123"

    def test_init_prefers_parameter_over_env(self, monkeypatch):
        """Test parameter API key takes precedence over env var."""
        monkeypatch.setenv("SECONDBRAIN_OPENAI_API_KEY", "env-key")
        provider = OpenAILLMProvider(api_key="param-key")

        assert provider._api_key == "param-key"

    def test_init_with_custom_model(self):
        """Test initialization with custom model."""
        provider = OpenAILLMProvider(model="gpt-4", api_key="test-key")

        assert provider._model == "gpt-4"

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        provider = OpenAILLMProvider(timeout=300, api_key="test-key")

        assert provider._timeout == 300


class TestOpenAILLMProviderGenerate:
    """Test OpenAILLMProvider.generate() method."""

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_generate_calls_client(self, mock_client_class):
        """Test generate calls OpenAI client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_completion

        provider = OpenAILLMProvider(api_key="test-key")
        response = provider.generate("Test prompt")

        assert response == "Test response"
        mock_client.chat.completions.create.assert_called_once()

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_generate_uses_custom_temperature(self, mock_client_class):
        """Test generate uses custom temperature."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Response"
        mock_client.chat.completions.create.return_value = mock_completion

        provider = OpenAILLMProvider(api_key="test-key")
        provider.generate("Test", temperature=0.8)

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["temperature"] == 0.8

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_generate_uses_custom_max_tokens(self, mock_client_class):
        """Test generate uses custom max_tokens."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Response"
        mock_client.chat.completions.create.return_value = mock_completion

        provider = OpenAILLMProvider(api_key="test-key")
        provider.generate("Test", max_tokens=500)

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["max_tokens"] == 500

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_generate_handles_api_error(self, mock_client_class):
        """Test generate handles API errors."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        provider = OpenAILLMProvider(api_key="test-key")

        # Should raise an exception for API errors
        with pytest.raises(Exception):
            provider.generate("Test prompt")


class TestOpenAILLMProviderHealthCheck:
    """Test OpenAILLMProvider.health_check() method."""

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_health_check_returns_true_on_success(self, mock_client_class):
        """Test health_check returns True when client works."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        # Mock the models.list() method that health_check actually calls
        mock_client.models.list.return_value = []

        provider = OpenAILLMProvider(api_key="test-key")
        result = provider.health_check()

        # Should return True (no exception raised)
        assert result is True
        mock_client.models.list.assert_called_once()

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_health_check_returns_false_on_failure(self, mock_client_class):
        """Test health_check returns False on error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        # Mock the models.list() method to raise an exception
        mock_client.models.list.side_effect = Exception("Connection failed")

        provider = OpenAILLMProvider(api_key="test-key")
        result = provider.health_check()

        assert result is False


class TestOpenAILLMProviderAsync:
    """Test async methods of OpenAILLMProvider."""

    @patch("secondbrain.rag.providers.openai.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_agenerate_calls_async_client(self, mock_client_class):
        """Test agenerate calls async OpenAI client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Async response"

        async def async_create(*args, **kwargs):
            return mock_completion

        mock_client.chat.completions.create = async_create

        provider = OpenAILLMProvider(api_key="test-key")
        response = await provider.agenerate("Test prompt")

        assert response == "Async response"


class TestOpenAILLMProviderEdgeCases:
    """Test edge cases for OpenAILLMProvider."""

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_generate_with_empty_prompt(self, mock_client_class):
        """Test generate handles empty prompt."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = ""
        mock_client.chat.completions.create.return_value = mock_completion

        provider = OpenAILLMProvider(api_key="test-key")

        # Empty prompt returns empty string - no exception raised
        result = provider.generate("")
        assert result == ""

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_generate_with_very_long_prompt(self, mock_client_class):
        """Test generate handles long prompts."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Response"
        mock_client.chat.completions.create.return_value = mock_completion

        provider = OpenAILLMProvider(api_key="test-key")
        long_prompt = "Test " * 1000
        response = provider.generate(long_prompt)

        assert response == "Response"

    @patch("secondbrain.rag.providers.openai.OpenAI")
    def test_generate_with_unicode_prompt(self, mock_client_class):
        """Test generate handles unicode prompts."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Response"
        mock_client.chat.completions.create.return_value = mock_completion

        provider = OpenAILLMProvider(api_key="test-key")
        response = provider.generate("Hello 世界 🌍")

        assert response == "Response"


class TestOpenAILLMProviderProperties:
    """Test OpenAILLMProvider properties."""

    def test_model_property(self):
        """Test model property returns model name."""
        provider = OpenAILLMProvider(model="gpt-4", api_key="test-key")
        assert provider.model == "gpt-4"

    def test_temperature_property(self):
        """Test temperature property returns temperature."""
        provider = OpenAILLMProvider(temperature=0.5, api_key="test-key")
        assert provider.temperature == 0.5

    def test_max_tokens_property(self):
        """Test max_tokens property returns max_tokens."""
        provider = OpenAILLMProvider(max_tokens=1000, api_key="test-key")
        assert provider.max_tokens == 1000

    def test_timeout_property(self):
        """Test timeout property returns timeout."""
        provider = OpenAILLMProvider(timeout=300, api_key="test-key")
        assert provider.timeout == 300
