"""Processing engine for data conversion and filtering.

Implements Section 11.1.5: Convert counts to engineering units via cpf/cpt,
apply soft zero offsets, and route processed samples to visualization and logging.
"""

import queue
import threading
from dataclasses import dataclass, replace
from typing import Callable, Optional

import numpy as np

from gsdv.models import CalibrationInfo, SampleRecord
from gsdv.processing.filters import FilterPipeline, MAX_CUTOFF_HZ


@dataclass(frozen=True, slots=True)
class SoftZeroOffsets:
    """Soft zero offsets for application-level biasing.

    When applied, these offsets are subtracted from raw counts before
    conversion to engineering units. This provides a software-based
    zeroing when device tare is unavailable or fails.

    Attributes:
        force_counts: Offset counts for [Fx, Fy, Fz].
        torque_counts: Offset counts for [Tx, Ty, Tz].
    """

    force_counts: tuple[int, int, int]
    torque_counts: tuple[int, int, int]

    def __post_init__(self) -> None:
        if len(self.force_counts) != 3:
            raise ValueError(f"force_counts must have 3 elements, got {len(self.force_counts)}")
        if len(self.torque_counts) != 3:
            raise ValueError(f"torque_counts must have 3 elements, got {len(self.torque_counts)}")

    @classmethod
    def from_sample(cls, sample: SampleRecord) -> "SoftZeroOffsets":
        """Create soft zero offsets from a sample's current counts.

        Args:
            sample: Sample whose counts will be used as zero offsets.

        Returns:
            SoftZeroOffsets capturing the sample's force and torque counts.
        """
        return cls(
            force_counts=(sample.counts[0], sample.counts[1], sample.counts[2]),
            torque_counts=(sample.counts[3], sample.counts[4], sample.counts[5]),
        )

    @classmethod
    def zero(cls) -> "SoftZeroOffsets":
        """Create zero offsets (no adjustment)."""
        return cls(force_counts=(0, 0, 0), torque_counts=(0, 0, 0))


# Callback type for processed samples
ProcessedSampleCallback = Callable[[SampleRecord], None]


class ProcessingEngine:
    """Engine for converting raw sensor data to engineering units.

    The processing engine sits between the acquisition engine and downstream
    consumers (visualization buffer, logger). It performs:

    1. Soft zero offset subtraction (optional, per BL-3)
    2. Counts to engineering units conversion (BL-1)
    3. Optional low-pass filtering (BL-4)
    4. Routing to visualization and logger queues

    Thread model:
    - Processing runs in a dedicated thread to avoid blocking acquisition
    - Downstream consumers receive samples via callbacks or queues
    - All public methods are thread-safe

    Example:
        >>> calibration = CalibrationInfo(counts_per_force=1000000.0, counts_per_torque=1000000.0)
        >>> engine = ProcessingEngine(calibration)
        >>> engine.set_visualization_callback(lambda s: plot_update(s))
        >>> engine.start()
        >>> # Feed samples from acquisition
        >>> engine.process_sample(sample)
        >>> # Or use the queue interface
        >>> engine.input_queue.put(sample)
    """

    def __init__(
        self,
        calibration: CalibrationInfo,
        sample_rate_hz: float = 1000.0,
        filter_enabled: bool = False,
        filter_cutoff_hz: float = MAX_CUTOFF_HZ,
        input_queue_size: int = 1000,
        output_queue_size: int = 1000,
    ) -> None:
        """Initialize the processing engine.

        Args:
            calibration: Calibration data with cpf/cpt values.
            sample_rate_hz: Input sample rate in Hz (used for digital filtering).
            filter_enabled: Whether the low-pass filter is enabled.
            filter_cutoff_hz: Low-pass cutoff frequency in Hz.
            input_queue_size: Max size of input queue (samples dropped if full).
            output_queue_size: Max size of logger output queue.
        """
        self._calibration = calibration
        self._soft_zero: Optional[SoftZeroOffsets] = None
        self._soft_zero_lock = threading.Lock()

        # Optional filtering (BL-4)
        self._filter_lock = threading.Lock()
        self._filter_pipeline = FilterPipeline(
            enabled=filter_enabled,
            cutoff_hz=filter_cutoff_hz,
            sample_rate_hz=sample_rate_hz,
            num_channels=6,
        )

        # Input queue for samples from acquisition engine
        self._input_queue: queue.Queue[SampleRecord] = queue.Queue(maxsize=input_queue_size)

        # Output queue for logger (async file writer)
        self._logger_queue: queue.Queue[SampleRecord] = queue.Queue(maxsize=output_queue_size)

        # Callbacks for visualization (synchronous, fast)
        self._visualization_callback: Optional[ProcessedSampleCallback] = None
        self._callback_lock = threading.Lock()

        # Processing thread
        self._processing_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._running_lock = threading.Lock()

        # Statistics
        self._samples_processed = 0
        self._samples_dropped_input = 0
        self._samples_dropped_logger = 0
        self._stats_lock = threading.Lock()

    @property
    def calibration(self) -> CalibrationInfo:
        """Current calibration data."""
        return self._calibration

    @property
    def input_queue(self) -> queue.Queue[SampleRecord]:
        """Queue for feeding raw samples into the engine."""
        return self._input_queue

    @property
    def logger_queue(self) -> queue.Queue[SampleRecord]:
        """Queue for processed samples destined for the logger."""
        return self._logger_queue

    @property
    def is_running(self) -> bool:
        """Whether the processing thread is running."""
        with self._running_lock:
            return self._running

    @property
    def soft_zero(self) -> Optional[SoftZeroOffsets]:
        """Current soft zero offsets, or None if not set."""
        with self._soft_zero_lock:
            return self._soft_zero

    @property
    def filter_enabled(self) -> bool:
        """Whether the low-pass filter is enabled."""
        with self._filter_lock:
            return self._filter_pipeline.enabled

    @property
    def filter_cutoff_hz(self) -> float:
        """Current low-pass cutoff frequency in Hz."""
        with self._filter_lock:
            return self._filter_pipeline.cutoff_hz

    def set_calibration(self, calibration: CalibrationInfo) -> None:
        """Update calibration data.

        Thread-safe. Takes effect for the next sample processed.

        Args:
            calibration: New calibration data.
        """
        self._calibration = calibration

    def set_soft_zero(self, offsets: Optional[SoftZeroOffsets]) -> None:
        """Set or clear soft zero offsets.

        Args:
            offsets: Offsets to apply, or None to disable soft zero.
        """
        with self._soft_zero_lock:
            self._soft_zero = offsets

    def set_filter_enabled(self, enabled: bool) -> None:
        """Enable or disable the low-pass filter (BL-4).

        When enabling, the filter is primed on the next sample to avoid
        a startup transient.
        """
        with self._filter_lock:
            self._filter_pipeline.enabled = enabled

    def set_filter_cutoff_hz(self, cutoff_hz: float) -> None:
        """Set the low-pass filter cutoff frequency in Hz (FR-26)."""
        with self._filter_lock:
            self._filter_pipeline.cutoff_hz = cutoff_hz

    def set_sample_rate_hz(self, sample_rate_hz: float) -> None:
        """Set the sample rate used for filter coefficient calculation."""
        with self._filter_lock:
            self._filter_pipeline.sample_rate_hz = sample_rate_hz

    def reset_filter(self) -> None:
        """Reset filter state (use when starting a new stream)."""
        with self._filter_lock:
            self._filter_pipeline.reset()

    def capture_soft_zero(self, sample: SampleRecord) -> SoftZeroOffsets:
        """Capture current counts as soft zero offsets.

        Convenience method that creates offsets from a sample and applies them.

        Args:
            sample: Sample whose counts become the zero reference.

        Returns:
            The captured SoftZeroOffsets.
        """
        offsets = SoftZeroOffsets.from_sample(sample)
        self.set_soft_zero(offsets)
        return offsets

    def clear_soft_zero(self) -> None:
        """Clear soft zero offsets."""
        self.set_soft_zero(None)

    def set_visualization_callback(self, callback: Optional[ProcessedSampleCallback]) -> None:
        """Set callback for visualization updates.

        The callback is invoked synchronously in the processing thread for
        each processed sample. It should be fast to avoid backing up the
        processing pipeline.

        Args:
            callback: Function to call with each processed sample, or None to disable.
        """
        with self._callback_lock:
            self._visualization_callback = callback

    def start(self) -> None:
        """Start the processing thread.

        Raises:
            RuntimeError: If already running.
        """
        with self._running_lock:
            if self._running:
                raise RuntimeError("Processing engine already running")
            self._running = True

        # New stream: reset filter state so the first sample is bumpless.
        self.reset_filter()

        self._stop_event.clear()
        self._processing_thread = threading.Thread(
            target=self._processing_loop,
            name="ProcessingEngine",
            daemon=True,
        )
        self._processing_thread.start()

    def stop(self) -> None:
        """Stop the processing thread."""
        with self._running_lock:
            if not self._running:
                return
            self._running = False

        self._stop_event.set()
        if self._processing_thread is not None:
            self._processing_thread.join(timeout=2.0)
            self._processing_thread = None

    def process_sample(self, sample: SampleRecord) -> SampleRecord:
        """Process a single sample synchronously.

        Applies soft zero offsets, converts to engineering units, and applies
        optional low-pass filtering.
        Does not route to queues or callbacks.

        Args:
            sample: Raw sample from acquisition.

        Returns:
            Processed sample with force_N and torque_Nm populated.
        """
        counts = sample.counts

        # Apply soft zero offsets if set
        with self._soft_zero_lock:
            offsets = self._soft_zero

        if offsets is not None:
            adjusted_counts = (
                counts[0] - offsets.force_counts[0],
                counts[1] - offsets.force_counts[1],
                counts[2] - offsets.force_counts[2],
                counts[3] - offsets.torque_counts[0],
                counts[4] - offsets.torque_counts[1],
                counts[5] - offsets.torque_counts[2],
            )
        else:
            adjusted_counts = counts

        # Convert to engineering units using calibration (BL-1)
        force_N, torque_Nm = self._calibration.convert_counts_to_si(adjusted_counts)

        values = np.empty(6, dtype=np.float64)
        values[:3] = force_N
        values[3:] = torque_Nm

        with self._filter_lock:
            filtered = self._filter_pipeline.apply(values)

        # Create new sample with converted values
        return replace(
            sample,
            counts=adjusted_counts,
            force_N=(float(filtered[0]), float(filtered[1]), float(filtered[2])),
            torque_Nm=(float(filtered[3]), float(filtered[4]), float(filtered[5])),
        )

    def submit_sample(self, sample: SampleRecord) -> bool:
        """Submit a sample for asynchronous processing.

        Non-blocking. If the input queue is full, the sample is dropped.

        Args:
            sample: Raw sample from acquisition.

        Returns:
            True if sample was queued, False if dropped.
        """
        try:
            self._input_queue.put_nowait(sample)
            return True
        except queue.Full:
            with self._stats_lock:
                self._samples_dropped_input += 1
            return False

    def statistics(self) -> dict[str, int]:
        """Get processing statistics.

        Returns:
            Dictionary with samples_processed, samples_dropped_input,
            samples_dropped_logger counts.
        """
        with self._stats_lock:
            return {
                "samples_processed": self._samples_processed,
                "samples_dropped_input": self._samples_dropped_input,
                "samples_dropped_logger": self._samples_dropped_logger,
            }

    def _processing_loop(self) -> None:
        """Main processing loop running in dedicated thread."""
        while not self._stop_event.is_set():
            try:
                sample = self._input_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Process the sample
            processed = self.process_sample(sample)

            with self._stats_lock:
                self._samples_processed += 1

            # Route to visualization callback
            with self._callback_lock:
                callback = self._visualization_callback
            if callback is not None:
                callback(processed)

            # Route to logger queue (non-blocking)
            try:
                self._logger_queue.put_nowait(processed)
            except queue.Full:
                with self._stats_lock:
                    self._samples_dropped_logger += 1

    def __enter__(self) -> "ProcessingEngine":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.stop()
