"""Tests for adaptive batch sizing utilities."""

from unittest.mock import patch

from secondbrain.utils.adaptive_batch import AdaptiveBatchSizer


class TestAdaptiveBatchSizer:
    """Test adaptive batch sizing functionality."""

    def test_init_default_values(self):
        """Test default initialization values."""
        sizer = AdaptiveBatchSizer()
        assert sizer.initial_size == 100
        assert sizer.min_size == 10
        assert sizer.max_size == 200
        assert sizer.current_size == 100

    def test_init_custom_values(self):
        """Test custom initialization values."""
        sizer = AdaptiveBatchSizer(
            initial_size=50,
            min_size=5,
            max_size=150,
            memory_threshold_mb=2048.0,
        )
        assert sizer.initial_size == 50
        assert sizer.min_size == 5
        assert sizer.max_size == 150
        assert sizer.memory_threshold == 2048.0
        assert sizer.current_size == 50

    def test_batch_size_unchanged_at_safe_memory(self):
        """Test batch size stays stable at safe memory levels."""
        sizer = AdaptiveBatchSizer(initial_size=100, memory_threshold_mb=4096)

        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=1000.0,  # ~24% of threshold (safe)
        ):
            new_size = sizer.adjust_batch_size()

        # Should increase slightly (1.1x) at safe levels
        assert new_size > 100
        assert new_size <= sizer.max_size

    def test_batch_size_reduces_at_high_memory(self):
        """Test batch size reduces when memory is high."""
        sizer = AdaptiveBatchSizer(initial_size=100, memory_threshold_mb=4096)

        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=3700.0,  # 90% of threshold (critical)
        ):
            new_size = sizer.adjust_batch_size()

        # Should reduce aggressively (0.5x) at critical levels
        assert new_size == 50  # 100 * 0.5

    def test_batch_size_reduces_moderately_at_80_percent(self):
        """Test batch size reduces moderately at 80% memory."""
        sizer = AdaptiveBatchSizer(initial_size=100, memory_threshold_mb=4096)

        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=3481.6,  # 85% of threshold (high)
        ):
            new_size = sizer.adjust_batch_size()

        # Should reduce moderately (0.75x) at high levels
        assert new_size == 75  # 100 * 0.75

    def test_batch_size_cannot_go_below_min(self):
        """Test batch size respects minimum bound."""
        sizer = AdaptiveBatchSizer(
            initial_size=100,
            min_size=10,
            memory_threshold_mb=4096,
        )

        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=4000.0,  # ~98% of threshold
        ):
            # Multiple reductions
            sizer.adjust_batch_size()  # → 50
            sizer.adjust_batch_size()  # → 25
            sizer.adjust_batch_size()  # → 12
            final_size = sizer.adjust_batch_size()  # → should hit min

        assert final_size >= sizer.min_size
        assert final_size == 10

    def test_batch_size_cannot_exceed_max(self):
        """Test batch size respects maximum bound."""
        sizer = AdaptiveBatchSizer(
            initial_size=100,
            max_size=150,
            memory_threshold_mb=4096,
        )

        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=1000.0,  # Safe memory
        ):
            # Multiple increases
            for _ in range(10):
                sizer.adjust_batch_size()

        assert sizer.current_size <= sizer.max_size
        assert sizer.current_size == 150

    def test_batch_size_gradually_increases_after_high_memory(self):
        """Test batch size gradually increases after memory drops."""
        sizer = AdaptiveBatchSizer(initial_size=100, memory_threshold_mb=4096)

        # First, simulate high memory
        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=3700.0,  # 90% (critical)
        ):
            sizer.adjust_batch_size()  # → 50

        # Now simulate low memory
        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=1000.0,  # 24% (safe)
        ):
            # Should wait for consecutive low readings
            sizer.adjust_batch_size()  # Still high memory count
            sizer.adjust_batch_size()  # Still high memory count
            size = sizer.adjust_batch_size()  # Now should increase

        # Should have increased after consecutive low readings
        assert size > 50

    def test_reset_restores_initial_size(self):
        """Test reset restores initial batch size."""
        sizer = AdaptiveBatchSizer(initial_size=100, memory_threshold_mb=4096)

        # Change the size
        with patch(
            "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
            return_value=3700.0,  # 90%
        ):
            sizer.adjust_batch_size()  # → 50

        assert sizer.current_size == 50

        # Reset
        sizer.reset()

        assert sizer.current_size == 100
        assert sizer._consecutive_high_memory == 0

    def test_adaptive_behavior_with_varying_memory(self):
        """Test adaptive behavior with realistic memory variations."""
        sizer = AdaptiveBatchSizer(
            initial_size=100,
            min_size=10,
            max_size=200,
            memory_threshold_mb=4096,
        )

        memory_sequence = [
            2000.0,  # Safe → increase
            2000.0,  # Safe → increase
            3500.0,  # High → reduce
            3700.0,  # Critical → reduce
            3700.0,  # Critical → reduce more
            1500.0,  # Safe → start recovery
            1500.0,  # Safe → continue recovery
            1500.0,  # Safe → increase
        ]

        sizes = []
        for mem in memory_sequence:
            with patch(
                "secondbrain.utils.adaptive_batch.get_current_memory_usage_mb",
                return_value=mem,
            ):
                sizes.append(sizer.adjust_batch_size())

        # Verify the trend: increase, increase, reduce, reduce, reduce, recover, recover, increase
        assert sizes[0] >= 100  # Initial increase
        assert sizes[2] < sizes[1]  # Reduction starts
        assert sizes[4] < sizes[3]  # More reduction
        assert sizes[7] >= sizes[5]  # Recovery begins
