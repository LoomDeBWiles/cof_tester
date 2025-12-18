"""Async buffered file writer with rotation support.

The file writer provides non-blocking logging for high-frequency sensor data.
It uses a dedicated writer thread with buffered writes and periodic flushes
to ensure the acquisition pipeline is never blocked by I/O operations.

Section 16.3: Dedicated writer thread, buffered writes, 250ms flush interval.
Sustains 1000Hz logging with no dropped samples.
"""

import errno
import io
import os
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

from gsdv.errors import DiskFullError


class WriterState(Enum):
    """State of the file writer."""

    STOPPED = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class WriterStats:
    """Statistics for the file writer."""

    state: WriterState
    samples_written: int
    samples_dropped: int
    bytes_written: int
    flushes: int
    flush_latency_avg_ms: float
    queue_size: int
    queue_capacity: int

    @property
    def drop_ratio(self) -> float:
        """Fraction of samples dropped (0.0 to 1.0)."""
        total = self.samples_written + self.samples_dropped
        return self.samples_dropped / total if total > 0 else 0.0

    @property
    def queue_fill_ratio(self) -> float:
        """Fraction of queue that is filled (0.0 to 1.0)."""
        return self.queue_size / self.queue_capacity if self.queue_capacity > 0 else 0.0


# Type for sample formatter function
SampleFormatter = Callable[[Any], str]


def default_csv_formatter(sample: Any) -> str:
    """Default CSV formatter for samples.

    Args:
        sample: Tuple or object to format.

    Returns:
        CSV-formatted line without newline.
    """
    if isinstance(sample, tuple):
        return ",".join(str(v) for v in sample)
    return str(sample)


class AsyncFileWriter:
    """Asynchronous buffered file writer for high-frequency data logging.

    The writer maintains a dedicated thread that pulls samples from a queue
    and writes them to disk in batches. The flush interval ensures data is
    persisted regularly without blocking the acquisition thread.

    Thread model:
    - Producer threads: Call write() to enqueue samples (never blocks acquisition)
    - Writer thread: Dequeues samples, buffers, and flushes to disk

    The write() method is non-blocking. If the queue is full, samples are
    dropped and counted in statistics rather than blocking the caller.

    Example:
        >>> writer = AsyncFileWriter(Path("data.csv"))
        >>> writer.start()
        >>> for sample in acquire_samples():
        ...     writer.write(sample)  # Never blocks
        >>> writer.stop()
        >>> print(f"Wrote {writer.stats().samples_written} samples")
    """

    # Default configuration
    DEFAULT_QUEUE_CAPACITY = 10_000  # Samples in queue (~10s at 1000Hz)
    DEFAULT_BUFFER_SIZE = 8192  # Bytes in write buffer
    DEFAULT_FLUSH_INTERVAL_MS = 250  # Flush every 250ms

    def __init__(
        self,
        path: Path,
        queue_capacity: int = DEFAULT_QUEUE_CAPACITY,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        flush_interval_ms: int = DEFAULT_FLUSH_INTERVAL_MS,
        formatter: Optional[SampleFormatter] = None,
        header: Optional[str] = None,
        line_terminator: str = "\n",
    ) -> None:
        """Initialize the file writer.

        Args:
            path: Output file path.
            queue_capacity: Maximum samples in queue before dropping.
            buffer_size: Write buffer size in bytes.
            flush_interval_ms: Interval between flushes in milliseconds.
            formatter: Function to format samples as strings. Defaults to CSV.
            header: Optional header line to write at file start.
            line_terminator: String to append to each line (e.g. "\\n", "\\r\\n").
        """
        self._path = path
        self._queue_capacity = queue_capacity
        self._buffer_size = buffer_size
        self._flush_interval_s = flush_interval_ms / 1000.0
        self._formatter = formatter or default_csv_formatter
        self._header = header
        self._line_terminator = line_terminator

        # Queue for samples
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=queue_capacity)

        # State management
        self._state = WriterState.STOPPED
        self._state_lock = threading.Lock()

        # Writer thread
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Statistics
        self._samples_written = 0
        self._samples_dropped = 0
        self._bytes_written = 0
        self._flushes = 0
        self._flush_latencies: list[float] = []
        self._stats_lock = threading.Lock()

        # File handle (managed by writer thread)
        self._file: Optional[io.TextIOWrapper] = None

    @property
    def path(self) -> Path:
        """Output file path."""
        return self._path

    @property
    def state(self) -> WriterState:
        """Current writer state."""
        with self._state_lock:
            return self._state

    @property
    def is_running(self) -> bool:
        """Whether the writer is currently running."""
        return self.state == WriterState.RUNNING

    def start(self) -> None:
        """Start the writer thread.

        Opens the output file and starts the background writer thread.

        Raises:
            RuntimeError: If already running.
            OSError: If the file cannot be opened.
        """
        with self._state_lock:
            if self._state == WriterState.RUNNING:
                raise RuntimeError("Writer already running")
            self._state = WriterState.RUNNING

        # Reset state
        self._stop_event.clear()
        with self._stats_lock:
            self._samples_written = 0
            self._samples_dropped = 0
            self._bytes_written = 0
            self._flushes = 0
            self._flush_latencies.clear()

        # Clear any stale items from queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Start writer thread
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="AsyncFileWriter",
            daemon=True,
        )
        self._writer_thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the writer thread and flush remaining data.

        Args:
            timeout: Maximum seconds to wait for thread to finish.
        """
        with self._state_lock:
            if self._state != WriterState.RUNNING:
                return
            self._state = WriterState.STOPPING

        # Signal thread to stop
        self._stop_event.set()
        # Send sentinel to unblock queue.get()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        # Wait for writer thread
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=timeout)
            self._writer_thread = None

        with self._state_lock:
            self._state = WriterState.STOPPED

    def write(self, sample: tuple) -> bool:
        """Write a sample to the queue (non-blocking).

        If the queue is full, the sample is dropped and counted in statistics.

        Args:
            sample: Sample tuple to write. Format depends on formatter.

        Returns:
            True if sample was queued, False if dropped.
        """
        if not self.is_running:
            return False

        try:
            self._queue.put_nowait(sample)
            return True
        except queue.Full:
            with self._stats_lock:
                self._samples_dropped += 1
            return False

    def stats(self) -> WriterStats:
        """Get current writer statistics.

        Returns:
            WriterStats with write counts, drops, and queue state.
        """
        with self._stats_lock:
            avg_latency = (
                sum(self._flush_latencies) / len(self._flush_latencies)
                if self._flush_latencies
                else 0.0
            )
            return WriterStats(
                state=self.state,
                samples_written=self._samples_written,
                samples_dropped=self._samples_dropped,
                bytes_written=self._bytes_written,
                flushes=self._flushes,
                flush_latency_avg_ms=avg_latency,
                queue_size=self._queue.qsize(),
                queue_capacity=self._queue_capacity,
            )

    def _writer_loop(self) -> None:
        """Main writer loop running in dedicated thread."""
        try:
            self._file = open(
                self._path, "w", buffering=self._buffer_size, newline=""
            )

            # Write header if provided
            if self._header:
                self._file.write(self._header)
                if not self._header.endswith("\n"):
                    self._file.write("\n")

            buffer: list[str] = []
            last_flush = time.monotonic()

            while not self._stop_event.is_set():
                # Calculate timeout to ensure regular flushes
                now = time.monotonic()
                elapsed = now - last_flush
                timeout = max(0.001, self._flush_interval_s - elapsed)

                try:
                    sample = self._queue.get(timeout=timeout)
                    if sample is None:
                        # Sentinel received, exit loop
                        break
                    line = self._formatter(sample) + "\n"
                    buffer.append(line)
                except queue.Empty:
                    pass

                # Flush if interval elapsed or buffer is large
                now = time.monotonic()
                if now - last_flush >= self._flush_interval_s or len(buffer) >= 1000:
                    if buffer:
                        self._flush_buffer(buffer)
                        buffer = []
                    last_flush = now

            # Final flush
            if buffer:
                self._flush_buffer(buffer)

            # Drain remaining queue items
            while True:
                try:
                    sample = self._queue.get_nowait()
                    if sample is not None:
                        line = self._formatter(sample) + "\n"
                        self._file.write(line)
                        with self._stats_lock:
                            self._samples_written += 1
                            self._bytes_written += len(line.encode("utf-8"))
                except queue.Empty:
                    break

            self._file.flush()
            os.fsync(self._file.fileno())

        except OSError as e:
            with self._state_lock:
                self._state = WriterState.ERROR
            
            if e.errno == errno.ENOSPC:
                raise DiskFullError(str(self._path)) from e
            raise
        finally:
            if self._file is not None:
                self._file.close()
                self._file = None

    def _flush_buffer(self, buffer: list[str]) -> None:
        """Flush buffer to file and update statistics."""
        if self._file is None:
            return

        start = time.perf_counter()
        data = "".join(buffer)
        self._file.write(data)
        self._file.flush()
        elapsed_ms = (time.perf_counter() - start) * 1000

        with self._stats_lock:
            self._samples_written += len(buffer)
            self._bytes_written += len(data.encode("utf-8"))
            self._flushes += 1
            self._flush_latencies.append(elapsed_ms)
            # Keep only last 100 latency samples
            if len(self._flush_latencies) > 100:
                self._flush_latencies.pop(0)

    def __enter__(self) -> "AsyncFileWriter":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.stop()
