"""CPU throttling utilities for controlling processor utilization."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CPUThrottler:
    """Monitor and throttle CPU utilization across worker processes.

    This throttler monitors system CPU usage and introduces delays when
    utilization exceeds the target threshold, preventing the application
    from consuming 100% CPU resources.
    """

    def __init__(
        self,
        target_utilization_percent: float = 70.0,
        check_interval_seconds: float = 1.0,
    ):
        """Initialize CPU throttler.

        Args:
            target_utilization_percent: Target CPU utilization (50-95).
            check_interval_seconds: Interval between CPU checks.
        """
        self.target_utilization = target_utilization_percent
        self.check_interval = check_interval_seconds
        self._enabled = True
        self._last_check_time = 0.0
        self._last_cpu_percent = 0.0

    def check_and_throttle(self) -> float:
        """Check CPU usage and throttle if necessary.

        Returns:
            Sleep time in seconds (0 if no throttling needed).
        """
        if not self._enabled:
            return 0.0

        current_time = time.monotonic()
        if current_time - self._last_check_time < self.check_interval:
            return 0.0

        try:
            cpu_percent = self._get_cpu_percent()
            self._last_cpu_percent = cpu_percent
            self._last_check_time = current_time

            if cpu_percent > self.target_utilization:
                excess_ratio = (cpu_percent - self.target_utilization) / (
                    100.0 - self.target_utilization
                )
                sleep_time = min(0.5, excess_ratio * 0.3)

                logger.debug(
                    "CPU throttling: %.1f%% utilization (target: %.1f%%), "
                    "sleeping for %.3fs",
                    cpu_percent,
                    self.target_utilization,
                    sleep_time,
                )

                time.sleep(sleep_time)
                return sleep_time

            return 0.0

        except Exception as e:
            logger.debug("CPU throttling check failed: %s", e)
            return 0.0

    def _get_cpu_percent(self) -> float:
        """Get current CPU utilization percentage.

        Returns:
            CPU utilization as percentage (0-100).
        """
        try:
            import psutil

            return float(psutil.cpu_percent(interval=0.1))
        except ImportError:
            pass

        # Read /proc/stat directly for CPU usage (system file, not a regular path)
        if os.path.exists("/proc/stat"):  # noqa: PTH110
            try:
                with open("/proc/stat") as f:  # noqa: PTH123
                    line = f.readline()
                    if line.startswith("cpu "):
                        parts = line.split()[1:8]
                        user, nice, system, idle = map(int, parts[:4])
                        total = user + nice + system + idle
                        if total > 0:
                            return (1.0 - (idle / total)) * 100.0
            except Exception:
                pass

        return 100.0

    def disable(self) -> None:
        """Disable CPU throttling."""
        self._enabled = False

    def enable(self) -> None:
        """Enable CPU throttling."""
        self._enabled = True

    @property
    def is_enabled(self) -> bool:
        """Check if throttling is enabled."""
        return self._enabled

    @property
    def last_cpu_percent(self) -> float:
        """Get last measured CPU percentage."""
        return self._last_cpu_percent
