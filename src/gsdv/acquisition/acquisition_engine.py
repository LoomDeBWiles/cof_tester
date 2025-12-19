"""Acquisition engine for receiving and buffering sensor data.

The acquisition engine manages the data pipeline from UDP sensor packets to
the ring buffer. It runs a dedicated receive thread that never blocks on
UI or I/O operations, ensuring sustained 1000Hz throughput.
"""

import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from gsdv.acquisition.ring_buffer import RingBuffer, RingBufferStats
from gsdv.models import SampleRecord
from gsdv.protocols.rdt_udp import RdtClient


class AcquisitionState(Enum):
    """State of the acquisition engine."""

    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class AcquisitionStats:
    """Statistics for the acquisition engine."""

    state: AcquisitionState
    buffer_stats: RingBufferStats
    packets_received: int
    packets_lost: int
    receive_errors: int
    samples_per_second: float

    @property
    def loss_ratio(self) -> float:
        """Fraction of packets lost (0.0 to 1.0)."""
        total = self.packets_received + self.packets_lost
        return self.packets_lost / total if total > 0 else 0.0


# Callback type for sample notifications
SampleCallback = Callable[[SampleRecord], None]


class AcquisitionEngine:
    """Engine for acquiring sensor data via UDP and buffering in a ring buffer.

    The engine manages:
    - A dedicated receive thread for UDP packets
    - A ring buffer for storing raw samples (default: 60s at 1000Hz)
    - Packet loss detection and statistics
    - Optional callbacks for new samples

    Thread model:
    - Receive thread: Reads UDP packets, parses them, writes to ring buffer
    - Main thread: Starts/stops acquisition, reads statistics, reads buffer

    The receive thread never blocks on UI or I/O. It writes directly to the
    pre-allocated ring buffer arrays.

    Example:
        >>> engine = AcquisitionEngine(ip="192.168.1.1")
        >>> engine.start()
        >>> # ... data streams into buffer ...
        >>> stats = engine.stats()
        >>> print(f"Received {stats.packets_received} packets")
        >>> data = engine.get_latest(1000)  # Last 1 second
        >>> engine.stop()
    """

    # Default buffer size: 60 seconds at 1000Hz
    DEFAULT_BUFFER_CAPACITY = 60_000

    def __init__(
        self,
        ip: str,
        port: int = 49152,
        buffer_capacity: int = DEFAULT_BUFFER_CAPACITY,
        receive_timeout: float = 0.1,
        decimation_factor: int = 1,
    ) -> None:
        """Initialize the acquisition engine.

        Args:
            ip: Sensor IP address.
            port: UDP port (default 49152).
            buffer_capacity: Ring buffer capacity in samples (default 60000).
            receive_timeout: Socket timeout in seconds for clean shutdown.
            decimation_factor: Only store every Nth sample (1=all, 10=100Hz from 1000Hz).
        """
        self._ip = ip
        self._port = port
        self._receive_timeout = receive_timeout
        self._decimation_factor = max(1, decimation_factor)
        self._decimation_counter = 0

        self._buffer = RingBuffer(capacity=buffer_capacity)
        self._client: Optional[RdtClient] = None

        # State management
        self._state = AcquisitionState.STOPPED
        self._state_lock = threading.Lock()

        # Receive thread
        self._receive_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Statistics
        self._packets_received = 0
        self._packets_lost = 0
        self._receive_errors = 0
        self._rate_samples: list[tuple[float, int]] = []
        self._stats_lock = threading.Lock()

        # Optional sample callback
        self._sample_callback: Optional[SampleCallback] = None
        self._callback_queue: queue.Queue[SampleRecord] = queue.Queue(maxsize=1000)
        self._callback_thread: Optional[threading.Thread] = None

    @property
    def ip(self) -> str:
        """Sensor IP address."""
        return self._ip

    @property
    def port(self) -> int:
        """UDP port."""
        return self._port

    @property
    def state(self) -> AcquisitionState:
        """Current acquisition state."""
        with self._state_lock:
            return self._state

    @property
    def is_running(self) -> bool:
        """Whether acquisition is currently running."""
        return self.state == AcquisitionState.RUNNING

    @property
    def buffer(self) -> RingBuffer:
        """Direct access to the ring buffer."""
        return self._buffer

    def set_sample_callback(self, callback: Optional[SampleCallback]) -> None:
        """Set a callback to be invoked for each received sample.

        The callback runs in a separate thread to avoid blocking the receive
        thread. If the callback queue fills up, samples are dropped.

        Args:
            callback: Function to call with each SampleRecord, or None to disable.
        """
        self._sample_callback = callback

    def start(self) -> None:
        """Start data acquisition.

        Starts the UDP client and receive thread. Non-blocking.

        Raises:
            RuntimeError: If already running or in an error state.
        """
        with self._state_lock:
            if self._state == AcquisitionState.RUNNING:
                raise RuntimeError("Acquisition already running")
            if self._state == AcquisitionState.ERROR:
                raise RuntimeError("Engine in error state, call reset() first")
            self._state = AcquisitionState.STARTING

        # Reset state
        self._stop_event.clear()
        with self._stats_lock:
            self._packets_received = 0
            self._packets_lost = 0
            self._receive_errors = 0
            self._rate_samples.clear()
        self._buffer.clear()

        # Create and start client
        self._client = RdtClient(self._ip, self._port)
        self._client.start_streaming()

        # Start receive thread
        self._receive_thread = threading.Thread(
            target=self._receive_loop,
            name="AcquisitionReceive",
            daemon=True,
        )
        self._receive_thread.start()

        # Start callback thread if callback is set
        if self._sample_callback is not None:
            self._callback_thread = threading.Thread(
                target=self._callback_loop,
                name="AcquisitionCallback",
                daemon=True,
            )
            self._callback_thread.start()

        with self._state_lock:
            self._state = AcquisitionState.RUNNING

    def stop(self) -> None:
        """Stop data acquisition.

        Signals the receive thread to stop and waits for clean shutdown.
        """
        with self._state_lock:
            if self._state != AcquisitionState.RUNNING:
                return
            self._state = AcquisitionState.STOPPING

        # Signal thread to stop
        self._stop_event.set()

        # Wait for receive thread
        if self._receive_thread is not None:
            self._receive_thread.join(timeout=2.0)
            self._receive_thread = None

        # Stop callback thread
        if self._callback_thread is not None:
            self._callback_thread.join(timeout=1.0)
            self._callback_thread = None

        # Stop client
        if self._client is not None:
            self._client.stop_streaming()
            self._client.close()
            self._client = None

        with self._state_lock:
            self._state = AcquisitionState.STOPPED

    def reset(self) -> None:
        """Reset the engine from an error state."""
        with self._state_lock:
            if self._state == AcquisitionState.RUNNING:
                raise RuntimeError("Cannot reset while running")
            self._state = AcquisitionState.STOPPED

        # Clean up any lingering resources
        if self._client is not None:
            self._client.close()
            self._client = None

    def stats(self) -> AcquisitionStats:
        """Get current acquisition statistics.

        Returns:
            AcquisitionStats with state, buffer stats, and packet statistics.
        """
        with self._stats_lock:
            return AcquisitionStats(
                state=self.state,
                buffer_stats=self._buffer.stats(),
                packets_received=self._packets_received,
                packets_lost=self._packets_lost,
                receive_errors=self._receive_errors,
                samples_per_second=self._calculate_rate(),
            )

    def get_latest(self, n: int) -> Optional[dict]:
        """Get the n most recent samples from the buffer.

        Args:
            n: Number of samples to retrieve.

        Returns:
            Dictionary with arrays for timestamps, rdt_sequence, ft_sequence,
            status, and counts. Returns None if buffer is empty.
        """
        return self._buffer.get_latest(n)

    def _receive_loop(self) -> None:
        """Main receive loop running in dedicated thread."""
        if self._client is None:
            return

        while not self._stop_event.is_set():
            try:
                for sample in self._client.receive_samples(
                    timeout=self._receive_timeout,
                    max_samples=100,  # Process in batches for efficiency
                ):
                    if self._stop_event.is_set():
                        break

                    # Update statistics for all received packets
                    with self._stats_lock:
                        self._packets_received += 1
                        self._update_rate()

                    # Apply decimation - only process every Nth sample
                    self._decimation_counter += 1
                    if self._decimation_counter < self._decimation_factor:
                        continue
                    self._decimation_counter = 0

                    # Write to ring buffer (never blocks)
                    self._buffer.append(
                        t_monotonic_ns=sample.t_monotonic_ns,
                        rdt_sequence=sample.rdt_sequence,
                        ft_sequence=sample.ft_sequence,
                        status=sample.status,
                        counts=sample.counts,
                    )

                    # Queue for callback (non-blocking)
                    if self._sample_callback is not None:
                        try:
                            self._callback_queue.put_nowait(sample)
                        except queue.Full:
                            pass  # Drop sample rather than block

                # Update packet loss from client statistics
                client_stats = self._client.statistics
                with self._stats_lock:
                    self._packets_lost = client_stats.packets_lost

            except OSError:
                with self._stats_lock:
                    self._receive_errors += 1
                # Brief pause before retry on error
                if not self._stop_event.is_set():
                    time.sleep(0.01)

    def _callback_loop(self) -> None:
        """Callback dispatch loop running in dedicated thread."""
        while not self._stop_event.is_set():
            try:
                sample = self._callback_queue.get(timeout=0.1)
                if self._sample_callback is not None:
                    self._sample_callback(sample)
            except queue.Empty:
                continue

    def _update_rate(self) -> None:
        """Update sample rate tracking (called with stats_lock held)."""
        now = time.monotonic()
        self._rate_samples.append((now, self._packets_received))

        # Keep only last 2 seconds of samples
        cutoff = now - 2.0
        while self._rate_samples and self._rate_samples[0][0] < cutoff:
            self._rate_samples.pop(0)

    def _calculate_rate(self) -> float:
        """Calculate current sample rate (called with stats_lock held)."""
        if len(self._rate_samples) < 2:
            return 0.0

        oldest_time, oldest_count = self._rate_samples[0]
        newest_time, newest_count = self._rate_samples[-1]

        elapsed = newest_time - oldest_time
        if elapsed <= 0:
            return 0.0

        return (newest_count - oldest_count) / elapsed

    def __enter__(self) -> "AcquisitionEngine":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.stop()
