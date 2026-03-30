"""Comprehensive tests for memory management utilities.

These tests improve branch coverage by testing all code paths including:
- Different platform behaviors (Linux, macOS, fallback)
- Error handling paths
- Edge cases and constraint boundaries
- MemoryMonitor class functionality
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from secondbrain.utils.memory_utils import (
    MemoryMonitor,
    calculate_safe_worker_count,
    check_memory_sufficient,
    get_available_memory_gb,
    get_current_memory_usage_mb,
    get_memory_limit_gb,
    set_memory_limit_mb,
)


class TestGetAvailableMemory:
    """Tests for get_available_memory_gb function."""

    @patch("builtins.open")
    @patch("os.path.exists")
    def test_linux_reads_from_proc_meminfo(self, mock_exists, mock_open):
        """Should read memory from /proc/meminfo on Linux."""
        mock_exists.return_value = True

        # Mock file content
        mock_file = MagicMock()
        mock_file.__iter__.return_value = [
            "MemTotal:       16384000 kB\n",
            "Other: 123\n",
        ]
        mock_open.return_value.__enter__.return_value = mock_file

        with patch.object(sys, "platform", "linux"):
            result = get_available_memory_gb()

            # 16384000 KB / (1024 * 1024) = 15.625 GB
            assert result == pytest.approx(15.625, rel=0.01)

    @patch("os.path.exists")
    def test_linux_missing_meminfo_falls_back(self, mock_exists):
        """Should fallback when /proc/meminfo doesn't exist."""
        mock_exists.return_value = False

        with patch("psutil.virtual_memory") as mock_psutil:
            mock_psutil.return_value.total = 8 * 1024 * 1024 * 1024  # 8GB

            with patch.object(sys, "platform", "linux"):
                result = get_available_memory_gb()
                assert result == 8.0

    @patch("subprocess.run")
    def test_macos_reads_from_sysctl(self, mock_run):
        """Should read memory from sysctl on macOS."""
        mock_run.return_value = MagicMock(stdout="17179869184\n")  # 16GB in bytes

        with patch.object(sys, "platform", "darwin"):
            result = get_available_memory_gb()

            # 17179869184 bytes / (1024^3) = 16GB
            assert result == pytest.approx(16.0, rel=0.01)

    @patch("subprocess.run")
    def test_macos_sysctl_failure_falls_back(self, mock_run):
        """Should fallback when sysctl fails on macOS."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "sysctl")

        with patch("psutil.virtual_memory") as mock_psutil:
            mock_psutil.return_value.total = 8 * 1024 * 1024 * 1024

            with patch.object(sys, "platform", "darwin"):
                result = get_available_memory_gb()
                assert result == 8.0

    def test_psutil_import_failure_uses_default(self, caplog):
        """Should use 8GB default when psutil is not available."""
        with patch("secondbrain.utils.memory_utils.sys.platform", "linux"):
            with patch("os.path.exists", return_value=False):
                with patch("builtins.__import__", side_effect=ImportError("psutil")):
                    result = get_available_memory_gb()
                    assert result == 8.0
                    assert "psutil not available" in caplog.messages[0]

    def test_unsupported_platform_uses_default(self, caplog):
        """Should use 8GB default on unsupported platforms."""
        with patch("secondbrain.utils.memory_utils.sys.platform", "win32"):
            with patch("builtins.__import__", side_effect=ImportError("psutil")):
                result = get_available_memory_gb()
                assert result == 8.0
                assert "psutil not available" in caplog.messages[0]


class TestGetMemoryLimit:
    """Tests for get_memory_limit_gb function."""

    @patch("secondbrain.utils.memory_utils.get_available_memory_gb")
    def test_returns_percentage_of_available(self, mock_available):
        """Should return specified percentage of available memory."""
        mock_available.return_value = 16.0

        result = get_memory_limit_gb(0.75)
        assert result == 12.0

    @patch("secondbrain.utils.memory_utils.get_available_memory_gb")
    def test_default_is_80_percent(self, mock_available):
        """Should default to 80% when percentage not specified."""
        mock_available.return_value = 10.0

        result = get_memory_limit_gb()
        assert result == 8.0

    @patch("secondbrain.utils.memory_utils.get_available_memory_gb")
    def test_100_percent_returns_all(self, mock_available):
        """Should return all available memory at 100%."""
        mock_available.return_value = 8.0

        result = get_memory_limit_gb(1.0)
        assert result == 8.0


class TestCalculateSafeWorkerCount:
    """Tests for calculate_safe_worker_count function."""

    def test_calculates_workers_based_on_memory(self):
        """Should calculate workers based on memory limit and per-worker estimate."""
        result = calculate_safe_worker_count(
            memory_limit_gb=4.0, estimated_memory_per_worker_gb=0.5
        )
        # 4.0 / 0.5 = 8 workers
        assert result == 8

    def test_enforces_minimum_workers(self):
        """Should enforce minimum worker count."""
        result = calculate_safe_worker_count(
            memory_limit_gb=0.5, estimated_memory_per_worker_gb=0.5, min_workers=4
        )
        # 0.5 / 0.5 = 1, but min is 4
        assert result == 4

    def test_enforces_maximum_workers(self):
        """Should enforce maximum worker count."""
        result = calculate_safe_worker_count(
            memory_limit_gb=16.0, estimated_memory_per_worker_gb=0.5, max_workers=10
        )
        # 16.0 / 0.5 = 32, but max is 10
        assert result == 10

    def test_handles_zero_memory_limit(self):
        """Should fallback to 1GB when memory limit is zero or negative."""
        result = calculate_safe_worker_count(
            memory_limit_gb=0, estimated_memory_per_worker_gb=0.5
        )
        # Should use 1.0 as fallback: 1.0 / 0.5 = 2 workers
        assert result == 2

    def test_handles_negative_memory_limit(self):
        """Should fallback to 1GB when memory limit is negative."""
        result = calculate_safe_worker_count(
            memory_limit_gb=-5.0, estimated_memory_per_worker_gb=0.5
        )
        assert result == 2

    def test_no_max_workers_uses_calculated(self):
        """Should use calculated value when no max specified."""
        result = calculate_safe_worker_count(
            memory_limit_gb=8.0, estimated_memory_per_worker_gb=0.5, max_workers=None
        )
        assert result == 16

    def test_respects_min_when_calculated_is_higher(self):
        """Should use calculated value when it's higher than minimum."""
        result = calculate_safe_worker_count(
            memory_limit_gb=8.0, estimated_memory_per_worker_gb=0.5, min_workers=2
        )
        # 8.0 / 0.5 = 16, min is 2, so use 16
        assert result == 16

    def test_both_min_and_max_constraints(self):
        """Should respect both min and max constraints."""
        result = calculate_safe_worker_count(
            memory_limit_gb=2.0,
            estimated_memory_per_worker_gb=0.5,
            min_workers=8,
            max_workers=4,
        )
        # 2.0 / 0.5 = 4, min is 8, max is 4
        # max(8, 4) = 8, then min(8, 4) = 4
        assert result == 4

    def test_ensures_at_least_one_worker(self):
        """Should ensure at least 1 worker even with very low memory."""
        result = calculate_safe_worker_count(
            memory_limit_gb=0.1, estimated_memory_per_worker_gb=1.0
        )
        # 0.1 / 1.0 = 0, but ensures at least 1
        assert result == 1


class TestGetCurrentMemoryUsage:
    """Tests for get_current_memory_usage_mb function."""

    @patch("resource.getrusage")
    def test_linux_returns_resource_usage(self, mock_getrusage):
        """Should return memory from resource module on Linux."""
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 102400  # 100MB in KB
        mock_getrusage.return_value = mock_usage

        with patch.object(sys, "platform", "linux"):
            result = get_current_memory_usage_mb()
            assert result == 100.0

    @patch("resource.getrusage")
    def test_macos_returns_resource_usage(self, mock_getrusage):
        """Should return memory from resource module on macOS."""
        mock_usage = MagicMock()
        mock_usage.ru_maxrss = 51200  # 50MB in KB
        mock_getrusage.return_value = mock_usage

        with patch.object(sys, "platform", "darwin"):
            result = get_current_memory_usage_mb()
            assert result == 50.0

    @patch("resource.getrusage")
    def test_resource_failure_falls_back_to_psutil(self, mock_getrusage):
        """Should fallback to psutil when resource fails."""
        mock_getrusage.side_effect = Exception("Resource error")

        with patch("psutil.Process") as mock_process:
            mock_process.return_value.memory_info.return_value.rss = 209715200  # 200MB

            with patch.object(sys, "platform", "linux"):
                result = get_current_memory_usage_mb()
                assert result == 200.0

    def test_psutil_not_available_returns_zero(self):
        """Should return 0 when psutil is not available."""
        with patch("resource.getrusage", side_effect=Exception()):
            with patch("secondbrain.utils.memory_utils.sys.platform", "linux"):
                with patch("builtins.__import__", side_effect=ImportError("psutil")):
                    result = get_current_memory_usage_mb()
                    assert result == 0.0

    def test_psutil_os_error_returns_zero(self):
        """Should return 0 on OSError from psutil."""
        with patch("resource.getrusage", side_effect=Exception()):
            with patch("psutil.Process", side_effect=OSError()):
                with patch.object(sys, "platform", "linux"):
                    result = get_current_memory_usage_mb()
                    assert result == 0.0


class TestSetMemoryLimit:
    """Tests for set_memory_limit_mb function."""

    @patch("resource.getrlimit")
    @patch("resource.setrlimit")
    def test_sets_limit_on_linux(self, mock_setrlimit, mock_getrlimit):
        """Should set memory limit on Linux."""
        mock_getrlimit.return_value = (1073741824, 2147483648)  # 1GB soft, 2GB hard

        with patch.object(sys, "platform", "linux"):
            result = set_memory_limit_mb(512)  # 512MB

            assert result is True
            mock_setrlimit.assert_called_once()

    @patch("resource.getrlimit")
    @patch("resource.setrlimit")
    def test_sets_limit_on_macos(self, mock_setrlimit, mock_getrlimit):
        """Should set memory limit on macOS."""
        mock_getrlimit.return_value = (1073741824, 2147483648)

        with patch.object(sys, "platform", "darwin"):
            result = set_memory_limit_mb(256)

            assert result is True

    def test_returns_false_on_windows(self):
        """Should return False on Windows."""
        with patch.object(sys, "platform", "win32"):
            result = set_memory_limit_mb(512)
            assert result is False

    @patch("resource.getrlimit")
    def test_returns_false_on_exception(self, mock_getrlimit):
        """Should return False when setting limit fails."""
        mock_getrlimit.side_effect = Exception("Set limit failed")

        with patch.object(sys, "platform", "linux"):
            result = set_memory_limit_mb(512)
            assert result is False


class TestCheckMemorySufficient:
    """Tests for check_memory_sufficient function."""

    def test_returns_true_when_memory_sufficient(self):
        """Should return True when memory is sufficient."""
        # 5GB required, 10GB limit, 1.2 safety margin
        # Effective limit = 10 / 1.2 = 8.33GB
        # 5GB <= 8.33GB → True
        result = check_memory_sufficient(
            required_gb=5.0, memory_limit_gb=10.0, safety_margin=1.2
        )
        assert result is True

    def test_returns_false_when_memory_insufficient(self):
        """Should return False when memory is insufficient."""
        # 9GB required, 10GB limit, 1.2 safety margin
        # Effective limit = 10 / 1.2 = 8.33GB
        # 9GB > 8.33GB → False
        result = check_memory_sufficient(
            required_gb=9.0, memory_limit_gb=10.0, safety_margin=1.2
        )
        assert result is False

    def test_safety_margin_affects_result(self):
        """Should consider safety margin in calculation."""
        # Without safety margin (1.0): 8GB required, 10GB limit → True
        # With safety margin (1.5): 8GB required, 10/1.5=6.67GB effective → False
        result_no_margin = check_memory_sufficient(8.0, 10.0, 1.0)
        result_with_margin = check_memory_sufficient(8.0, 10.0, 1.5)

        assert result_no_margin is True
        assert result_with_margin is False

    def test_exact_match_returns_true(self):
        """Should return True when required equals effective limit."""
        # 8.33GB required, 10GB limit, 1.2 margin → 8.33GB effective
        result = check_memory_sufficient(
            required_gb=8.333, memory_limit_gb=10.0, safety_margin=1.2
        )
        assert result is True


class TestMemoryMonitor:
    """Tests for MemoryMonitor class."""

    def test_init_sets_attributes(self):
        """Should initialize with correct attributes."""
        monitor = MemoryMonitor(memory_limit_gb=8.0, warning_threshold=0.9)

        assert monitor.memory_limit_gb == 8.0
        assert monitor.warning_threshold == 0.9
        assert monitor._peak_usage_mb == 0.0

    @patch("secondbrain.utils.memory_utils.get_current_memory_usage_mb")
    def test_check_and_warn_returns_true_when_safe(self, mock_current):
        """Should return True when memory usage is below threshold."""
        mock_current.return_value = 4096  # 4GB

        monitor = MemoryMonitor(memory_limit_gb=8.0, warning_threshold=0.8)
        result = monitor.check_and_warn()

        assert result is True

    @patch("secondbrain.utils.memory_utils.get_current_memory_usage_mb")
    def test_check_and_warn_returns_false_when_above_threshold(
        self, mock_current, caplog
    ):
        """Should return False and warn when above threshold."""
        mock_current.return_value = 7168  # 7GB (87.5% of 8GB)

        monitor = MemoryMonitor(memory_limit_gb=8.0, warning_threshold=0.8)

        with caplog.at_level("WARNING"):
            result = monitor.check_and_warn()

            assert result is False
            assert any("memory usage" in msg.lower() for msg in caplog.messages)

    @patch("secondbrain.utils.memory_utils.get_current_memory_usage_mb")
    def test_tracks_peak_usage(self, mock_current):
        """Should track peak memory usage."""
        mock_current.side_effect = [1024, 2048, 1536, 3072]  # Peak should be 3072

        monitor = MemoryMonitor(memory_limit_gb=8.0)

        monitor.check_and_warn()
        monitor.check_and_warn()
        monitor.check_and_warn()
        monitor.check_and_warn()

        assert monitor._peak_usage_mb == 3072

    @patch("secondbrain.utils.memory_utils.get_current_memory_usage_mb")
    def test_get_usage_stats_returns_correct_dict(self, mock_current):
        """Should return correct usage statistics."""
        mock_current.return_value = 4096  # 4GB

        monitor = MemoryMonitor(memory_limit_gb=8.0, warning_threshold=0.7)
        stats = monitor.get_usage_stats()

        assert stats["current_mb"] == 4096
        assert stats["current_gb"] == pytest.approx(4.0)
        assert stats["limit_gb"] == 8.0
        assert stats["usage_ratio"] == pytest.approx(0.5)
        assert stats["usage_percent"] == pytest.approx(50.0)
        assert "peak_mb" in stats

    @patch("secondbrain.utils.memory_utils.get_current_memory_usage_mb")
    def test_peak_updates_only_on_increase(self, mock_current):
        """Should only update peak when current usage increases."""
        mock_current.side_effect = [2048, 1024, 4096]  # 2GB, 1GB, 4GB

        monitor = MemoryMonitor(memory_limit_gb=8.0)

        monitor.check_and_warn()  # Peak = 2GB
        monitor.check_and_warn()  # 1GB < 2GB, peak stays 2GB
        monitor.check_and_warn()  # 4GB > 2GB, peak = 4GB

        assert monitor._peak_usage_mb == 4096
