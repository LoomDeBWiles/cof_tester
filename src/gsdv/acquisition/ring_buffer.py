"""Ring buffer implementation for streaming data.

Provides a fixed-size circular buffer that overwrites oldest data when full.
Optimized for storing sensor sample data at high rates (1000Hz) with minimal
allocation overhead.
"""

import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class RingBufferStats:
    """Statistics for ring buffer state."""

    capacity: int
    size: int
    total_written: int
    overwrites: int

    @property
    def fill_ratio(self) -> float:
        """Fraction of buffer that is filled (0.0 to 1.0)."""
        return self.size / self.capacity if self.capacity > 0 else 0.0

    @property
    def is_full(self) -> bool:
        """Whether the buffer has reached capacity."""
        return self.size >= self.capacity


class RingBuffer:
    """Thread-safe ring buffer for sensor sample data.

    Stores raw sample data in a fixed-size circular buffer. When full, oldest
    data is overwritten. Designed for high-throughput streaming at 1000Hz.

    The buffer stores:
    - timestamps: int64 monotonic nanoseconds
    - rdt_sequence: uint32 packet sequence numbers
    - ft_sequence: uint32 sensor sample sequence numbers
    - status: uint32 sensor status codes
    - counts: int32 array of shape (capacity, 6) for [Fx, Fy, Fz, Tx, Ty, Tz]

    Thread safety: All public methods are thread-safe. The buffer uses a single
    lock for simplicity and correctness over maximum throughput.

    Example:
        >>> buffer = RingBuffer(capacity=60000)  # 60s at 1000Hz
        >>> buffer.append(
        ...     t_monotonic_ns=1234567890,
        ...     rdt_sequence=1,
        ...     ft_sequence=100,
        ...     status=0,
        ...     counts=(10, 20, 30, 40, 50, 60),
        ... )
        >>> stats = buffer.stats()
        >>> print(f"Buffer {stats.fill_ratio:.1%} full")
    """

    def __init__(self, capacity: int) -> None:
        """Initialize ring buffer with given capacity.

        Args:
            capacity: Maximum number of samples the buffer can hold.

        Raises:
            ValueError: If capacity is not positive.
        """
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")

        self._capacity = capacity
        self._lock = threading.Lock()

        # Pre-allocate arrays
        self._timestamps = np.zeros(capacity, dtype=np.int64)
        self._rdt_sequence = np.zeros(capacity, dtype=np.uint32)
        self._ft_sequence = np.zeros(capacity, dtype=np.uint32)
        self._status = np.zeros(capacity, dtype=np.uint32)
        self._counts = np.zeros((capacity, 6), dtype=np.int32)

        # Buffer state
        self._head = 0  # Next write position
        self._size = 0  # Current number of valid entries
        self._total_written = 0  # Total samples ever written
        self._overwrites = 0  # Number of samples overwritten

    @property
    def capacity(self) -> int:
        """Maximum number of samples the buffer can hold."""
        return self._capacity

    def append(
        self,
        t_monotonic_ns: int,
        rdt_sequence: int,
        ft_sequence: int,
        status: int,
        counts: tuple[int, int, int, int, int, int],
    ) -> None:
        """Append a sample to the buffer.

        If the buffer is full, the oldest sample is overwritten.

        Args:
            t_monotonic_ns: Monotonic timestamp in nanoseconds.
            rdt_sequence: RDT packet sequence number.
            ft_sequence: Sensor sample sequence number.
            status: Sensor status code.
            counts: Raw force/torque counts [Fx, Fy, Fz, Tx, Ty, Tz].
        """
        with self._lock:
            idx = self._head

            self._timestamps[idx] = t_monotonic_ns
            self._rdt_sequence[idx] = rdt_sequence
            self._ft_sequence[idx] = ft_sequence
            self._status[idx] = status
            self._counts[idx, :] = counts

            self._head = (self._head + 1) % self._capacity
            self._total_written += 1

            if self._size < self._capacity:
                self._size += 1
            else:
                self._overwrites += 1

    def stats(self) -> RingBufferStats:
        """Get current buffer statistics.

        Returns:
            RingBufferStats with capacity, size, total_written, overwrites.
        """
        with self._lock:
            return RingBufferStats(
                capacity=self._capacity,
                size=self._size,
                total_written=self._total_written,
                overwrites=self._overwrites,
            )

    def get_latest(self, n: int) -> Optional[dict[str, NDArray]]:
        """Get the n most recent samples.

        Args:
            n: Number of samples to retrieve (clamped to available size).

        Returns:
            Dictionary with arrays for timestamps, rdt_sequence, ft_sequence,
            status, and counts. Returns None if buffer is empty.
            Arrays are copies, safe to modify.
        """
        with self._lock:
            return self._get_latest_unlocked(n)

    def get_all(self) -> Optional[dict[str, NDArray]]:
        """Get all samples in chronological order.

        Returns:
            Dictionary with arrays for all fields. Returns None if buffer is empty.
            Arrays are copies, safe to modify.
        """
        with self._lock:
            return self._get_latest_unlocked(self._size)

    def _get_latest_unlocked(self, n: int) -> Optional[dict[str, NDArray]]:
        """Internal get_latest without locking (caller must hold lock)."""
        if self._size == 0:
            return None

        n = min(n, self._size)

        # Calculate indices for most recent n samples
        if self._size < self._capacity:
            # Buffer not yet full, data starts at 0
            start = self._size - n
            indices = np.arange(start, self._size)
        else:
            # Buffer full, calculate wrapped indices
            # Head points to next write position = oldest data
            # Most recent is at head - 1
            end = self._head
            start = (end - n) % self._capacity
            if start < end:
                indices = np.arange(start, end)
            else:
                indices = np.concatenate([
                    np.arange(start, self._capacity),
                    np.arange(0, end),
                ])

        return {
            "timestamps": self._timestamps[indices].copy(),
            "rdt_sequence": self._rdt_sequence[indices].copy(),
            "ft_sequence": self._ft_sequence[indices].copy(),
            "status": self._status[indices].copy(),
            "counts": self._counts[indices].copy(),
        }

    def clear(self) -> None:
        """Clear all data from the buffer.

        Statistics counters (total_written, overwrites) are reset.
        """
        with self._lock:
            self._head = 0
            self._size = 0
            self._total_written = 0
            self._overwrites = 0
            # Arrays are not zeroed for performance; size tracks validity
