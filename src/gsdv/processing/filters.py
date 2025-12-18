"""Digital filtering implementations (IIR low-pass).

Implements BL-4 from the specification: Optional 2nd-order Butterworth IIR low-pass
filter with configurable cutoff frequency (0.7-120 Hz), stable for streaming.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray


# Cutoff frequency bounds (Hz) per Section 14.4 and BL-4
MIN_CUTOFF_HZ: Final[float] = 0.7
MAX_CUTOFF_HZ: Final[float] = 120.0


@dataclass(frozen=True, slots=True)
class ButterworthCoefficients:
    """Coefficients for a 2nd-order Butterworth IIR low-pass filter.

    The filter is implemented in Direct Form II Transposed for numerical stability:
        y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]

    Normalized so that a0 = 1.
    """

    b0: float
    b1: float
    b2: float
    a1: float
    a2: float


def compute_butterworth_coefficients(
    cutoff_hz: float, sample_rate_hz: float
) -> ButterworthCoefficients:
    """Compute 2nd-order Butterworth low-pass filter coefficients.

    Uses the bilinear transform with frequency prewarping to convert the analog
    Butterworth prototype to a digital filter.

    Args:
        cutoff_hz: Cutoff frequency in Hz. Must be in [MIN_CUTOFF_HZ, MAX_CUTOFF_HZ].
        sample_rate_hz: Sample rate in Hz. Must be positive and > 2*cutoff_hz (Nyquist).

    Returns:
        ButterworthCoefficients with normalized coefficients (a0=1).

    Raises:
        ValueError: If cutoff_hz is out of range or sample_rate_hz is invalid.
    """
    if not MIN_CUTOFF_HZ <= cutoff_hz <= MAX_CUTOFF_HZ:
        raise ValueError(
            f"cutoff_hz must be in [{MIN_CUTOFF_HZ}, {MAX_CUTOFF_HZ}], got {cutoff_hz}"
        )
    if sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz must be positive, got {sample_rate_hz}")
    if cutoff_hz >= sample_rate_hz / 2:
        raise ValueError(
            f"cutoff_hz ({cutoff_hz}) must be less than Nyquist frequency "
            f"({sample_rate_hz / 2})"
        )

    # Prewarp the cutoff frequency for bilinear transform
    omega_c = 2 * math.pi * cutoff_hz
    omega_c_prewarped = 2 * sample_rate_hz * math.tan(omega_c / (2 * sample_rate_hz))

    # 2nd-order Butterworth analog prototype has poles at s = omega_c * e^(±j*3*pi/4)
    # Transfer function: H(s) = omega_c^2 / (s^2 + sqrt(2)*omega_c*s + omega_c^2)
    sqrt2 = math.sqrt(2)

    # Bilinear transform: s = 2*fs * (z-1)/(z+1)
    # After substitution and simplification:
    k = omega_c_prewarped / sample_rate_hz
    k2 = k * k
    sqrt2_k = sqrt2 * k
    denom = 4 + 2 * sqrt2_k + k2

    # Normalized coefficients (a0 = 1)
    b0 = k2 / denom
    b1 = 2 * k2 / denom
    b2 = k2 / denom
    a1 = (2 * k2 - 8) / denom
    a2 = (4 - 2 * sqrt2_k + k2) / denom

    return ButterworthCoefficients(b0=b0, b1=b1, b2=b2, a1=a1, a2=a2)


class LowPassFilter:
    """2nd-order Butterworth IIR low-pass filter for streaming data.

    Maintains internal state to process samples one at a time or in batches.
    Supports multiple channels (e.g., 6 F/T channels) processed independently.

    The filter is implemented using Direct Form II Transposed structure,
    which has better numerical properties than Direct Form I.

    Example:
        # Create filter for 6 channels at 1000 Hz with 10 Hz cutoff
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=6)

        # Process samples one at a time
        for sample in samples:
            filtered = lpf.process_sample(sample)

        # Or process a batch
        filtered_batch = lpf.process_batch(sample_array)

        # Reset state for new stream
        lpf.reset()
    """

    def __init__(
        self, cutoff_hz: float, sample_rate_hz: float, num_channels: int = 6
    ) -> None:
        """Initialize the low-pass filter.

        Args:
            cutoff_hz: Cutoff frequency in Hz (0.7-120).
            sample_rate_hz: Sample rate in Hz.
            num_channels: Number of independent channels to filter (default 6 for F/T).

        Raises:
            ValueError: If parameters are invalid.
        """
        if num_channels <= 0:
            raise ValueError(f"num_channels must be positive, got {num_channels}")

        self._coeffs = compute_butterworth_coefficients(cutoff_hz, sample_rate_hz)
        self._cutoff_hz = cutoff_hz
        self._sample_rate_hz = sample_rate_hz
        self._num_channels = num_channels

        # State for Direct Form II Transposed: two delay elements per channel
        # z1 holds state from n-1, z2 holds state from n-2
        self._z1: NDArray[np.float64] = np.zeros(num_channels, dtype=np.float64)
        self._z2: NDArray[np.float64] = np.zeros(num_channels, dtype=np.float64)

    @property
    def cutoff_hz(self) -> float:
        """Return the cutoff frequency in Hz."""
        return self._cutoff_hz

    @property
    def sample_rate_hz(self) -> float:
        """Return the sample rate in Hz."""
        return self._sample_rate_hz

    @property
    def num_channels(self) -> int:
        """Return the number of channels."""
        return self._num_channels

    @property
    def coefficients(self) -> ButterworthCoefficients:
        """Return the filter coefficients."""
        return self._coeffs

    def reset(self) -> None:
        """Reset filter state to zero.

        Call this when starting a new stream or after a gap in data.
        """
        self._z1.fill(0.0)
        self._z2.fill(0.0)

    def prime(
        self, x: NDArray[np.float64] | tuple[float, ...] | list[float]
    ) -> None:
        """Prime filter state to a steady value for artifact-free startup.

        Sets internal delay elements so that a constant input equal to `x`
        produces an immediate output equal to `x` (no startup transient).
        """
        x_arr = np.asarray(x, dtype=np.float64)
        if x_arr.shape != (self._num_channels,):
            raise ValueError(
                f"Input must have shape ({self._num_channels},), got {x_arr.shape}"
            )

        c = self._coeffs
        # Direct Form II Transposed steady state for DC input:
        # z1 = (1 - b0) * x, z2 = (b2 - a2) * x
        self._z1[:] = (1.0 - c.b0) * x_arr
        self._z2[:] = (c.b2 - c.a2) * x_arr

    def process_sample(
        self, x: NDArray[np.float64] | tuple[float, ...] | list[float]
    ) -> NDArray[np.float64]:
        """Process a single multi-channel sample.

        Args:
            x: Input sample with num_channels values.

        Returns:
            Filtered output sample as numpy array.

        Raises:
            ValueError: If input length doesn't match num_channels.
        """
        x_arr = np.asarray(x, dtype=np.float64)
        if x_arr.shape != (self._num_channels,):
            raise ValueError(
                f"Input must have shape ({self._num_channels},), got {x_arr.shape}"
            )

        # Direct Form II Transposed:
        # y[n] = b0*x[n] + z1[n-1]
        # z1[n] = b1*x[n] - a1*y[n] + z2[n-1]
        # z2[n] = b2*x[n] - a2*y[n]
        c = self._coeffs
        y = c.b0 * x_arr + self._z1
        self._z1 = c.b1 * x_arr - c.a1 * y + self._z2
        self._z2 = c.b2 * x_arr - c.a2 * y

        return y

    def process_batch(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Process a batch of samples.

        Args:
            x: Input array of shape (num_samples, num_channels).

        Returns:
            Filtered output array of same shape.

        Raises:
            ValueError: If input shape is invalid.
        """
        if x.ndim != 2 or x.shape[1] != self._num_channels:
            raise ValueError(
                f"Input must have shape (N, {self._num_channels}), got {x.shape}"
            )

        num_samples = x.shape[0]
        y = np.empty_like(x, dtype=np.float64)

        c = self._coeffs
        z1 = self._z1.copy()
        z2 = self._z2.copy()

        for i in range(num_samples):
            x_i = x[i]
            y_i = c.b0 * x_i + z1
            z1 = c.b1 * x_i - c.a1 * y_i + z2
            z2 = c.b2 * x_i - c.a2 * y_i
            y[i] = y_i

        self._z1 = z1
        self._z2 = z2

        return y


class FilterPipeline:
    """Manages optional filtering for the processing engine.

    Provides a unified interface that can be enabled/disabled without
    requiring the caller to track filter state.

    Example:
        pipeline = FilterPipeline(
            enabled=True,
            cutoff_hz=10.0,
            sample_rate_hz=1000.0
        )

        # Process samples - filtering applied if enabled
        for sample in samples:
            output = pipeline.apply(sample)

        # Disable filtering
        pipeline.enabled = False

        # Now samples pass through unchanged
        for sample in samples:
            output = pipeline.apply(sample)  # Returns input unchanged
    """

    def __init__(
        self,
        enabled: bool = False,
        cutoff_hz: float = MAX_CUTOFF_HZ,
        sample_rate_hz: float = 1000.0,
        num_channels: int = 6,
    ) -> None:
        """Initialize the filter pipeline.

        Args:
            enabled: Whether filtering is active.
            cutoff_hz: Cutoff frequency in Hz (0.7-120).
            sample_rate_hz: Sample rate in Hz.
            num_channels: Number of channels.
        """
        self._enabled = enabled
        self._cutoff_hz = cutoff_hz
        self._sample_rate_hz = sample_rate_hz
        self._num_channels = num_channels

        self._needs_prime = False

        # Create filter if enabled and parameters are valid
        self._filter: LowPassFilter | None = None
        if enabled:
            self._create_filter()

    def _create_filter(self) -> None:
        """Create or recreate the internal filter."""
        self._filter = LowPassFilter(
            cutoff_hz=self._cutoff_hz,
            sample_rate_hz=self._sample_rate_hz,
            num_channels=self._num_channels,
        )
        self._needs_prime = True

    @property
    def enabled(self) -> bool:
        """Return whether filtering is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable filtering."""
        if value and not self._enabled:
            self._create_filter()
        self._enabled = value

    @property
    def cutoff_hz(self) -> float:
        """Return the cutoff frequency in Hz."""
        return self._cutoff_hz

    @cutoff_hz.setter
    def cutoff_hz(self, value: float) -> None:
        """Set the cutoff frequency, recreating the filter."""
        if value != self._cutoff_hz:
            self._cutoff_hz = value
            if self._enabled:
                self._create_filter()

    @property
    def sample_rate_hz(self) -> float:
        """Return the sample rate in Hz."""
        return self._sample_rate_hz

    @sample_rate_hz.setter
    def sample_rate_hz(self, value: float) -> None:
        """Set the sample rate, recreating the filter."""
        if value != self._sample_rate_hz:
            self._sample_rate_hz = value
            if self._enabled:
                self._create_filter()

    def reset(self) -> None:
        """Reset filter state.

        After reset, the next input primes the filter to avoid a startup transient.
        """
        if self._filter is not None:
            self._filter.reset()
            self._needs_prime = True

    def apply(
        self, x: NDArray[np.float64] | tuple[float, ...] | list[float]
    ) -> NDArray[np.float64]:
        """Apply filtering to a single sample if enabled.

        Args:
            x: Input sample with num_channels values.

        Returns:
            Filtered output if enabled, otherwise input converted to array.
        """
        x_arr = np.asarray(x, dtype=np.float64)
        if self._enabled and self._filter is not None:
            if self._needs_prime:
                self._filter.prime(x_arr)
                self._needs_prime = False
                return x_arr
            return self._filter.process_sample(x_arr)
        return x_arr

    def apply_batch(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Apply filtering to a batch of samples if enabled.

        Args:
            x: Input array of shape (num_samples, num_channels).

        Returns:
            Filtered output if enabled, otherwise input unchanged.
        """
        if self._enabled and self._filter is not None:
            if self._needs_prime and x.shape[0] > 0:
                self._filter.prime(x[0])
                self._needs_prime = False
            return self._filter.process_batch(x)
        return x
