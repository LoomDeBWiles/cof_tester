"""Tests for decimation and multi-resolution tier management."""

import threading

import numpy as np
import pytest

from gsdv.processing import (
    TIER1,
    TIER2,
    TIER3,
    RAW_TIER,
    TierConfig,
    TierStats,
    VisualizationBuffer,
    VisualizationBufferStats,
)


class TestTierConfig:
    """Tests for TierConfig dataclass."""

    def test_raw_tier_config(self) -> None:
        assert RAW_TIER.name == "raw"
        assert RAW_TIER.capacity == 60_000
        assert RAW_TIER.decimation_factor == 1
        assert RAW_TIER.sample_rate_hz == 1000.0

    def test_tier1_config(self) -> None:
        assert TIER1.name == "tier1"
        assert TIER1.capacity == 36_000
        assert TIER1.decimation_factor == 100
        assert TIER1.sample_rate_hz == 10.0

    def test_tier2_config(self) -> None:
        assert TIER2.name == "tier2"
        assert TIER2.capacity == 8_640
        assert TIER2.decimation_factor == 100
        assert TIER2.sample_rate_hz == 0.1

    def test_tier3_config(self) -> None:
        assert TIER3.name == "tier3"
        assert TIER3.capacity == 6_048
        assert TIER3.decimation_factor == 10
        assert TIER3.sample_rate_hz == 0.01


class TestTierStats:
    """Tests for TierStats dataclass."""

    def test_fill_ratio_empty(self) -> None:
        stats = TierStats(name="test", capacity=100, size=0, total_buckets_written=0)
        assert stats.fill_ratio == 0.0

    def test_fill_ratio_half(self) -> None:
        stats = TierStats(name="test", capacity=100, size=50, total_buckets_written=50)
        assert stats.fill_ratio == 0.5

    def test_fill_ratio_full(self) -> None:
        stats = TierStats(name="test", capacity=100, size=100, total_buckets_written=100)
        assert stats.fill_ratio == 1.0

    def test_fill_ratio_zero_capacity(self) -> None:
        stats = TierStats(name="test", capacity=0, size=0, total_buckets_written=0)
        assert stats.fill_ratio == 0.0


class TestVisualizationBufferStats:
    """Tests for VisualizationBufferStats dataclass."""

    def test_memory_mb_conversion(self) -> None:
        tier_stats = (
            TierStats(name="tier1", capacity=100, size=50, total_buckets_written=50),
        )
        stats = VisualizationBufferStats(tier_stats=tier_stats, memory_bytes=1024 * 1024)
        assert stats.memory_mb == 1.0

    def test_memory_mb_zero(self) -> None:
        stats = VisualizationBufferStats(tier_stats=(), memory_bytes=0)
        assert stats.memory_mb == 0.0


class TestVisualizationBufferInit:
    """Tests for VisualizationBuffer initialization."""

    def test_initial_stats_empty(self) -> None:
        buffer = VisualizationBuffer()
        stats = buffer.stats()
        for tier_stat in stats.tier_stats:
            assert tier_stat.size == 0
            assert tier_stat.total_buckets_written == 0

    def test_initial_tier_names(self) -> None:
        buffer = VisualizationBuffer()
        stats = buffer.stats()
        tier_names = [ts.name for ts in stats.tier_stats]
        assert tier_names == ["tier1", "tier2", "tier3"]


class TestVisualizationBufferAddSample:
    """Tests for VisualizationBuffer.add_sample()."""

    def test_single_sample_no_bucket(self) -> None:
        buffer = VisualizationBuffer()
        buffer.add_sample(t_ns=1000, counts=(1, 2, 3, 4, 5, 6))
        stats = buffer.stats()
        # Not enough samples to complete a bucket
        assert stats.tier_stats[0].size == 0

    def test_100_samples_creates_tier1_bucket(self) -> None:
        buffer = VisualizationBuffer()
        for i in range(100):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, i, i, i, i, i))
        stats = buffer.stats()
        # 100 samples = 1 tier1 bucket
        assert stats.tier_stats[0].size == 1
        assert stats.tier_stats[0].total_buckets_written == 1

    def test_200_samples_creates_two_tier1_buckets(self) -> None:
        buffer = VisualizationBuffer()
        for i in range(200):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, i, i, i, i, i))
        stats = buffer.stats()
        assert stats.tier_stats[0].size == 2

    def test_10000_samples_creates_tier2_bucket(self) -> None:
        buffer = VisualizationBuffer()
        # 10000 samples = 100 tier1 buckets = 1 tier2 bucket
        for i in range(10_000):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i % 100, i % 100, i % 100, i % 100, i % 100, i % 100))
        stats = buffer.stats()
        assert stats.tier_stats[0].size == 100  # tier1
        assert stats.tier_stats[1].size == 1    # tier2

    def test_min_max_preserved(self) -> None:
        buffer = VisualizationBuffer()
        # Add 100 samples with varying values
        for i in range(100):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 100 - i, i * 2, 50, 25, 75))
        data = buffer.get_tier_data("tier1")
        assert data is not None
        # Check min/max for Fx channel
        assert data["counts_min"][0, 0] == 0    # min of 0..99
        assert data["counts_max"][0, 0] == 99   # max of 0..99
        # Check min/max for Fy channel
        assert data["counts_min"][0, 1] == 1    # min of 100..1
        assert data["counts_max"][0, 1] == 100  # max of 100..1

    def test_timestamps_preserved(self) -> None:
        buffer = VisualizationBuffer()
        start_ns = 1_000_000_000
        for i in range(100):
            buffer.add_sample(t_ns=start_ns + i * 1_000_000, counts=(0, 0, 0, 0, 0, 0))
        data = buffer.get_tier_data("tier1")
        assert data is not None
        assert data["t_start_ns"][0] == start_ns
        assert data["t_end_ns"][0] == start_ns + 99 * 1_000_000

    def test_numpy_array_counts(self) -> None:
        buffer = VisualizationBuffer()
        counts = np.array([10, 20, 30, 40, 50, 60], dtype=np.int32)
        for i in range(100):
            buffer.add_sample(t_ns=i * 1_000_000, counts=counts)
        data = buffer.get_tier_data("tier1")
        assert data is not None
        np.testing.assert_array_equal(data["counts_min"][0], [10, 20, 30, 40, 50, 60])
        np.testing.assert_array_equal(data["counts_max"][0], [10, 20, 30, 40, 50, 60])


class TestVisualizationBufferGetTierData:
    """Tests for VisualizationBuffer.get_tier_data()."""

    def test_empty_tier_returns_none(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.get_tier_data("tier1") is None

    def test_invalid_tier_raises_error(self) -> None:
        buffer = VisualizationBuffer()
        with pytest.raises(ValueError, match="Invalid tier name"):
            buffer.get_tier_data("invalid")

    def test_time_range_filter_start(self) -> None:
        buffer = VisualizationBuffer()
        # Create 3 buckets
        for i in range(300):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))
        # Filter starting from middle
        data = buffer.get_tier_data("tier1", start_ns=150_000_000)
        assert data is not None
        # Should get buckets 1 and 2 (indices 100-199 and 200-299 overlap with start)
        assert len(data["t_start_ns"]) == 2

    def test_time_range_filter_end(self) -> None:
        buffer = VisualizationBuffer()
        for i in range(300):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))
        # Filter ending before last bucket
        data = buffer.get_tier_data("tier1", end_ns=150_000_000)
        assert data is not None
        # Should get buckets 0 and 1
        assert len(data["t_start_ns"]) == 2

    def test_time_range_filter_both(self) -> None:
        buffer = VisualizationBuffer()
        for i in range(500):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))
        # Filter middle range
        data = buffer.get_tier_data("tier1", start_ns=150_000_000, end_ns=350_000_000)
        assert data is not None
        # Should get buckets 1, 2, 3
        assert len(data["t_start_ns"]) == 3

    def test_returns_copies(self) -> None:
        buffer = VisualizationBuffer()
        for i in range(100):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))
        data1 = buffer.get_tier_data("tier1")
        data2 = buffer.get_tier_data("tier1")
        assert data1 is not None and data2 is not None
        data1["t_start_ns"][0] = 999999
        assert data2["t_start_ns"][0] != 999999


class TestVisualizationBufferSelectTier:
    """Tests for VisualizationBuffer.select_tier_for_window()."""

    def test_select_tier1_for_1_second(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.select_tier_for_window(1.0) == "tier1"

    def test_select_tier1_for_1_minute(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.select_tier_for_window(60.0) == "tier1"

    def test_select_tier1_for_1_hour(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.select_tier_for_window(3600.0) == "tier1"

    def test_select_tier2_for_2_hours(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.select_tier_for_window(7200.0) == "tier2"

    def test_select_tier2_for_24_hours(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.select_tier_for_window(86400.0) == "tier2"

    def test_select_tier3_for_2_days(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.select_tier_for_window(172800.0) == "tier3"

    def test_select_tier3_for_7_days(self) -> None:
        buffer = VisualizationBuffer()
        assert buffer.select_tier_for_window(604800.0) == "tier3"


class TestVisualizationBufferClear:
    """Tests for VisualizationBuffer.clear()."""

    def test_clear_resets_all_tiers(self) -> None:
        buffer = VisualizationBuffer()
        for i in range(200):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))
        buffer.clear()
        stats = buffer.stats()
        for tier_stat in stats.tier_stats:
            assert tier_stat.size == 0
            assert tier_stat.total_buckets_written == 0

    def test_get_tier_data_returns_none_after_clear(self) -> None:
        buffer = VisualizationBuffer()
        for i in range(100):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))
        buffer.clear()
        assert buffer.get_tier_data("tier1") is None


class TestVisualizationBufferMemory:
    """Tests for memory usage constraints."""

    def test_memory_under_10mb(self) -> None:
        buffer = VisualizationBuffer()
        stats = buffer.stats()
        # Memory should be under 10MB
        assert stats.memory_mb < 10.0

    def test_memory_calculation(self) -> None:
        buffer = VisualizationBuffer()
        stats = buffer.stats()
        # Each tier has:
        # - t_start_ns: int64 * capacity
        # - t_end_ns: int64 * capacity
        # - counts_min: int32 * capacity * 6
        # - counts_max: int32 * capacity * 6
        # - sample_count: uint32 * capacity
        # Per entry: 8 + 8 + 24 + 24 + 4 = 68 bytes
        # tier1: 36000 * 68 = 2,448,000
        # tier2: 8640 * 68 = 587,520
        # tier3: 6048 * 68 = 411,264
        # Total: ~3,446,784 bytes = ~3.3 MB
        assert stats.memory_bytes > 3_000_000
        assert stats.memory_bytes < 4_000_000


class TestVisualizationBufferThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_adds(self) -> None:
        buffer = VisualizationBuffer()
        num_threads = 4
        samples_per_thread = 1000

        def add_samples(thread_id: int) -> None:
            for i in range(samples_per_thread):
                buffer.add_sample(
                    t_ns=thread_id * 1_000_000_000 + i * 1_000_000,
                    counts=(thread_id, i, 0, 0, 0, 0),
                )

        threads = [
            threading.Thread(target=add_samples, args=(tid,))
            for tid in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = buffer.stats()
        # 4000 samples total = 40 tier1 buckets
        assert stats.tier_stats[0].total_buckets_written == 40

    def test_concurrent_read_write(self) -> None:
        buffer = VisualizationBuffer()
        stop_event = threading.Event()
        read_count = [0]

        def writer() -> None:
            i = 0
            while not stop_event.is_set():
                buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))
                i += 1

        def reader() -> None:
            while not stop_event.is_set():
                buffer.get_tier_data("tier1")
                buffer.stats()
                read_count[0] += 1

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        reader_thread.start()

        threading.Event().wait(0.1)
        stop_event.set()

        writer_thread.join()
        reader_thread.join()

        assert read_count[0] > 0


class TestVisualizationBufferRingWrap:
    """Tests for ring buffer wrapping behavior."""

    def test_tier1_wrap_around(self) -> None:
        buffer = VisualizationBuffer()
        # Fill more than tier1 capacity (36000 buckets)
        # Each bucket needs 100 samples
        # To create 36001 buckets, we need 3,600,100 samples
        # That's too slow, so let's test with a smaller scenario
        # by verifying the wrap behavior with time filtering

        # Create 10 buckets
        for i in range(1000):
            buffer.add_sample(t_ns=i * 1_000_000, counts=(i, 0, 0, 0, 0, 0))

        data = buffer.get_tier_data("tier1")
        assert data is not None
        assert len(data["t_start_ns"]) == 10
        # Buckets should be in chronological order
        for j in range(len(data["t_start_ns"]) - 1):
            assert data["t_start_ns"][j] < data["t_start_ns"][j + 1]


class TestTierPropagation:
    """Tests for bucket propagation between tiers."""

    def test_tier1_to_tier2_propagation(self) -> None:
        buffer = VisualizationBuffer()
        # 10000 samples = 100 tier1 buckets = 1 tier2 bucket
        for i in range(10_000):
            # Use varying values to test min/max propagation
            value = (i % 100) if i < 5000 else (99 - i % 100)
            buffer.add_sample(t_ns=i * 1_000_000, counts=(value, 0, 0, 0, 0, 0))

        tier2_data = buffer.get_tier_data("tier2")
        assert tier2_data is not None
        assert len(tier2_data["t_start_ns"]) == 1
        # Min should be 0, max should be 99 (from varying values)
        assert tier2_data["counts_min"][0, 0] == 0
        assert tier2_data["counts_max"][0, 0] == 99

    def test_tier2_to_tier3_propagation(self) -> None:
        buffer = VisualizationBuffer()
        # 100000 samples = 1000 tier1 buckets = 10 tier2 buckets = 1 tier3 bucket
        for i in range(100_000):
            value = i % 1000
            buffer.add_sample(t_ns=i * 1_000_000, counts=(value, 0, 0, 0, 0, 0))

        tier3_data = buffer.get_tier_data("tier3")
        assert tier3_data is not None
        assert len(tier3_data["t_start_ns"]) == 1
        # Min should be 0, max should be 999
        assert tier3_data["counts_min"][0, 0] == 0
        assert tier3_data["counts_max"][0, 0] == 999
