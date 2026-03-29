"""Memory management utilities for controlling RAM usage.

This module provides functions to:
- Calculate available system memory
- Determine safe worker count based on memory constraints
- Monitor memory usage during operations
"""

from __future__ import annotations

import logging
import os
import resource
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def get_available_memory_gb() -> float:
    """Get available system memory in GB.

    Returns:
        Available memory in gigabytes.
    """
    if sys.platform == "darwin" or sys.platform == "linux":
        try:
            # Try to get total memory from /proc or sysctl
            if sys.platform == "linux" and os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            # Convert from KB to GB
                            kb = int(line.split()[1])
                            return kb / (1024 * 1024)
            elif sys.platform == "darwin":
                import subprocess

                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                bytes_mem = int(result.stdout.strip())
                return bytes_mem / (1024 * 1024 * 1024)
        except Exception as e:
            logger.warning("Could not read system memory: %s", e)

    # Fallback: try psutil if available
    try:
        import psutil

        return psutil.virtual_memory().total / (1024 * 1024 * 1024)
    except ImportError:
        logger.warning(
            "psutil not available and could not read system memory. Using default 8GB"
        )
        return 8.0

    return 8.0  # Default fallback


def get_memory_limit_gb(percentage: float = 0.8) -> float:
    """Get memory limit in GB based on percentage of available memory.

    Args:
        percentage: Percentage of available memory to use (0.0-1.0).
                   Default is 0.8 (80%).

    Returns:
        Memory limit in gigabytes.
    """
    available_gb = get_available_memory_gb()
    return available_gb * percentage


def calculate_safe_worker_count(
    memory_limit_gb: float,
    estimated_memory_per_worker_gb: float = 0.5,
    min_workers: int = 1,
    max_workers: int | None = None,
) -> int:
    """Calculate safe number of worker processes based on memory constraints.

    Args:
        memory_limit_gb: Maximum memory to use in GB.
        estimated_memory_per_worker_gb: Estimated memory per worker in GB.
                                       Default 0.5GB (512MB) per worker.
        min_workers: Minimum number of workers to use.
        max_workers: Maximum number of workers to allow (None = no limit).

    Returns:
        Safe number of worker processes.
    """
    if memory_limit_gb <= 0:
        memory_limit_gb = 1.0  # Safety fallback

    # Calculate workers based on memory
    workers_by_memory = int(memory_limit_gb / estimated_memory_per_worker_gb)

    # Apply min/max constraints
    workers = max(min_workers, workers_by_memory)

    if max_workers is not None:
        workers = min(workers, max_workers)

    # Ensure at least 1 worker
    workers = max(1, workers)

    logger.info(
        "Calculated safe worker count: %d (memory limit: %.2fGB, "
        "estimated per worker: %.2fGB)",
        workers,
        memory_limit_gb,
        estimated_memory_per_worker_gb,
    )

    return workers


def get_current_memory_usage_mb() -> float:
    """Get current process memory usage in MB.

    Returns:
        Current memory usage in megabytes.
    """
    try:
        if sys.platform == "darwin" or sys.platform == "linux":
            # Get memory usage from resource module
            usage = resource.getrusage(resource.RUSAGE_SELF)
            # ru_maxrss is in KB on Linux/macOS
            return usage.ru_maxrss / 1024
    except Exception as e:
        logger.debug("Could not get current memory usage: %s", e)

    # Fallback: try psutil
    try:
        import psutil

        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def set_memory_limit_mb(limit_mb: float) -> bool:
    """Set memory limit for current process.

    Args:
        limit_mb: Memory limit in megabytes.

    Returns:
        True if limit was set successfully, False otherwise.
    """
    if sys.platform == "darwin" or sys.platform == "linux":
        try:
            # Convert MB to bytes
            limit_bytes = int(limit_mb * 1024 * 1024)
            # Get current limits
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            # Set new limit (keep hard limit unchanged or set to new value)
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, hard))
            logger.info("Set memory limit to %.2f MB", limit_mb)
            return True
        except Exception as e:
            logger.warning("Could not set memory limit: %s", e)
            return False

    logger.warning("Memory limiting not supported on this platform")
    return False


def check_memory_sufficient(
    required_gb: float, memory_limit_gb: float, safety_margin: float = 1.2
) -> bool:
    """Check if available memory is sufficient for required operations.

    Args:
        required_gb: Required memory in GB.
        memory_limit_gb: Memory limit in GB.
        safety_margin: Safety margin multiplier (default 1.2 = 20% buffer).

    Returns:
        True if memory is sufficient, False otherwise.
    """
    effective_limit = memory_limit_gb / safety_margin
    return required_gb <= effective_limit


class MemoryMonitor:
    """Monitor memory usage during operations."""

    def __init__(self, memory_limit_gb: float, warning_threshold: float = 0.8):
        """Initialize memory monitor.

        Args:
            memory_limit_gb: Memory limit in GB.
            warning_threshold: Threshold (0.0-1.0) for warning alerts.
        """
        self.memory_limit_gb = memory_limit_gb
        self.warning_threshold = warning_threshold
        self._peak_usage_mb = 0.0

    def check_and_warn(self) -> bool:
        """Check memory usage and warn if approaching limit.

        Returns:
            True if memory usage is safe, False if warning threshold exceeded.
        """
        current_mb = get_current_memory_usage_mb()
        current_gb = current_mb / 1024
        usage_ratio = current_gb / self.memory_limit_gb

        if usage_ratio > self.warning_threshold:
            logger.warning(
                "Memory usage at %.1f%% of limit (%.2fGB / %.2fGB)",
                usage_ratio * 100,
                current_gb,
                self.memory_limit_gb,
            )
            return False

        if current_mb > self._peak_usage_mb:
            self._peak_usage_mb = current_mb

        return True

    def get_usage_stats(self) -> dict:
        """Get current memory usage statistics.

        Returns:
            Dictionary with memory usage information.
        """
        current_mb = get_current_memory_usage_mb()
        current_gb = current_mb / 1024
        usage_ratio = current_gb / self.memory_limit_gb

        return {
            "current_mb": current_mb,
            "current_gb": current_gb,
            "limit_gb": self.memory_limit_gb,
            "usage_ratio": usage_ratio,
            "usage_percent": usage_ratio * 100,
            "peak_mb": self._peak_usage_mb,
        }
