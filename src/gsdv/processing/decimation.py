"""Decimation and multi-resolution tier management for plotting.

Implements a tiered visualization buffer that stores sensor data at multiple
resolutions to support time windows from 1 second to 7 days while keeping
memory usage under 10MB.

Tier structure:
- Raw: Full resolution ring buffer (60s at 1000Hz = 60,000 samples)
- Tier1: 1 hour at 10Hz = 36,000 samples, decimated 100:1 from raw
- Tier2: 24 hours at 0.1Hz = 8,640 samples, decimated 100:1 from Tier1
- Tier3: 7 days at 0.01Hz = 6,048 samples, decimated 10:1 from Tier2

Each tier stores min/max values per bucket to preserve signal extremes
for accurate visualization of peaks and troughs.
"""

import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from gsdv.acquisition.ring_buffer import RingBuffer


@dataclass(frozen=True, slots=True)
class TierConfig:
    """Configuration for a single tier."""

    name: str
    capacity: int
    decimation_factor: int
    sample_rate_hz: float


# Tier configurations per Section 16.2
RAW_TIER = TierConfig(name="raw", capacity=60_000, decimation_factor=1, sample_rate_hz=1000.0)
TIER1 = TierConfig(name="tier1", capacity=36_000, decimation_factor=100, sample_rate_hz=10.0)
TIER2 = TierConfig(name="tier2", capacity=8_640, decimation_factor=100, sample_rate_hz=0.1)
TIER3 = TierConfig(name="tier3", capacity=6_048, decimation_factor=10, sample_rate_hz=0.01)


@dataclass(frozen=True, slots=True)
class TierStats:
    """Statistics for a single tier."""

    name: str
    capacity: int
    size: int
    total_buckets_written: int

    @property
    def fill_ratio(self) -> float:
        """Fraction of tier that is filled (0.0 to 1.0)."""
        return self.size / self.capacity if self.capacity > 0 else 0.0


@dataclass(frozen=True, slots=True)
class VisualizationBufferStats:
    """Statistics for the entire visualization buffer."""

    tier_stats: tuple[TierStats, ...]
    memory_bytes: int

    @property
    def memory_mb(self) -> float:
        """Memory usage in megabytes."""
        return self.memory_bytes / (1024 * 1024)


class _TierBuffer:
    """Internal buffer for a single tier storing min/max aggregates.

    Each bucket stores:
    - t_start_ns: Start timestamp of the bucket
    - t_end_ns: End timestamp of the bucket
    - counts_min: Minimum counts [Fx, Fy, Fz, Tx, Ty, Tz] in bucket
    - counts_max: Maximum counts [Fx, Fy, Fz, Tx, Ty, Tz] in bucket
    - sample_count: Number of samples aggregated into this bucket
    """

    def __init__(self, config: TierConfig) -> None:
        self._config = config
        self._capacity = config.capacity
        self._decimation_factor = config.decimation_factor

        # Pre-allocate arrays
        self._t_start_ns = np.zeros(self._capacity, dtype=np.int64)
        self._t_end_ns = np.zeros(self._capacity, dtype=np.int64)
        self._counts_min = np.zeros((self._capacity, 6), dtype=np.int32)
        self._counts_max = np.zeros((self._capacity, 6), dtype=np.int32)
        self._sample_count = np.zeros(self._capacity, dtype=np.uint32)

        # Buffer state
        self._head = 0
        self._size = 0
        self._total_written = 0

        # Accumulator for building current bucket
        self._accum_count = 0
        self._accum_sample_count = 0
        self._accum_t_start: Optional[int] = None
        self._accum_t_end: Optional[int] = None
        self._accum_min: Optional[NDArray[np.int32]] = None
        self._accum_max: Optional[NDArray[np.int32]] = None
        self._scratch_counts = np.empty(6, dtype=np.int32)

    @property
    def config(self) -> TierConfig:
        """Tier configuration."""
        return self._config

    def add_sample(
        self,
        t_ns: int,
        counts: tuple[int, int, int, int, int, int] | NDArray[np.int32],
    ) -> Optional[tuple[int, int, NDArray[np.int32], NDArray[np.int32], int]]:
        """Add a sample to the accumulator.

        When decimation_factor samples have been accumulated, the bucket is
        finalized and added to the ring buffer.

        Args:
            t_ns: Timestamp in nanoseconds.
            counts: Raw counts [Fx, Fy, Fz, Tx, Ty, Tz].

        Returns:
            If a bucket was completed, returns (t_start_ns, t_end_ns, min, max, sample_count)
            for propagation to the next tier. Otherwise None.
        """
        if isinstance(counts, np.ndarray):
            counts_arr = counts
        else:
            self._scratch_counts[:] = counts
            counts_arr = self._scratch_counts

        if self._accum_count == 0:
            self._accum_t_start = t_ns
            self._accum_t_end = t_ns
            self._accum_min = counts_arr.copy()
            self._accum_max = counts_arr.copy()
            self._accum_sample_count = 1
        else:
            self._accum_t_end = t_ns
            np.minimum(self._accum_min, counts_arr, out=self._accum_min)
            np.maximum(self._accum_max, counts_arr, out=self._accum_max)
            self._accum_sample_count += 1

        self._accum_count += 1

        if self._accum_count >= self._decimation_factor:
            return self._finalize_bucket()

        return None

    def add_bucket(
        self,
        t_start_ns: int,
        t_end_ns: int,
        counts_min: NDArray[np.int32],
        counts_max: NDArray[np.int32],
        sample_count: int,
    ) -> Optional[tuple[int, int, NDArray[np.int32], NDArray[np.int32], int]]:
        """Add a bucket from the previous tier (for hierarchical propagation).

        Args:
            t_start_ns: Start timestamp of the bucket.
            t_end_ns: End timestamp of the bucket.
            counts_min: Minimum counts in the bucket.
            counts_max: Maximum counts in the bucket.
            sample_count: Number of original samples in the bucket.

        Returns:
            If decimation_factor buckets have been accumulated, returns the
            aggregated bucket for propagation. Otherwise None.
        """
        if self._accum_count == 0:
            self._accum_t_start = t_start_ns
            self._accum_t_end = t_end_ns
            self._accum_min = counts_min.copy()
            self._accum_max = counts_max.copy()
            self._accum_sample_count = sample_count
        else:
            self._accum_t_end = t_end_ns
            np.minimum(self._accum_min, counts_min, out=self._accum_min)
            np.maximum(self._accum_max, counts_max, out=self._accum_max)
            self._accum_sample_count += sample_count

        # Count buckets, not samples - each bucket from the previous tier counts as 1
        self._accum_count += 1

        if self._accum_count >= self._decimation_factor:
            return self._finalize_bucket()

        return None

    def _finalize_bucket(self) -> tuple[int, int, NDArray[np.int32], NDArray[np.int32], int]:
        """Finalize current accumulator into a stored bucket."""
        idx = self._head

        self._t_start_ns[idx] = self._accum_t_start
        self._t_end_ns[idx] = self._accum_t_end
        self._counts_min[idx, :] = self._accum_min
        self._counts_max[idx, :] = self._accum_max
        self._sample_count[idx] = self._accum_sample_count

        result = (
            self._accum_t_start,
            self._accum_t_end,
            self._accum_min.copy(),
            self._accum_max.copy(),
            self._accum_sample_count,
        )

        self._head = (self._head + 1) % self._capacity
        self._total_written += 1
        if self._size < self._capacity:
            self._size += 1

        # Reset accumulator
        self._accum_count = 0
        self._accum_sample_count = 0
        self._accum_t_start = None
        self._accum_t_end = None
        self._accum_min = None
        self._accum_max = None

        return result

    def stats(self) -> TierStats:
        """Get current tier statistics."""
        return TierStats(
            name=self._config.name,
            capacity=self._capacity,
            size=self._size,
            total_buckets_written=self._total_written,
        )

    def get_data(
        self,
        start_ns: Optional[int] = None,
        end_ns: Optional[int] = None,
    ) -> Optional[dict[str, NDArray]]:
        """Get bucket data within the time range.

        Args:
            start_ns: Start timestamp (inclusive). None means from beginning.
            end_ns: End timestamp (inclusive). None means to end.

        Returns:
            Dictionary with t_start_ns, t_end_ns, counts_min, counts_max, sample_count.
            Returns None if no data in range.
        """
        if self._size == 0:
            return None

        # Get all data in chronological order
        if self._size < self._capacity:
            indices = np.arange(self._size)
        else:
            start_idx = self._head
            if start_idx == 0:
                indices = np.arange(self._capacity)
            else:
                indices = np.concatenate([
                    np.arange(start_idx, self._capacity),
                    np.arange(0, start_idx),
                ])

        t_starts = self._t_start_ns[indices]
        t_ends = self._t_end_ns[indices]

        # Filter by time range
        mask = np.ones(len(indices), dtype=bool)
        if start_ns is not None:
            mask &= t_ends >= start_ns
        if end_ns is not None:
            mask &= t_starts <= end_ns

        if not np.any(mask):
            return None

        filtered_indices = indices[mask]

        return {
            "t_start_ns": self._t_start_ns[filtered_indices].copy(),
            "t_end_ns": self._t_end_ns[filtered_indices].copy(),
            "counts_min": self._counts_min[filtered_indices].copy(),
            "counts_max": self._counts_max[filtered_indices].copy(),
            "sample_count": self._sample_count[filtered_indices].copy(),
        }

    def memory_bytes(self) -> int:
        """Calculate memory usage of this tier in bytes."""
        return (
            self._t_start_ns.nbytes
            + self._t_end_ns.nbytes
            + self._counts_min.nbytes
            + self._counts_max.nbytes
            + self._sample_count.nbytes
        )

    def clear(self) -> None:
        """Clear all data from the tier."""
        self._head = 0
        self._size = 0
        self._total_written = 0
        self._accum_count = 0
        self._accum_sample_count = 0
        self._accum_t_start = None
        self._accum_t_end = None
        self._accum_min = None
        self._accum_max = None


class VisualizationBuffer:
    """Multi-resolution buffer for visualization with tiered downsampling.

    Manages multiple resolution tiers to support time windows from 1 second
    to 7 days while maintaining memory usage under 10MB.

    Tier structure:
    - Tier1: 1 hour at 10Hz, decimated 100:1 from raw (1000Hz)
    - Tier2: 24 hours at 0.1Hz, decimated 100:1 from Tier1
    - Tier3: 7 days at 0.01Hz, decimated 10:1 from Tier2

    Each tier stores min/max values per bucket to preserve signal extremes.

    Thread safety: All public methods are thread-safe.

    Example:
        >>> buffer = VisualizationBuffer()
        >>> buffer.add_sample(t_ns=1234567890, counts=(10, 20, 30, 40, 50, 60))
        >>> data = buffer.get_tier_data("tier1")
        >>> stats = buffer.stats()
        >>> print(f"Memory: {stats.memory_mb:.2f} MB")
    """

    def __init__(self) -> None:
        """Initialize the visualization buffer with all tiers."""
        self._lock = threading.Lock()

        self._tier1 = _TierBuffer(TIER1)
        self._tier2 = _TierBuffer(TIER2)
        self._tier3 = _TierBuffer(TIER3)

        self._tiers = {
            "tier1": self._tier1,
            "tier2": self._tier2,
            "tier3": self._tier3,
        }

    def add_sample(
        self,
        t_ns: int,
        counts: tuple[int, int, int, int, int, int] | NDArray[np.int32],
    ) -> None:
        """Add a raw sample and propagate through tiers.

        The sample is accumulated into Tier1. When Tier1 completes a bucket
        (100 samples), it propagates to Tier2, and so on.

        Args:
            t_ns: Timestamp in nanoseconds.
            counts: Raw counts [Fx, Fy, Fz, Tx, Ty, Tz].
        """
        with self._lock:
            # Add to Tier1 (decimates 100:1 from raw)
            result = self._tier1.add_sample(t_ns, counts)

            if result is not None:
                # Tier1 completed a bucket, propagate to Tier2
                t_start, t_end, mins, maxs, count = result
                result2 = self._tier2.add_bucket(t_start, t_end, mins, maxs, count)

                if result2 is not None:
                    # Tier2 completed a bucket, propagate to Tier3
                    t_start2, t_end2, mins2, maxs2, count2 = result2
                    self._tier3.add_bucket(t_start2, t_end2, mins2, maxs2, count2)

    def get_tier_data(
        self,
        tier_name: str,
        start_ns: Optional[int] = None,
        end_ns: Optional[int] = None,
    ) -> Optional[dict[str, NDArray]]:
        """Get data from a specific tier within a time range.

        Args:
            tier_name: One of "tier1", "tier2", "tier3".
            start_ns: Start timestamp (inclusive). None means from beginning.
            end_ns: End timestamp (inclusive). None means to end.

        Returns:
            Dictionary with t_start_ns, t_end_ns, counts_min, counts_max, sample_count.
            Returns None if tier is empty or no data in range.

        Raises:
            ValueError: If tier_name is invalid.
        """
        if tier_name not in self._tiers:
            raise ValueError(f"Invalid tier name: {tier_name}. Must be one of {list(self._tiers.keys())}")

        with self._lock:
            return self._tiers[tier_name].get_data(start_ns, end_ns)

    def select_tier_for_window(self, window_seconds: float) -> str:
        """Select the appropriate tier for a time window.

        Args:
            window_seconds: Time window duration in seconds.

        Returns:
            Tier name that provides the best resolution for the window.
        """
        # Use the highest resolution tier that covers the window
        # Tier capacities in seconds:
        # - tier1: 36000 samples / 10 Hz = 3600s = 1 hour
        # - tier2: 8640 samples / 0.1 Hz = 86400s = 24 hours
        # - tier3: 6048 samples / 0.01 Hz = 604800s = 7 days

        if window_seconds <= 3600:  # <= 1 hour
            return "tier1"
        elif window_seconds <= 86400:  # <= 24 hours
            return "tier2"
        else:
            return "tier3"

    def stats(self) -> VisualizationBufferStats:
        """Get current buffer statistics.

        Returns:
            VisualizationBufferStats with tier stats and memory usage.
        """
        with self._lock:
            tier_stats = tuple(tier.stats() for tier in self._tiers.values())
            memory = sum(tier.memory_bytes() for tier in self._tiers.values())
            return VisualizationBufferStats(tier_stats=tier_stats, memory_bytes=memory)

    def clear(self) -> None:
        """Clear all data from all tiers."""
        with self._lock:
            for tier in self._tiers.values():
                tier.clear()


@dataclass(frozen=True, slots=True)
class MultiResolutionBufferStats:
    """Statistics for a multi-resolution buffer including the raw ring."""

    tiers: VisualizationBufferStats
    raw_memory_bytes: int

    @property
    def memory_bytes(self) -> int:
        """Total memory usage in bytes (raw + tiers)."""
        return self.raw_memory_bytes + self.tiers.memory_bytes

    @property
    def memory_mb(self) -> float:
        """Total memory usage in megabytes (raw + tiers)."""
        return self.memory_bytes / (1024 * 1024)


class MultiResolutionBuffer:
    """Multi-resolution plot buffer: raw ring + tiered min/max downsampling.

    This is the concrete buffer described in Section 16.2:
    - Raw ring: 60s at 1000Hz (via RingBuffer)
    - Tier1: 1hr at 10Hz (100ms buckets)
    - Tier2: 24hr at 0.1Hz (10s buckets)
    - Tier3: 7d at 0.01Hz (100s buckets)
    """

    def __init__(
        self,
        *,
        raw_capacity: int = RAW_TIER.capacity,
        sample_rate_hz: float = RAW_TIER.sample_rate_hz,
    ) -> None:
        if raw_capacity <= 0:
            raise ValueError(f"raw_capacity must be positive, got {raw_capacity}")
        if sample_rate_hz <= 0:
            raise ValueError(f"sample_rate_hz must be positive, got {sample_rate_hz}")

        self._sample_rate_hz = sample_rate_hz
        self._raw = RingBuffer(capacity=raw_capacity)
        self._tiers = VisualizationBuffer()

    @property
    def raw(self) -> RingBuffer:
        """Access the raw ring buffer."""
        return self._raw

    @property
    def tiers(self) -> VisualizationBuffer:
        """Access the downsampled tier buffer."""
        return self._tiers

    @property
    def sample_rate_hz(self) -> float:
        """Raw sampling rate in Hz used for window calculations."""
        return self._sample_rate_hz

    def append(
        self,
        t_monotonic_ns: int,
        rdt_sequence: int,
        ft_sequence: int,
        status: int,
        counts: tuple[int, int, int, int, int, int],
    ) -> None:
        """Append a raw sample and propagate to tiers."""
        self._raw.append(
            t_monotonic_ns=t_monotonic_ns,
            rdt_sequence=rdt_sequence,
            ft_sequence=ft_sequence,
            status=status,
            counts=counts,
        )
        self._tiers.add_sample(t_ns=t_monotonic_ns, counts=counts)

    def clear(self) -> None:
        """Clear raw and tier buffers."""
        self._raw.clear()
        self._tiers.clear()

    def select_tier_for_window(self, window_seconds: float) -> str:
        """Select the best data source for the requested window.

        Returns:
            "raw" when the raw ring covers the requested window, otherwise a tier name
            from VisualizationBuffer ("tier1", "tier2", "tier3").
        """
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {window_seconds}")

        raw_duration_seconds = self._raw.capacity / self._sample_rate_hz
        if window_seconds <= raw_duration_seconds:
            return "raw"
        return self._tiers.select_tier_for_window(window_seconds)

    def get_window_data(self, window_seconds: float) -> Optional[dict[str, object]]:
        """Fetch data appropriate for plotting a given window.

        Returns a dict in one of two shapes:

        Raw:
            {"kind": "raw", "tier": "raw", ...RingBuffer.get_latest()...}

        Tier (min/max buckets):
            {
                "kind": "minmax",
                "tier": "tier1|tier2|tier3",
                "t_ref_ns": int,
                "t_start_ns": int64[],
                "t_end_ns": int64[],
                "counts_min": int32[:,6],
                "counts_max": int32[:,6],
                "sample_count": uint32[],
            }
        """
        tier = self.select_tier_for_window(window_seconds)

        if tier == "raw":
            n_samples = int(window_seconds * self._sample_rate_hz)
            raw = self._raw.get_latest(n_samples)
            if raw is None:
                return None
            return {
                "kind": "raw",
                "tier": "raw",
                **raw,
            }

        tier_data = self._tiers.get_tier_data(tier)
        if tier_data is None:
            # Fallback: if tiers haven't produced buckets yet, show whatever raw we have.
            raw = self._raw.get_all()
            if raw is None:
                return None
            return {
                "kind": "raw",
                "tier": "raw",
                **raw,
            }

        t_ref_ns = int(tier_data["t_end_ns"][-1])
        start_ns = t_ref_ns - int(window_seconds * 1e9)

        # Buckets are chronological; use t_end_ns for a fast start index.
        start_idx = int(np.searchsorted(tier_data["t_end_ns"], start_ns, side="left"))

        return {
            "kind": "minmax",
            "tier": tier,
            "t_ref_ns": t_ref_ns,
            "t_start_ns": tier_data["t_start_ns"][start_idx:],
            "t_end_ns": tier_data["t_end_ns"][start_idx:],
            "counts_min": tier_data["counts_min"][start_idx:],
            "counts_max": tier_data["counts_max"][start_idx:],
            "sample_count": tier_data["sample_count"][start_idx:],
        }

    def stats(self) -> MultiResolutionBufferStats:
        """Compute current buffer memory usage."""
        tiers_stats = self._tiers.stats()

        # RingBuffer storage layout (per sample):
        # - timestamps: int64 (8)
        # - rdt_sequence: uint32 (4)
        # - ft_sequence: uint32 (4)
        # - status: uint32 (4)
        # - counts: int32[6] (24)
        bytes_per_sample = 8 + 4 + 4 + 4 + 24
        raw_memory = self._raw.capacity * bytes_per_sample

        return MultiResolutionBufferStats(tiers=tiers_stats, raw_memory_bytes=raw_memory)
