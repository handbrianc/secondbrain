"""Tests for SharedRateLimiter."""

import asyncio
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest

import secondbrain.embedding.providers.openai as openai_mod
from secondbrain.embedding.providers.factory import EmbeddingProviderFactory
from secondbrain.utils import tracing as tracing_mod
from secondbrain.utils.rate_limiter import (
    SharedRateLimiter,
    get_shared_rate_limiter,
    reset_shared_rate_limiter,
)


def _embeddings_response(items: list[tuple[int, list[float]]]):
    """Fake embeddings response: list of (index, embedding) pairs."""
    response = MagicMock()
    data = []
    for index, embedding in items:
        item = MagicMock()
        item.index = index
        item.embedding = embedding
        data.append(item)
    response.data = data
    return response


def monkeypatch_delenv() -> None:
    """Ensure the tracing env flag is absent (conftest may have set it)."""
    import os

    os.environ.pop("SECONDBRAIN_TRACING_ENABLED", None)


@pytest.fixture(autouse=True, scope="module")
def _fast_rate_limiter_time():
    """Accelerate rate-limiter tests by advancing time virtually.

    Shares the same time-mocking approach as _fast_circuit_breaker_time.
    Patch time.sleep to accumulate virtual time; time.monotonic returns
    the virtual base.  Eliminates ~750ms of artificial time.sleep calls.
    """
    _orig_sleep = time.sleep
    _orig_monotonic = time.monotonic

    _lazy_base: float | None = None

    def _fast_monotonic() -> float:
        nonlocal _lazy_base
        if _lazy_base is None:
            _lazy_base = _orig_monotonic()
        return _lazy_base  # type: ignore[return-value]

    def _fast_sleep(seconds: float) -> None:
        if seconds <= 0:
            return
        nonlocal _lazy_base
        if _lazy_base is None:
            _lazy_base = _orig_monotonic()
        _lazy_base += seconds + 1e-6

    time.sleep = _fast_sleep  # type: ignore[method-assign]
    time.monotonic = _fast_monotonic  # type: ignore[method-assign]
    yield
    time.sleep = _orig_sleep  # type: ignore[method-assign]
    time.monotonic = _orig_monotonic


class TestSharedRateLimiterInit:
    """Test SharedRateLimiter initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        limiter = SharedRateLimiter(max_requests=100, window_seconds=60.0)

        assert limiter.max_requests == 100
        assert limiter.window_seconds == 60.0
        assert len(limiter._timestamps) == 0

    def test_init_with_custom_values(self):
        """Test initialization with custom rate limit parameters."""
        limiter = SharedRateLimiter(max_requests=50, window_seconds=30.0)

        assert limiter.max_requests == 50
        assert limiter.window_seconds == 30.0

    def test_init_creates_shared_state(self):
        """Test that initialization creates shared list and lock."""
        limiter = SharedRateLimiter(max_requests=100, window_seconds=60.0)

        # Verify timestamps is a list
        assert hasattr(limiter._timestamps, "append")
        assert hasattr(limiter._timestamps, "pop")
        assert hasattr(limiter._lock, "acquire")
        assert hasattr(limiter._lock, "release")


class TestSharedRateLimiterAcquire:
    """Test SharedRateLimiter.acquire() method."""

    def test_acquire_allows_requests_under_limit(self):
        """Test that acquire allows requests when under the limit."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=60.0)

        # Should allow 5 requests
        for _i in range(5):
            assert limiter.acquire() is True

        # 6th request should be denied
        assert limiter.acquire() is False

    def test_acquire_rejects_over_limit(self):
        """Test that acquire rejects requests when over the limit."""
        limiter = SharedRateLimiter(max_requests=3, window_seconds=60.0)

        # Fill the limit
        for _ in range(3):
            limiter.acquire()

        # All subsequent requests should fail
        assert limiter.acquire() is False
        assert limiter.acquire() is False

    def test_acquire_allows_after_window_expires(self):
        """Test that acquire allows requests after time window expires."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.1)

        # Use up the limit
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False

        # Wait for window to expire
        time.sleep(0.15)

        # Should be able to acquire again
        assert limiter.acquire() is True

    def test_acquire_cleans_old_timestamps(self):
        """Test that acquire removes timestamps outside the window."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.1)

        # Make 2 requests
        limiter.acquire()
        limiter.acquire()

        # Wait for window to expire
        time.sleep(0.15)

        # Make 2 more requests - should clean old timestamps
        assert limiter.acquire() is True
        assert limiter.acquire() is True

        # Should still be at limit
        assert limiter.acquire() is False

    def test_acquire_is_thread_safe(self):
        """Test that acquire handles concurrent access correctly."""
        import threading

        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)

        results = []
        lock = threading.Lock()

        def make_request():
            result = limiter.acquire()
            with lock:
                results.append(result)

        # Create 20 concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Exactly 10 should succeed
        assert sum(results) == 10
        assert results.count(False) == 10


class TestSharedRateLimiterWaitAndAcquire:
    """Test SharedRateLimiter.wait_and_acquire() method."""

    def test_wait_and_acquire_immediate_success(self):
        """Test wait_and_acquire when slot is immediately available."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=60.0)

        # Should succeed immediately
        assert limiter.wait_and_acquire(timeout=1.0) is True

    def test_wait_and_acquire_waits_for_slot(self):
        """Test wait_and_acquire waits for slot to become available."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.2)

        # Use up the limit
        limiter.acquire()
        limiter.acquire()

        # Should wait and then succeed
        start = time.monotonic()
        result = limiter.wait_and_acquire(timeout=1.0)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 0.15  # Should have waited for window

    def test_wait_and_acquire_respects_timeout(self):
        """Test wait_and_acquire returns False on timeout."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=10.0)

        # Use the limit
        limiter.acquire()

        # Should timeout after 0.2 seconds
        start = time.monotonic()
        result = limiter.wait_and_acquire(timeout=0.2)
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed >= 0.15
        assert elapsed < 0.5

    def test_wait_and_acquire_with_no_timeout(self):
        """Test wait_and_acquire waits indefinitely without timeout."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.1)

        # Use up the limit
        limiter.acquire()
        limiter.acquire()

        # Should eventually succeed (with short timeout for test)
        start = time.monotonic()
        result = limiter.wait_and_acquire(timeout=0.5)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 0.05


class TestSharedRateLimiterGetRemaining:
    """Test SharedRateLimiter.get_remaining() method."""

    def test_get_remaining_starts_at_max(self):
        """Test that get_remaining returns max_requests initially."""
        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)

        assert limiter.get_remaining() == 10

    def test_get_remaining_decreases_with_requests(self):
        """Test that get_remaining decreases after each acquire."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=60.0)

        assert limiter.get_remaining() == 5
        limiter.acquire()
        assert limiter.get_remaining() == 4
        limiter.acquire()
        assert limiter.get_remaining() == 3

    def test_get_remaining_respects_window(self):
        """Test that get_remaining increases after window expires."""
        limiter = SharedRateLimiter(max_requests=3, window_seconds=0.1)

        # Use up the limit
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()

        assert limiter.get_remaining() == 0

        # Wait for window to expire
        time.sleep(0.15)

        # Should be reset
        assert limiter.get_remaining() == 3

    def test_get_remaining_never_negative(self):
        """Test that get_remaining never returns negative value."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=60.0)

        limiter.acquire()
        # Multiple acquires should not affect remaining
        limiter.acquire()
        limiter.acquire()

        assert limiter.get_remaining() >= 0


class TestRateLimiterEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_max_requests(self):
        """Test rate limiter with max_requests=0."""
        limiter = SharedRateLimiter(max_requests=0, window_seconds=60.0)

        # Should never allow requests
        assert limiter.acquire() is False
        assert limiter.acquire() is False
        assert limiter.get_remaining() == 0

    def test_very_short_window(self):
        """Test rate limiter with very short time window."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=0.1)

        # Should allow requests initially
        for _ in range(5):
            assert limiter.acquire() is True

        # Should block after limit
        assert limiter.acquire() is False

        # Should reset after window expires (use 2x window for safety)
        time.sleep(0.25)
        assert limiter.acquire() is True

    def test_very_large_max_requests(self):
        """Test rate limiter with very large max_requests."""
        limiter = SharedRateLimiter(max_requests=10000, window_seconds=60.0)

        # Should allow many requests
        for _ in range(1000):
            assert limiter.acquire() is True

        assert limiter.get_remaining() == 9000

    def test_exact_limit_boundary(self):
        """Test behavior exactly at the limit boundary."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=60.0)

        # First request should succeed
        assert limiter.acquire() is True
        assert limiter.get_remaining() == 0

        # Second should fail
        assert limiter.acquire() is False
        assert limiter.get_remaining() == 0

        # Third should also fail
        assert limiter.acquire() is False

    def test_wait_and_acquire_empty_timestamps(self):
        """Test wait_and_acquire when timestamps list is empty (edge case)."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=0.1)

        # First acquire succeeds
        assert limiter.acquire() is True

        # Wait for window to expire so timestamps are cleaned
        time.sleep(0.15)

        # Now wait_and_acquire should work with empty timestamps path
        result = limiter.wait_and_acquire(timeout=0.5)
        assert result is True


class TestSharedRateLimiterFactory:
    """Test get_shared_rate_limiter / reset_shared_rate_limiter."""

    def setup_method(self):
        """Start every factory test from a clean shared instance."""
        reset_shared_rate_limiter()

    def teardown_method(self):
        """Leave no shared instance behind for other test modules."""
        reset_shared_rate_limiter()

    def test_returns_same_instance_across_calls(self):
        """Subsequent calls return the process-wide shared instance."""
        limiter = get_shared_rate_limiter(max_requests=5, window_seconds=30.0)

        assert get_shared_rate_limiter(max_requests=5, window_seconds=30.0) is limiter

    def test_first_call_parameters_win(self):
        """The limiter is created once; later calls reuse it unchanged."""
        limiter = get_shared_rate_limiter(max_requests=5, window_seconds=30.0)

        again = get_shared_rate_limiter(max_requests=99, window_seconds=1.0)

        assert again is limiter
        assert limiter.max_requests == 5
        assert limiter.window_seconds == 30.0

    def test_reset_creates_fresh_instance(self):
        """reset_shared_rate_limiter drops the shared instance."""
        first = get_shared_rate_limiter(max_requests=5, window_seconds=30.0)

        reset_shared_rate_limiter()
        second = get_shared_rate_limiter(max_requests=5, window_seconds=30.0)

        assert second is not first

    def test_shared_state_across_references(self):
        """State acquired through one reference is visible through the other."""
        first = get_shared_rate_limiter(max_requests=2, window_seconds=30.0)
        second = get_shared_rate_limiter(max_requests=2, window_seconds=30.0)

        assert first.acquire() is True

        assert second.get_remaining() == 1


class TestProviderRateLimiterWiring:
    """SharedRateLimiter wired into OpenAIEmbeddingProvider API calls."""

    def _make_provider(self, rate_limiter=None):
        """Provider with the OpenAI SDK clients patched out (no network)."""
        with (
            patch("secondbrain.embedding.providers.openai.OpenAI") as mock_openai,
            patch("secondbrain.embedding.providers.openai.AsyncOpenAI") as mock_async,
        ):
            provider = openai_mod.OpenAIEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="sk-test",
                rate_limiter=rate_limiter,
            )
        sync_client = mock_openai.return_value
        async_client = mock_async.return_value
        sync_client.embeddings.create.return_value = _embeddings_response([(0, [0.1])])
        async_client.embeddings.create = AsyncMock(
            return_value=_embeddings_response([(0, [0.1])])
        )
        return provider, sync_client, async_client

    def test_disabled_no_limiter_constructed(self):
        """Default construction has no limiter and no rate limiting."""
        provider, sync_client, _ = self._make_provider()

        assert provider._rate_limiter is None
        provider.generate("hello")
        provider.generate_batch(["a", "b"])

        assert sync_client.embeddings.create.call_count == 2

    def test_generate_acquires_slot_before_api_call(self):
        """generate() takes a rate-limit slot before calling the API."""
        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)
        provider, sync_client, _ = self._make_provider(rate_limiter=limiter)

        provider.generate("hello")

        assert sync_client.embeddings.create.call_count == 1
        assert limiter.get_remaining() == 9

    def test_generate_batch_acquires_one_slot_per_call(self):
        """A batch call takes a single slot (one API request), not per text."""
        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)
        provider, sync_client, _ = self._make_provider(rate_limiter=limiter)

        provider.generate_batch(["a", "b", "c"])

        assert sync_client.embeddings.create.call_count == 1
        assert limiter.get_remaining() == 9

    def test_calls_deferred_at_limit_until_window_expires(self):
        """Calls beyond the limit queue and complete after the window resets."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=60.0)
        provider, sync_client, _ = self._make_provider(rate_limiter=limiter)

        call_times: list[float] = []
        original = sync_client.embeddings.create.return_value

        def _record_time(**kwargs):
            call_times.append(time.monotonic())
            return original

        sync_client.embeddings.create.side_effect = _record_time

        provider.generate("first")
        provider.generate("second")

        assert sync_client.embeddings.create.call_count == 2
        # The second call waited for the 60s window (virtual time) to turn over
        assert call_times[1] - call_times[0] >= 60.0

    def test_async_generate_acquires_slot(self):
        """generate_async takes a rate-limit slot before the API call."""
        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)
        provider, _, async_client = self._make_provider(rate_limiter=limiter)

        async def run():
            await provider.generate_async("hello")

        asyncio.run(run())

        async_client.embeddings.create.assert_awaited_once()
        assert limiter.get_remaining() == 9

    def test_async_generate_batch_deferred_at_limit(self):
        """Concurrent async batch calls share the limiter and queue at the limit."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=60.0)
        provider, _, async_client = self._make_provider(rate_limiter=limiter)

        async def run():
            # Both tasks start concurrently; the second must wait for a slot
            return await asyncio.gather(
                provider.generate_batch_async(["a"]),
                provider.generate_batch_async(["b"]),
            )

        results = asyncio.run(run())

        # Both batch calls completed; the second waited for the single slot
        assert async_client.embeddings.create.await_count == 2
        assert all(result == [[0.1]] for result in results)
        assert limiter.get_remaining() == 0

    def test_batch_call_blocked_when_slot_exhausted(self):
        """generate_batch also queues when the limiter is at its limit."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=60.0)
        provider, sync_client, _ = self._make_provider(rate_limiter=limiter)

        provider.generate("single")  # consumes the only slot
        call_count_before = sync_client.embeddings.create.call_count
        provider.generate_batch(["a", "b"])  # must defer, not fail

        assert sync_client.embeddings.create.call_count == call_count_before + 1
        assert limiter.get_remaining() == 0


class TestFactoryRateLimiterPlumbing:
    """EmbeddingProviderFactory builds the shared limiter from config."""

    def setup_method(self):
        """Fresh shared limiter per test so config changes are observed."""
        reset_shared_rate_limiter()

    def teardown_method(self):
        """Leave no shared instance behind for other test modules."""
        reset_shared_rate_limiter()

    @staticmethod
    def _config(**overrides):
        """Config stub standing in for the real pydantic settings object."""
        cfg = MagicMock()
        cfg.embedding_provider = "openai"
        cfg.embedding_model = "text-embedding-3-small"
        cfg.embedding_api_key = "sk-test"
        cfg.embedding_api_base = None
        cfg.embedding_dimensions = 1536
        cfg.embedding_timeout = 30
        cfg.rate_limit_enabled = False
        cfg.rate_limit_max_requests = 7
        cfg.rate_limit_window_seconds = 2.5
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg

    def test_disabled_builds_provider_without_limiter(self):
        """rate_limit_enabled=False (default) wires no limiter."""
        provider = EmbeddingProviderFactory.create_from_config(self._config())

        assert provider._rate_limiter is None

    def test_enabled_wires_shared_limiter_with_config_values(self):
        """rate_limit_enabled=True wires the process-wide limiter."""
        cfg = self._config(rate_limit_enabled=True)

        provider = EmbeddingProviderFactory.create_from_config(cfg)
        again = EmbeddingProviderFactory.create_from_config(
            self._config(rate_limit_enabled=True)
        )

        assert provider._rate_limiter is not None
        assert provider._rate_limiter.max_requests == 7
        assert provider._rate_limiter.window_seconds == 2.5
        # Both providers share the same process-wide limiter instance
        assert again._rate_limiter is provider._rate_limiter

    def test_create_openai_plumbs_limiter_from_config(self):
        """create_openai reads the same config flags."""
        with patch("secondbrain.config.config") as mock_get_config:
            mock_get_config.return_value = self._config(rate_limit_enabled=True)

            provider = EmbeddingProviderFactory.create_openai()

        assert provider._rate_limiter is not None
        assert provider._rate_limiter.max_requests == 7
        assert provider._rate_limiter.window_seconds == 2.5

    def test_config_field_defaults_rate_limiting_off(self):
        """The real Config declares rate_limit_enabled, default False."""
        from secondbrain.config import Config

        model_fields = Config.model_fields

        assert "rate_limit_enabled" in model_fields
        assert model_fields["rate_limit_enabled"].default is False


class TestTracePropagationHooks:
    """create_trace_propagation_hooks and its wiring into the provider."""

    def setup_method(self):
        """Tracing is force-disabled by tests/conftest.py; start from that."""
        tracing_mod._tracing_enabled = False
        monkeypatch_delenv()

    def teardown_method(self):
        """Restore the conftest default (disabled) state."""
        tracing_mod._tracing_enabled = False
        monkeypatch_delenv()

    @staticmethod
    def _fake_request():
        """Stand-in for an httpx2 Request with a plain header mapping."""

        class _FakeRequest:
            def __init__(self):
                self.headers = {}

        return _FakeRequest()

    def test_returns_none_when_tracing_disabled(self):
        """No hooks when tracing is off (zero overhead)."""
        assert tracing_mod.create_trace_propagation_hooks() is None

    def test_returns_sync_and_async_flavors_when_enabled(self, monkeypatch):
        """Tracing enabled yields hook mappings for both client flavours."""
        monkeypatch.setattr(tracing_mod, "_tracing_enabled", True)

        hooks = tracing_mod.create_trace_propagation_hooks()

        assert hooks is not None
        assert hooks["sync"]["request"]
        assert hooks["async"]["request"]

    def test_hook_injects_current_trace_context(self, monkeypatch):
        """The sync hook writes traceparent from the current context."""
        monkeypatch.setattr(tracing_mod, "_tracing_enabled", True)
        request = self._fake_request()

        with tracing_mod.set_trace_context("a" * 32, "b" * 16, flags="0f"):
            hooks = tracing_mod.create_trace_propagation_hooks()
            assert hooks is not None
            for hook in hooks["sync"]["request"]:
                if not asyncio.iscoroutinefunction(hook):
                    hook(request)

        assert request.headers["traceparent"] == f"00-{'a' * 32}-{'b' * 16}-0f"

    async def test_async_hook_injects_current_trace_context(self, monkeypatch):
        """The async hook (used by AsyncClient) also writes traceparent."""
        monkeypatch.setattr(tracing_mod, "_tracing_enabled", True)
        request = self._fake_request()

        with tracing_mod.set_trace_context("c" * 32, "d" * 16):
            hooks = tracing_mod.create_trace_propagation_hooks()
            assert hooks is not None
            for hook in hooks["async"]["request"]:
                result = hook(request)
                if asyncio.iscoroutine(result):
                    await result

        assert request.headers["traceparent"] == f"00-{'c' * 32}-{'d' * 16}-01"

    def test_provider_sync_client_hook_fires_on_request(self, monkeypatch):
        """A real httpx2.Client built by the provider injects traceparent."""
        monkeypatch.setattr(tracing_mod, "_tracing_enabled", True)

        captured: dict[str, str] = {}

        def _capturing_transport():
            return httpx2.MockTransport(
                lambda request: (
                    captured.update(traceparent=request.headers.get("traceparent", "")),
                    httpx2.Response(200, json={"data": []}),
                )[1]
            )

        def _client_with_transport(**kwargs):
            return httpx2.Client(**{**kwargs, "transport": _capturing_transport()})

        # Replace only the provider's httpx2 binding so the built client uses
        # a capturing transport; the real httpx2 module stays intact for the
        # OpenAI SDK's isinstance checks.
        httpx2_stub = types.SimpleNamespace(
            Client=_client_with_transport,
            AsyncClient=httpx2.AsyncClient,
            Timeout=httpx2.Timeout,
        )
        with patch.object(openai_mod, "httpx2", httpx2_stub):
            provider = openai_mod.OpenAIEmbeddingProvider(
                model="text-embedding-3-small", api_key="sk-test"
            )

        provider._client._client.get("https://embedding.example.com/v1/models")

        assert captured["traceparent"].startswith("00-")

    async def test_provider_async_client_hook_fires_on_request(self, monkeypatch):
        """A real httpx2.AsyncClient built by the provider awaits its hook."""
        monkeypatch.setattr(tracing_mod, "_tracing_enabled", True)

        captured: dict[str, str] = {}

        def _capturing_transport():
            return httpx2.MockTransport(
                lambda request: (
                    captured.update(traceparent=request.headers.get("traceparent", "")),
                    httpx2.Response(200, json={"data": []}),
                )[1]
            )

        def _async_client_with_transport(**kwargs):
            return httpx2.AsyncClient(**{**kwargs, "transport": _capturing_transport()})

        httpx2_stub = types.SimpleNamespace(
            AsyncClient=_async_client_with_transport,
            Client=httpx2.Client,
            Timeout=httpx2.Timeout,
        )
        with patch.object(openai_mod, "httpx2", httpx2_stub):
            provider = openai_mod.OpenAIEmbeddingProvider(
                model="text-embedding-3-small", api_key="sk-test"
            )

        async def fire():
            async with provider._async_client._client as client:
                await client.get("https://embedding.example.com/v1/models")

        await fire()

        assert captured["traceparent"].startswith("00-")
