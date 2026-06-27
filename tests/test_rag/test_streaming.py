"""Unit tests for streaming functionality in LLM providers."""


from secondbrain.rag.providers.mock import MockLLMProvider


class TestMockProviderStreaming:
    """Test MockLLMProvider streaming functionality."""

    def test_stream_chat_basic(self):
        """Test basic streaming without thinking content."""
        provider = MockLLMProvider(default_response="Test response for streaming")
        chunks = []

        def on_chunk(content: str, reasoning: str | None) -> None:
            chunks.append((content, reasoning))

        result = provider.stream_chat(
            messages=[{"role": "user", "content": "test query"}],
            on_chunk=on_chunk
        )

        assert "Test response for streaming" in result
        assert len(chunks) > 0
        assert all(reasoning is None for _, reasoning in chunks)
        assert "".join(content for content, _ in chunks) == result

    def test_stream_chat_with_multiple_chunks(self):
        """Test streaming produces multiple chunks."""
        provider = MockLLMProvider(default_response="This is a longer response that should produce multiple chunks")
        chunks = []

        def on_chunk(content: str, reasoning: str | None) -> None:
            chunks.append(content)

        result = provider.stream_chat(
            messages=[{"role": "user", "content": "test"}],
            on_chunk=on_chunk
        )

        assert len(chunks) > 1
        assert "".join(chunks) == result

    def test_stream_chat_empty_messages(self):
        """Test streaming with empty messages list."""
        provider = MockLLMProvider()
        chunks = []

        def on_chunk(content: str, reasoning: str | None) -> None:
            chunks.append(content)

        result = provider.stream_chat(messages=[], on_chunk=on_chunk)

        assert result is not None
        assert len(chunks) > 0

    def test_stream_chat_async_basic(self):
        """Test async streaming."""
        import asyncio

        provider = MockLLMProvider(default_response="Async test response")
        chunks = []

        def on_chunk(content: str, reasoning: str | None) -> None:
            chunks.append((content, reasoning))

        async def run_test():
            return await provider.stream_chat_async(
                messages=[{"role": "user", "content": "test"}],
                on_chunk=on_chunk
            )

        result = asyncio.run(run_test())

        assert "Async test response" in result
        assert len(chunks) > 0
        assert "".join(content for content, _ in chunks) == result

    def test_stream_chat_callback_invocation(self):
        """Test that callback is invoked for each chunk."""
        provider = MockLLMProvider(default_response="ABC")
        call_count = 0

        def on_chunk(content: str, reasoning: str | None) -> None:
            nonlocal call_count
            call_count += 1

        result = provider.stream_chat(
            messages=[{"role": "user", "content": "test"}],
            on_chunk=on_chunk
        )

        assert call_count > 0
        assert len(result) > 0

    def test_stream_chat_response_map(self):
        """Test streaming with response map."""
        provider = MockLLMProvider(
            response_map={"test": "Mapped response for test query"}
        )
        chunks = []

        def on_chunk(content: str, reasoning: str | None) -> None:
            chunks.append(content)

        result = provider.stream_chat(
            messages=[{"role": "user", "content": "this is a test query"}],
            on_chunk=on_chunk
        )

        assert result == "Mapped response for test query"
        assert "".join(chunks) == result


class TestStreamingCallbackSignature:
    """Test streaming callback signature compliance."""

    def test_callback_with_content_only(self):
        """Test callback with content but no reasoning."""
        provider = MockLLMProvider()
        received = []

        def on_chunk(content: str, reasoning: str | None) -> None:
            received.append({"content": content, "reasoning": reasoning})

        provider.stream_chat(
            messages=[{"role": "user", "content": "test"}],
            on_chunk=on_chunk
        )

        assert all(r["reasoning"] is None for r in received)
        assert any(r["content"] for r in received)

    def test_callback_type_hints(self):
        """Test callback accepts correct types."""
        provider = MockLLMProvider()

        def on_chunk(content: str, reasoning: str | None) -> None:
            assert isinstance(content, str)
            assert reasoning is None or isinstance(reasoning, str)

        provider.stream_chat(
            messages=[{"role": "user", "content": "test"}],
            on_chunk=on_chunk
        )
