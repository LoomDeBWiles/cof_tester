"""Tests for digital filtering implementations."""

import math

import numpy as np
import pytest

from gsdv.processing.filters import (
    MAX_CUTOFF_HZ,
    MIN_CUTOFF_HZ,
    ButterworthCoefficients,
    FilterPipeline,
    LowPassFilter,
    compute_butterworth_coefficients,
)


class TestButterworthCoefficients:
    """Tests for coefficient computation."""

    def test_valid_coefficients_at_10hz_1000hz_sample_rate(self) -> None:
        """Compute coefficients for 10 Hz cutoff at 1000 Hz sample rate."""
        coeffs = compute_butterworth_coefficients(cutoff_hz=10.0, sample_rate_hz=1000.0)

        assert isinstance(coeffs, ButterworthCoefficients)
        # b coefficients should be positive for low-pass
        assert coeffs.b0 > 0
        assert coeffs.b1 > 0
        assert coeffs.b2 > 0
        # Verify b1 = 2*b0 for Butterworth (symmetric numerator)
        assert math.isclose(coeffs.b1, 2 * coeffs.b0, rel_tol=1e-10)
        assert math.isclose(coeffs.b2, coeffs.b0, rel_tol=1e-10)

    def test_coefficients_at_minimum_cutoff(self) -> None:
        """Compute coefficients at minimum cutoff frequency."""
        coeffs = compute_butterworth_coefficients(cutoff_hz=MIN_CUTOFF_HZ, sample_rate_hz=1000.0)
        assert coeffs.b0 > 0

    def test_coefficients_at_maximum_cutoff(self) -> None:
        """Compute coefficients at maximum cutoff frequency."""
        coeffs = compute_butterworth_coefficients(cutoff_hz=MAX_CUTOFF_HZ, sample_rate_hz=1000.0)
        assert coeffs.b0 > 0

    def test_cutoff_below_minimum_raises_error(self) -> None:
        """Cutoff below minimum should raise ValueError."""
        with pytest.raises(ValueError, match="cutoff_hz must be in"):
            compute_butterworth_coefficients(cutoff_hz=0.5, sample_rate_hz=1000.0)

    def test_cutoff_above_maximum_raises_error(self) -> None:
        """Cutoff above maximum should raise ValueError."""
        with pytest.raises(ValueError, match="cutoff_hz must be in"):
            compute_butterworth_coefficients(cutoff_hz=150.0, sample_rate_hz=1000.0)

    def test_cutoff_at_nyquist_raises_error(self) -> None:
        """Cutoff at or above Nyquist frequency should raise ValueError."""
        with pytest.raises(ValueError, match="must be less than Nyquist"):
            compute_butterworth_coefficients(cutoff_hz=50.0, sample_rate_hz=100.0)

    def test_negative_sample_rate_raises_error(self) -> None:
        """Negative sample rate should raise ValueError."""
        with pytest.raises(ValueError, match="sample_rate_hz must be positive"):
            compute_butterworth_coefficients(cutoff_hz=10.0, sample_rate_hz=-1000.0)

    def test_zero_sample_rate_raises_error(self) -> None:
        """Zero sample rate should raise ValueError."""
        with pytest.raises(ValueError, match="sample_rate_hz must be positive"):
            compute_butterworth_coefficients(cutoff_hz=10.0, sample_rate_hz=0.0)

    def test_filter_stability(self) -> None:
        """Verify filter is stable (poles inside unit circle)."""
        coeffs = compute_butterworth_coefficients(cutoff_hz=10.0, sample_rate_hz=1000.0)
        # For stability, roots of 1 + a1*z^-1 + a2*z^-2 must be inside unit circle
        # Using the characteristic equation z^2 + a1*z + a2 = 0
        discriminant = coeffs.a1 * coeffs.a1 - 4 * coeffs.a2
        if discriminant >= 0:
            # Real roots
            root1 = (-coeffs.a1 + math.sqrt(discriminant)) / 2
            root2 = (-coeffs.a1 - math.sqrt(discriminant)) / 2
            assert abs(root1) < 1
            assert abs(root2) < 1
        else:
            # Complex roots: magnitude = sqrt(a2)
            assert abs(coeffs.a2) < 1


class TestLowPassFilter:
    """Tests for IIR low-pass filter."""

    def test_filter_initialization(self) -> None:
        """Filter initializes with correct parameters."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=6)
        assert lpf.cutoff_hz == 10.0
        assert lpf.sample_rate_hz == 1000.0
        assert lpf.num_channels == 6

    def test_filter_with_invalid_channels_raises_error(self) -> None:
        """Zero or negative channels should raise ValueError."""
        with pytest.raises(ValueError, match="num_channels must be positive"):
            LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=0)

    def test_process_single_sample(self) -> None:
        """Process a single sample through the filter."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        sample = np.array([1.0, 2.0, 3.0])
        output = lpf.process_sample(sample)
        assert output.shape == (3,)
        assert output.dtype == np.float64

    def test_process_sample_with_tuple(self) -> None:
        """Process a tuple input."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        output = lpf.process_sample((1.0, 2.0, 3.0))
        assert output.shape == (3,)

    def test_process_sample_with_list(self) -> None:
        """Process a list input."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        output = lpf.process_sample([1.0, 2.0, 3.0])
        assert output.shape == (3,)

    def test_process_sample_wrong_size_raises_error(self) -> None:
        """Wrong input size should raise ValueError."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        with pytest.raises(ValueError, match="Input must have shape"):
            lpf.process_sample(np.array([1.0, 2.0]))

    def test_process_batch(self) -> None:
        """Process a batch of samples."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        batch = np.random.randn(100, 3)
        output = lpf.process_batch(batch)
        assert output.shape == (100, 3)
        assert output.dtype == np.float64

    def test_process_batch_wrong_shape_raises_error(self) -> None:
        """Wrong batch shape should raise ValueError."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        with pytest.raises(ValueError, match="Input must have shape"):
            lpf.process_batch(np.random.randn(100, 4))

    def test_filter_reset(self) -> None:
        """Reset clears filter state."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        # Process some samples to build up state
        for _ in range(10):
            lpf.process_sample(np.array([1.0, 1.0, 1.0]))
        # Reset and process again
        lpf.reset()
        # After reset, first output should be same as a fresh filter
        fresh_lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        sample = np.array([1.0, 2.0, 3.0])
        output_after_reset = lpf.process_sample(sample)
        output_fresh = fresh_lpf.process_sample(sample)
        np.testing.assert_array_almost_equal(output_after_reset, output_fresh)

    def test_dc_passthrough(self) -> None:
        """DC signal should pass through unchanged after settling."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=1)
        dc_value = 5.0
        # Let filter settle with DC input
        for _ in range(500):
            output = lpf.process_sample(np.array([dc_value]))
        # After settling, output should equal DC input
        assert math.isclose(output[0], dc_value, rel_tol=1e-3)

    def test_high_frequency_attenuation(self) -> None:
        """High frequency signal should be attenuated."""
        sample_rate = 1000.0
        cutoff = 10.0
        lpf = LowPassFilter(cutoff_hz=cutoff, sample_rate_hz=sample_rate, num_channels=1)

        # Generate high frequency sine wave (100 Hz, well above cutoff)
        n_samples = 1000
        t = np.arange(n_samples) / sample_rate
        high_freq = 100.0
        input_signal = np.sin(2 * np.pi * high_freq * t)

        # Process through filter
        output = np.zeros(n_samples)
        for i in range(n_samples):
            output[i] = lpf.process_sample(np.array([input_signal[i]]))[0]

        # Skip transient (first 100 samples)
        input_rms = np.sqrt(np.mean(input_signal[100:] ** 2))
        output_rms = np.sqrt(np.mean(output[100:] ** 2))

        # Output should be significantly attenuated (at least 10x for 100 Hz vs 10 Hz cutoff)
        assert output_rms < input_rms / 10

    def test_low_frequency_passthrough(self) -> None:
        """Low frequency signal should pass through with minimal attenuation."""
        sample_rate = 1000.0
        cutoff = 100.0
        lpf = LowPassFilter(cutoff_hz=cutoff, sample_rate_hz=sample_rate, num_channels=1)

        # Generate low frequency sine wave (1 Hz, well below cutoff)
        n_samples = 2000
        t = np.arange(n_samples) / sample_rate
        low_freq = 1.0
        input_signal = np.sin(2 * np.pi * low_freq * t)

        # Process through filter
        output = np.zeros(n_samples)
        for i in range(n_samples):
            output[i] = lpf.process_sample(np.array([input_signal[i]]))[0]

        # Skip transient
        input_rms = np.sqrt(np.mean(input_signal[500:] ** 2))
        output_rms = np.sqrt(np.mean(output[500:] ** 2))

        # Output should be close to input (within 5%)
        assert math.isclose(output_rms, input_rms, rel_tol=0.05)

    def test_streaming_consistency(self) -> None:
        """Batch and sample-by-sample processing give same results."""
        lpf1 = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)
        lpf2 = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=3)

        batch = np.random.randn(50, 3)

        # Process batch
        batch_output = lpf1.process_batch(batch)

        # Process sample by sample
        sample_output = np.zeros_like(batch)
        for i in range(len(batch)):
            sample_output[i] = lpf2.process_sample(batch[i])

        np.testing.assert_array_almost_equal(batch_output, sample_output)

    def test_independent_channel_processing(self) -> None:
        """Each channel is filtered independently."""
        lpf = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=2)

        # Feed different signals to each channel
        lpf_ch0 = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=1)
        lpf_ch1 = LowPassFilter(cutoff_hz=10.0, sample_rate_hz=1000.0, num_channels=1)

        for i in range(100):
            sample = np.array([float(i), float(i * 2)])
            output = lpf.process_sample(sample)
            output_ch0 = lpf_ch0.process_sample(np.array([float(i)]))
            output_ch1 = lpf_ch1.process_sample(np.array([float(i * 2)]))

            assert math.isclose(output[0], output_ch0[0], rel_tol=1e-10)
            assert math.isclose(output[1], output_ch1[0], rel_tol=1e-10)


class TestFilterPipeline:
    """Tests for the filter pipeline."""

    def test_pipeline_disabled_by_default(self) -> None:
        """Pipeline is disabled by default."""
        pipeline = FilterPipeline()
        assert not pipeline.enabled

    def test_pipeline_passes_through_when_disabled(self) -> None:
        """Disabled pipeline passes input unchanged."""
        pipeline = FilterPipeline(enabled=False)
        sample = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        output = pipeline.apply(sample)
        np.testing.assert_array_equal(output, sample)

    def test_pipeline_filters_when_enabled(self) -> None:
        """Enabled pipeline applies filtering."""
        pipeline = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)
        sample = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        output = pipeline.apply(sample)
        # First sample through filter won't equal input
        assert not np.allclose(output, sample)

    def test_enable_toggle(self) -> None:
        """Can toggle filtering on and off."""
        pipeline = FilterPipeline(enabled=False, cutoff_hz=10.0, sample_rate_hz=1000.0)

        sample = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

        # Disabled: passthrough
        output_disabled = pipeline.apply(sample.copy())
        np.testing.assert_array_equal(output_disabled, sample)

        # Enable
        pipeline.enabled = True
        output_enabled = pipeline.apply(sample.copy())
        assert not np.allclose(output_enabled, sample)

        # Disable again
        pipeline.enabled = False
        output_disabled_again = pipeline.apply(sample.copy())
        np.testing.assert_array_equal(output_disabled_again, sample)

    def test_cutoff_change_recreates_filter(self) -> None:
        """Changing cutoff recreates the filter."""
        pipeline = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)
        assert pipeline.cutoff_hz == 10.0

        pipeline.cutoff_hz = 50.0
        assert pipeline.cutoff_hz == 50.0

    def test_sample_rate_change_recreates_filter(self) -> None:
        """Changing sample rate recreates the filter."""
        pipeline = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)
        assert pipeline.sample_rate_hz == 1000.0

        pipeline.sample_rate_hz = 2000.0
        assert pipeline.sample_rate_hz == 2000.0

    def test_reset(self) -> None:
        """Reset clears filter state."""
        pipeline = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)

        # Process some samples
        sample = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        for _ in range(10):
            pipeline.apply(sample)

        # Reset
        pipeline.reset()

        # Verify reset by comparing with fresh pipeline
        fresh = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)
        output_after_reset = pipeline.apply(sample.copy())
        output_fresh = fresh.apply(sample.copy())
        np.testing.assert_array_almost_equal(output_after_reset, output_fresh)

    def test_apply_batch_when_disabled(self) -> None:
        """Batch apply passes through when disabled."""
        pipeline = FilterPipeline(enabled=False)
        batch = np.random.randn(100, 6)
        output = pipeline.apply_batch(batch)
        np.testing.assert_array_equal(output, batch)

    def test_apply_batch_when_enabled(self) -> None:
        """Batch apply filters when enabled."""
        pipeline = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)
        batch = np.random.randn(100, 6)
        output = pipeline.apply_batch(batch)
        assert output.shape == batch.shape
        # Output should differ from input
        assert not np.allclose(output, batch)

    def test_pipeline_with_tuple_input(self) -> None:
        """Pipeline handles tuple input."""
        pipeline = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)
        output = pipeline.apply((1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
        assert output.shape == (6,)

    def test_pipeline_with_list_input(self) -> None:
        """Pipeline handles list input."""
        pipeline = FilterPipeline(enabled=True, cutoff_hz=10.0, sample_rate_hz=1000.0)
        output = pipeline.apply([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        assert output.shape == (6,)
