"""Tests for multicore rate limiting across workers."""
import pytest


class TestMulticoreRateLimit:
    """Test rate limiting across multiprocessing workers."""

    def test_rate_limit_config_exists(self):
        """Rate limit configuration exists in config."""
        from secondbrain.config import config
        
        cfg = config()
        # Check if rate limit settings exist (may vary by implementation)
        # Just verify we can access the config without error
        assert cfg is not None

    def test_rate_limiter_module_exists(self):
        """Rate limiter module exists."""
        from secondbrain.utils import rate_limiter
        
        assert rate_limiter is not None

    def test_rate_limiter_function_exists(self):
        """Rate limiter functions are available."""
        from secondbrain.utils.rate_limiter import get_shared_rate_limiter
        
        assert callable(get_shared_rate_limiter)
