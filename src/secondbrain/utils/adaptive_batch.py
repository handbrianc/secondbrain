"""Adaptive batch processing with memory-based sizing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from secondbrain.utils.memory_utils import get_current_memory_usage_mb

logger = logging.getLogger(__name__)


class AdaptiveBatchSizer:
    """Dynamically adjust batch size based on memory usage.

    This sizer monitors current memory usage and adjusts batch sizes
    to prevent memory exhaustion during long-running operations like
    document ingestion.
    """

    def __init__(
        self,
        initial_size: int = 100,
        min_size: int = 10,
        max_size: int = 200,
        memory_threshold_mb: float = 4096.0,
    ):
        """Initialize adaptive batch sizer.

        Args:
            initial_size: Starting batch size.
            min_size: Minimum batch size.
            max_size: Maximum batch size.
            memory_threshold_mb: Memory threshold for reduction.
        """
        self.initial_size = initial_size
        self.min_size = min_size
        self.max_size = max_size
        self.memory_threshold = memory_threshold_mb
        self._current_size = initial_size
        self._consecutive_high_memory = 0

    def adjust_batch_size(self) -> int:
        """Adjust batch size based on current memory usage.

        Returns:
            Adjusted batch size.
        """
        current_mb = get_current_memory_usage_mb()
        usage_ratio = current_mb / self.memory_threshold

        if usage_ratio > 0.9:
            self._current_size = max(self.min_size, int(self._current_size * 0.5))
            self._consecutive_high_memory += 3
            logger.warning(
                "Critical memory usage: %.1fMB (threshold: %.0fMB), "
                "reduced batch size to %d",
                current_mb,
                self.memory_threshold,
                self._current_size,
            )
        elif usage_ratio > 0.8:
            self._current_size = max(self.min_size, int(self._current_size * 0.75))
            self._consecutive_high_memory += 1
            logger.info(
                "High memory usage: %.1fMB (threshold: %.0fMB), "
                "reduced batch size to %d",
                current_mb,
                self.memory_threshold,
                self._current_size,
            )
        elif usage_ratio < 0.5 and self._consecutive_high_memory > 0:
            self._consecutive_high_memory = max(0, self._consecutive_high_memory - 1)
            if self._consecutive_high_memory == 0:
                self._current_size = min(self.max_size, int(self._current_size * 1.2))
                logger.debug(
                    "Low memory usage: %.1fMB, increased batch size to %d",
                    current_mb,
                    self._current_size,
                )
        elif usage_ratio < 0.6:
            self._current_size = min(self.max_size, int(self._current_size * 1.1))
            logger.debug(
                "Safe memory usage: %.1fMB, increased batch size to %d",
                current_mb,
                self._current_size,
            )

        return self._current_size

    @property
    def current_size(self) -> int:
        """Get current batch size."""
        return self._current_size

    def reset(self) -> None:
        """Reset to initial size."""
        self._current_size = self.initial_size
        self._consecutive_high_memory = 0
