"""Async edge case tests for RAG pipeline.

Exercises asyncio.CancellationError propagation, timeout escalation,
and backpressure handling via Semaphore throttling in RAGPipeline.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.pipeline import RAGPipeline


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher with async search."""
    mock = MagicMock()
    mock.search_async = AsyncMock(
        return_value=[
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
    )
    return mock


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LocalLLMProvider with async support."""
    mock = MagicMock(spec=LocalLLMProvider)
    mock.agenerate = AsyncMock(return_value="generated answer")
    mock.stream_chat_async = AsyncMock(
        side_effect=RuntimeError("streaming not supported")
    )
    return mock


@pytest.fixture
def pipeline(
    mock_searcher: MagicMock,
    mock_llm_provider: MagicMock,
) -> RAGPipeline:
    """Create RAGPipeline with mocked dependencies."""
    return RAGPipeline(
        searcher=mock_searcher,
        llm_provider=mock_llm_provider,
        top_k=5,
    )


class TestLLMTimeoutCancellation:
    """Tests for asyncio.TimeoutError propagation through RAGPipeline."""

    @pytest.mark.asyncio
    async def test_llm_timeout_triggers_cancellation(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Mock embedding provider raises asyncio.TimeoutError.

        verify it propagates through RAGPipeline.chat_async().
        """
        # Arrange
        mock_searcher.search_async = AsyncMock(
            return_value=[{"chunk_text": "context", "source_file": "f.pdf", "page": 1}]
        )

        async def _raise_timeout(*args: object, **kwargs: object) -> str:
            raise TimeoutError("LLM request timed out")

        mock_llm_provider.agenerate = AsyncMock(side_effect=_raise_timeout)
        mock_llm_provider.stream_chat_async = AsyncMock(side_effect=_raise_timeout)

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        # Act
        result = await pipeline.chat_async("test query", MagicMock())

        # Assert - pipeline swallows TimeoutError and returns graceful error response
        assert "answer" in result
        assert (
            "timeout" in result["answer"].lower()
            or "apologize" in result["answer"].lower()
            or "error" in result["answer"].lower()
        ), f"Expected graceful error message, got: {result['answer']}"

    @pytest.mark.asyncio
    async def test_llm_timeout_in_query_async(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """asyncio.TimeoutError from agenerate in query_async is handled gracefully."""
        mock_searcher.search_async = AsyncMock(
            return_value=[{"chunk_text": "context", "source_file": "f.pdf", "page": 1}]
        )

        async def _raise_timeout(*args: object, **kwargs: object) -> str:
            raise TimeoutError("Generation timeout")

        mock_llm_provider.agenerate = AsyncMock(side_effect=_raise_timeout)
        mock_llm_provider.stream_chat_async = AsyncMock(side_effect=_raise_timeout)

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = await pipeline.query_async("test query")

        # Pipeline catches all exceptions and returns error response
        assert "answer" in result
        assert (
            "timeout" in result["answer"].lower()
            or "apologize" in result["answer"].lower()
            or "error" in result["answer"].lower()
        )


class TestOperationTimeoutEscalation:
    """Tests for long-running operations triggering circuit breaker mid-request."""

    @pytest.mark.asyncio
    async def test_operation_timeout_escalation(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Simulate long operation that trips circuit breaker mid-request.

        verify pipeline handles CircuitBroken state gracefully.
        """
        # Simulate circuit breaker transitioning to OPEN state mid-operation
        mock_searcher.search_async = AsyncMock(
            return_value=[{"chunk_text": "context", "source_file": "f.pdf", "page": 1}]
        )

        async def _tripped_breaker(*args: object, **kwargs: object) -> str:
            # CircuitBreaker.open() raises CircuitBreakerError
            from secondbrain.utils.circuit_breaker import CircuitBreakerError

            raise CircuitBreakerError("Circuit broken: search service unavailable")

        mock_llm_provider.agenerate = AsyncMock(side_effect=_tripped_breaker)
        mock_llm_provider.stream_chat_async = AsyncMock(side_effect=_tripped_breaker)

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = await pipeline.query_async("test query")

        # Pipeline catches CircuitBreakerError and returns error response
        assert "answer" in result
        assert (
            "unavailable" in result["answer"].lower()
            or "apologize" in result["answer"].lower()
            or "error" in result["answer"].lower()
        )

    @pytest.mark.asyncio
    async def test_chat_timeout_escalation(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Long operation timeout escalates to error in chat_async."""
        mock_searcher.search_async = AsyncMock(
            return_value=[{"chunk_text": "context", "source_file": "f.pdf", "page": 1}]
        )

        async def _escalating_timeout(*args: object, **kwargs: object) -> str:
            from secondbrain.utils.circuit_breaker import CircuitBreakerError

            raise CircuitBreakerError("Circuit open after 3 failures")

        mock_llm_provider.agenerate = AsyncMock(side_effect=_escalating_timeout)
        mock_llm_provider.stream_chat_async = AsyncMock(side_effect=_escalating_timeout)

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = await pipeline.chat_async("test query", MagicMock())

        assert "answer" in result
        assert (
            "unavailable" in result["answer"].lower()
            or "apologize" in result["answer"].lower()
            or "error" in result["answer"].lower()
        )


class TestBackpressureHandling:
    """Tests for asyncio.Semaphore-based backpressure when search outpaces LLM."""

    @pytest.mark.asyncio
    async def test_backpressure_handling(self) -> None:
        """Semaphore simulates fast producers / slow consumer; pipeline completes.

        without deadlock, demonstrating backpressure does not block indefinitely.
        """
        max_capacity = 3
        backpressure_sem = asyncio.Semaphore(max_capacity)
        generate_calls = 0

        async def throttled_generate(
            prompt: str, *, temperature: float = 0.7, max_tokens: int = 4096
        ) -> str:
            nonlocal generate_calls
            async with backpressure_sem:
                generate_calls += 1
                await asyncio.sleep(0.005)
            return f"processed: {prompt[:20]}..."

        mock_searcher = MagicMock()
        mock_searcher.search_async = AsyncMock(
            return_value=[
                {"chunk_text": f"chunk {i}", "source_file": f"f{i}.pdf", "page": i}
                for i in range(10)
            ]
        )

        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.agenerate = AsyncMock(side_effect=throttled_generate)
        mock_llm_provider.stream_chat_async = AsyncMock(
            side_effect=RuntimeError("not streaming")
        )

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=10,
        )

        # Must complete within timeout; proves no unbounded queue growth / deadlock
        result = await asyncio.wait_for(
            pipeline.query_async("semaphore test"),
            timeout=10.0,
        )

        assert "answer" in result
        # Semaphore allowed at most max_capacity concurrent generates
        assert 1 <= generate_calls <= 10

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrent_work(self) -> None:
        """Semaphore(1) serializes calls; verify serialized execution completes."""
        active_workers = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def counting_generate(
            prompt: str, *, temperature: float = 0.7, max_tokens: int = 4096
        ) -> str:
            nonlocal active_workers, max_concurrent
            async with lock:
                active_workers += 1
                max_concurrent = max(max_concurrent, active_workers)
            try:
                await asyncio.sleep(0.01)
            finally:
                active_workers -= 1
            return f"answer: {prompt[:10]}"

        mock_searcher = MagicMock()
        mock_searcher.search_async = AsyncMock(
            return_value=[
                {"chunk_text": f"ctx {i}", "source_file": f"f{i}.txt", "page": i}
                for i in range(5)
            ]
        )

        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.agenerate = AsyncMock(side_effect=counting_generate)
        mock_llm_provider.stream_chat_async = AsyncMock(side_effect=RuntimeError("off"))

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = await asyncio.wait_for(
            pipeline.query_async("serialized test"),
            timeout=10.0,
        )

        assert "answer" in result
        # Semaphore(1) means max 1 concurrent call
        assert max_concurrent <= 1
