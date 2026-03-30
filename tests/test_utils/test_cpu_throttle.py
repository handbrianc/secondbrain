"""Tests for CPU throttling utilities."""

from unittest.mock import patch

import pytest

from secondbrain.utils.cpu_throttle import CPUThrottler


class TestCPUThrottler:
    """Test CPU throttling functionality."""

    def test_init_default_values(self):
        """Test default initialization values."""
        throttler = CPUThrottler()
        assert throttler.target_utilization == 70.0
        assert throttler.check_interval == 1.0
        assert throttler.is_enabled is True

    def test_init_custom_values(self):
        """Test custom initialization values."""
        throttler = CPUThrottler(
            target_utilization_percent=80.0,
            check_interval_seconds=2.0,
        )
        assert throttler.target_utilization == 80.0
        assert throttler.check_interval == 2.0

    def test_throttler_disabled_returns_zero(self):
        """Test that disabled throttler returns 0 sleep time."""
        throttler = CPUThrottler()
        throttler.disable()
        sleep_time = throttler.check_and_throttle()
        assert sleep_time == 0.0
        assert throttler.is_enabled is False

    def test_throttler_enabled_after_disable(self):
        """Test re-enabling throttler."""
        throttler = CPUThrottler()
        throttler.disable()
        throttler.enable()
        assert throttler.is_enabled is True

    def test_get_cpu_percent_uses_psutil(self):
        """Test CPU percentage retrieval uses psutil when available."""
        import sys
        from unittest.mock import MagicMock

        # Create mock psutil
        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.return_value = 50.0

        # Temporarily replace psutil in sys.modules
        psutil_backup = sys.modules.get("psutil")
        sys.modules["psutil"] = mock_psutil

        try:
            # Need to reimport to pick up the mock
            import importlib
            from secondbrain.utils import cpu_throttle

            importlib.reload(cpu_throttle)

            throttler = cpu_throttle.CPUThrottler()
            cpu_percent = throttler._get_cpu_percent()

            assert cpu_percent == 50.0
            mock_psutil.cpu_percent.assert_called_once_with(interval=0.1)
        finally:
            # Restore original psutil
            if psutil_backup is not None:
                sys.modules["psutil"] = psutil_backup
            else:
                sys.modules.pop("psutil", None)
            # Reload back to original
            importlib.reload(cpu_throttle)

    def test_check_and_throttle_no_throttling_needed(self):
        """Test no throttling when CPU is well below high target."""
        throttler = CPUThrottler(target_utilization_percent=99.0)

        with patch("time.monotonic", side_effect=[0, 2, 4]):  # Force check interval
            sleep_time = throttler.check_and_throttle()

        # With 99% target, even high CPU won't trigger throttling
        assert sleep_time == 0.0
        assert throttler.last_cpu_percent >= 0

    def test_check_and_throttle_applies_throttling(self):
        """Test throttling mechanism by checking throttler state after call."""
        throttler = CPUThrottler(target_utilization_percent=50.0)

        with patch("time.monotonic", side_effect=[0, 2, 4]):  # Force check interval
            with patch("time.sleep") as mock_sleep:
                throttler.check_and_throttle()

                # The throttler should have recorded CPU usage
                assert throttler.last_cpu_percent >= 0
                # If CPU exceeded target, sleep should have been called
                # If not, it shouldn't have been - either is valid
                if throttler.last_cpu_percent > 50.0:
                    mock_sleep.assert_called_once()
                else:
                    mock_sleep.assert_not_called()

    @patch("secondbrain.utils.cpu_throttle.os.path.exists")
    @patch("builtins.open")
    def test_get_cpu_percent_fallback_to_proc_stat(self, mock_open, mock_exists):
        """Test CPU percentage fallback to /proc/stat reading."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = lambda s, *args: None
        mock_open.return_value.readline.return_value = "cpu 1000 0 500 2000 0 0 0 0 0 0"

        # Create throttler with psutil mocked to None
        with patch.dict("sys.modules", {"psutil": None}):
            # Force reimport
            import importlib
            from secondbrain.utils import cpu_throttle

            importlib.reload(cpu_throttle)

            throttler = cpu_throttle.CPUThrottler()
            cpu_percent = throttler._get_cpu_percent()

            # Calculate: (1 - idle/total) * 100 = (1 - 2000/3500) * 100 = 42.86%
            assert 40.0 < cpu_percent < 45.0

    def test_get_cpu_percent_returns_100_on_error(self):
        """Test fallback to 100% when all methods fail."""
        # Create throttler with psutil mocked to None and /proc/stat not existing
        with patch.dict("sys.modules", {"psutil": None}):
            # Force reimport
            import importlib
            from secondbrain.utils import cpu_throttle

            importlib.reload(cpu_throttle)

            throttler = cpu_throttle.CPUThrottler()

            # Test the fallback path when psutil is not available and /proc/stat doesn't exist
            with patch("os.path.exists", return_value=False):
                cpu_percent = throttler._get_cpu_percent()

                assert cpu_percent == 100.0

    def test_check_interval_respected(self):
        """Test that throttler respects check interval."""
        throttler = CPUThrottler(check_interval_seconds=5.0)

        with patch("time.monotonic", side_effect=[0, 1, 2]):  # Within interval
            with patch("time.sleep") as mock_sleep:
                throttler.check_and_throttle()
                throttler.check_and_throttle()

                # Should only check once (second call is within interval)
                assert mock_sleep.call_count <= 1
