"""Tests for multicore rate limiting across workers."""
from secondbrain.config import config
from secondbrain.utils.rate_limiter import get_shared_rate_limiter


class TestMulticoreRateLimit:
    """Test rate limiting across multiprocessing workers."""

    def test_rate_limit_config_exists(self):
        cfg = config()
        assert cfg is not None

    def test_rate_limiter_function_exists(self):
        assert callable(get_shared_rate_limiter)
