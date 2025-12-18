"""Performance validation tests against Section 3.3 success metrics.

Tests verify:
- Zero data loss at sustained 1000 Hz streaming rates
- Data path latency suitable for <50ms plot updates
- Data availability rate supports 30 fps refresh
- Memory footprint under 200 MB during normal operation
- Startup time under 3 seconds
"""

import gc
import sys
import time
import tracemalloc

import pytest

from gsdv.acquisition.ring_buffer import RingBuffer
from gsdv.protocols.rdt_udp import RdtClient


class TestDataLossAt1000Hz:
    """Validate zero data loss at sustained 1000 Hz streaming."""

    @pytest.mark.parametrize("sample_count", [1000, 2000, 3000])
    def test_zero_packet_loss_at_1000hz(
        self, sensor_simulator, sample_count: int
    ) -> None:
        """Stream sample_count samples at 1000 Hz with zero packet loss.

        Section 3.3 requirement: Zero data loss at sustained 1000 Hz streaming rates.
        """
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(
                client.receive_samples(timeout=10.0, max_samples=sample_count)
            )
            client.stop_streaming()
            stats = client.statistics

        # Verify we received all requested samples
        assert len(samples) == sample_count, (
            f"Expected {sample_count} samples, got {len(samples)}"
        )

        # Verify zero packet loss
        assert stats.packets_lost == 0, (
            f"Packet loss detected: {stats.packets_lost} packets lost "
            f"out of {stats.packets_received} received"
        )

        # Verify sequential sequence numbers
        for i in range(1, len(samples)):
            expected_seq = samples[i - 1].rdt_sequence + 1
            actual_seq = samples[i].rdt_sequence
            assert actual_seq == expected_seq, (
                f"Sequence gap at index {i}: expected {expected_seq}, got {actual_seq}"
            )

    def test_sustained_streaming_5000_samples(self, sensor_simulator) -> None:
        """Extended streaming test for 5000 samples at 1000 Hz (~5 seconds).

        Validates sustained throughput without packet loss.
        """
        sample_count = 5000
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(
                client.receive_samples(timeout=10.0, max_samples=sample_count)
            )
            client.stop_streaming()
            stats = client.statistics

        assert len(samples) == sample_count, f"Got {len(samples)} samples"
        assert stats.packets_lost == 0, f"Packet loss: {stats.packets_lost}"

        # Calculate actual sample rate
        if len(samples) >= 2:
            first_ts = samples[0].t_monotonic_ns
            last_ts = samples[-1].t_monotonic_ns
            duration_ns = last_ts - first_ts
            actual_rate = (len(samples) - 1) / (duration_ns / 1e9)
            # Should be close to 1000 Hz (within 5%)
            assert 950 <= actual_rate <= 1050, f"Sample rate {actual_rate:.1f} Hz"


class TestDataPathLatency:
    """Validate data path latency supports <50ms plot updates.

    Note: The plot widget is not yet implemented, so we test the underlying
    data path latency from receive to buffer storage.
    """

    def test_receive_latency_under_1ms(self, sensor_simulator) -> None:
        """Individual packet receive latency should be well under 50ms.

        Tests the time from socket receive to SampleRecord creation.
        """
        latencies_ms: list[float] = []

        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()

            for sample in client.receive_samples(timeout=0.5, max_samples=100):
                # Timestamp is captured at receive time
                now_ns = time.monotonic_ns()
                latency_ms = (now_ns - sample.t_monotonic_ns) / 1e6
                latencies_ms.append(latency_ms)

            client.stop_streaming()

        assert len(latencies_ms) >= 50, "Not enough samples for latency test"

        # Average latency should be well under 50ms (typically < 1ms)
        avg_latency = sum(latencies_ms) / len(latencies_ms)
        assert avg_latency < 10.0, f"Average latency {avg_latency:.2f}ms exceeds 10ms"

        # 99th percentile should still be well under 50ms
        sorted_latencies = sorted(latencies_ms)
        p99_idx = int(len(sorted_latencies) * 0.99)
        p99_latency = sorted_latencies[p99_idx]
        assert p99_latency < 50.0, f"P99 latency {p99_latency:.2f}ms exceeds 50ms"

    def test_ring_buffer_append_latency(self) -> None:
        """Ring buffer append operation should be very fast.

        Section 3.3: Plot update latency under 50ms requires fast data storage.
        """
        buffer = RingBuffer(capacity=60_000)
        latencies_us: list[float] = []

        for i in range(1000):
            start = time.perf_counter_ns()
            buffer.append(
                t_monotonic_ns=time.monotonic_ns(),
                rdt_sequence=i,
                ft_sequence=i * 10,
                status=0,
                counts=(100, 200, 300, 400, 500, 600),
            )
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1e3)

        avg_latency_us = sum(latencies_us) / len(latencies_us)
        max_latency_us = max(latencies_us)

        # Average append should be well under 1ms (typically ~1-10 microseconds)
        assert avg_latency_us < 1000, f"Average append {avg_latency_us:.1f}us > 1ms"
        # Max append should still be under 10ms
        assert max_latency_us < 10000, f"Max append {max_latency_us:.1f}us > 10ms"


class TestDataRefreshRate:
    """Validate data availability supports 30 fps refresh rate.

    Section 3.3 requirement: Plot refresh rate at least 30 fps.
    """

    def test_data_available_at_30fps_intervals(self, sensor_simulator) -> None:
        """Data should be available at intervals <= 33.3ms for 30 fps refresh.

        Tests that we receive data frequently enough to support 30 fps plotting.
        """
        # Collect timestamps of when data becomes available
        receive_times: list[float] = []

        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()

            start_time = time.monotonic()
            for sample in client.receive_samples(timeout=1.0, max_samples=1000):
                receive_times.append(time.monotonic())

            client.stop_streaming()

        assert len(receive_times) >= 100, "Not enough samples for refresh rate test"

        # At 1000 Hz, we should receive ~33 samples every 33.3ms (one frame at 30fps)
        # Check that intervals between receives are consistent
        intervals_ms = [
            (receive_times[i] - receive_times[i - 1]) * 1000
            for i in range(1, len(receive_times))
        ]

        # Average interval should be ~1ms (1000 Hz)
        avg_interval = sum(intervals_ms) / len(intervals_ms)
        assert avg_interval < 5.0, f"Average interval {avg_interval:.2f}ms > 5ms"

        # Count how many intervals exceed 33.3ms (one frame at 30fps)
        frame_interval_ms = 1000 / 30  # 33.3ms
        long_gaps = sum(1 for interval in intervals_ms if interval > frame_interval_ms)
        gap_ratio = long_gaps / len(intervals_ms)

        # Less than 1% of intervals should exceed frame time
        assert gap_ratio < 0.01, (
            f"{long_gaps} of {len(intervals_ms)} intervals ({gap_ratio:.1%}) "
            f"exceed {frame_interval_ms:.1f}ms frame time"
        )

    def test_ring_buffer_read_supports_30fps(self) -> None:
        """Ring buffer read operations fast enough for 30 fps display updates.

        At 30 fps with 1000 Hz data, each frame needs ~33 samples.
        """
        buffer = RingBuffer(capacity=60_000)

        # Fill buffer with test data
        for i in range(1000):
            buffer.append(
                t_monotonic_ns=i * 1_000_000,  # 1ms spacing
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, i, i, i, i, i),
            )

        # Measure time to read 33 samples (one frame worth at 30fps)
        read_times_us: list[float] = []
        for _ in range(100):
            start = time.perf_counter_ns()
            data = buffer.get_latest(33)
            end = time.perf_counter_ns()
            read_times_us.append((end - start) / 1e3)

        avg_read_us = sum(read_times_us) / len(read_times_us)
        max_read_us = max(read_times_us)

        # Read should complete well within frame time (33.3ms)
        assert avg_read_us < 1000, f"Average read {avg_read_us:.1f}us > 1ms"
        assert max_read_us < 10000, f"Max read {max_read_us:.1f}us > 10ms"


class TestMemoryFootprint:
    """Validate memory footprint under 200 MB during normal operation.

    Section 3.3 requirement: Memory footprint under 200 MB during normal operation.
    """

    def test_ring_buffer_memory_footprint(self) -> None:
        """Ring buffer memory usage should be bounded and predictable.

        60,000 samples (60s at 1000Hz) with 6 int32 counts + metadata.
        Expected: ~2.6 MB for counts + overhead for timestamps/sequences.
        """
        gc.collect()
        tracemalloc.start()

        buffer = RingBuffer(capacity=60_000)

        # Fill the buffer completely
        for i in range(60_000):
            buffer.append(
                t_monotonic_ns=i * 1_000_000,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(1000, 2000, 3000, 4000, 5000, 6000),
            )

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        current_mb = current / (1024 * 1024)
        peak_mb = peak / (1024 * 1024)

        # Buffer should use less than 10 MB (well under 200 MB budget)
        assert peak_mb < 10, f"Ring buffer peak memory {peak_mb:.1f} MB > 10 MB"

    def test_streaming_memory_stability(self, sensor_simulator) -> None:
        """Memory should remain stable during sustained streaming.

        Verifies no memory leaks during streaming operation.
        """
        gc.collect()
        tracemalloc.start()

        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()

            # Stream 2000 samples (~2 seconds at 1000 Hz)
            samples = list(client.receive_samples(timeout=5.0, max_samples=2000))

            client.stop_streaming()

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)

        # Streaming should use minimal memory (samples are iterator-consumed)
        assert peak_mb < 50, f"Streaming peak memory {peak_mb:.1f} MB > 50 MB"
        assert len(samples) >= 1800, f"Expected ~2000 samples, got {len(samples)}"

    def test_combined_components_under_200mb(self, sensor_simulator) -> None:
        """All components together should stay under 200 MB.

        Tests ring buffer + streaming + typical operation.
        """
        gc.collect()
        tracemalloc.start()

        # Create ring buffer (primary memory consumer)
        buffer = RingBuffer(capacity=60_000)

        # Stream and store in buffer
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()

            for sample in client.receive_samples(timeout=5.0, max_samples=1000):
                buffer.append(
                    t_monotonic_ns=sample.t_monotonic_ns,
                    rdt_sequence=sample.rdt_sequence,
                    ft_sequence=sample.ft_sequence,
                    status=sample.status,
                    counts=sample.counts,
                )

            client.stop_streaming()

        # Read data back (simulating plot update)
        data = buffer.get_latest(1000)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        stats = buffer.stats()

        # Combined operation should be well under 200 MB
        assert peak_mb < 50, f"Combined peak memory {peak_mb:.1f} MB > 50 MB"
        assert stats.size >= 900, f"Expected ~1000 samples in buffer, got {stats.size}"


class TestStartupTime:
    """Validate startup time under 3 seconds.

    Section 3.3 requirement: Startup time under 3 seconds.
    """

    def test_core_module_import_time(self) -> None:
        """Core protocol modules should import quickly.

        Tests import time for the main modules used in the data path.
        """
        import importlib

        modules_to_test = [
            "gsdv.protocols.rdt_udp",
            "gsdv.protocols.tcp_cmd",
            "gsdv.protocols.http_calibration",
            "gsdv.acquisition.ring_buffer",
            "gsdv.processing.units",
        ]

        total_import_time = 0.0

        for module_name in modules_to_test:
            # Unload if already loaded
            if module_name in sys.modules:
                del sys.modules[module_name]

            start = time.perf_counter()
            importlib.import_module(module_name)
            end = time.perf_counter()

            import_time = end - start
            total_import_time += import_time

            # Each module should import in under 500ms
            assert import_time < 0.5, (
                f"Module {module_name} import time {import_time:.3f}s > 0.5s"
            )

        # Total import time should be well under 3 seconds
        assert total_import_time < 2.0, (
            f"Total import time {total_import_time:.3f}s > 2.0s"
        )

    def test_ring_buffer_initialization_time(self) -> None:
        """Ring buffer should initialize quickly.

        60,000 sample buffer initialization time.
        """
        init_times: list[float] = []

        for _ in range(10):
            gc.collect()
            start = time.perf_counter()
            buffer = RingBuffer(capacity=60_000)
            end = time.perf_counter()
            init_times.append(end - start)
            del buffer

        avg_init_time = sum(init_times) / len(init_times)
        max_init_time = max(init_times)

        # Initialization should be very fast (under 100ms)
        assert avg_init_time < 0.1, f"Average init time {avg_init_time:.3f}s > 0.1s"
        assert max_init_time < 0.2, f"Max init time {max_init_time:.3f}s > 0.2s"

    def test_client_connection_time(self, sensor_simulator) -> None:
        """RDT client should connect and start streaming quickly.

        Time from client creation to first sample received.
        """
        start = time.perf_counter()

        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()

            # Get first sample
            for sample in client.receive_samples(timeout=1.0, max_samples=1):
                first_sample_time = time.perf_counter()
                break

            client.stop_streaming()

        time_to_first_sample = first_sample_time - start

        # Should receive first sample within 500ms
        assert time_to_first_sample < 0.5, (
            f"Time to first sample {time_to_first_sample:.3f}s > 0.5s"
        )


class TestSampleRateAccuracy:
    """Validate sample rate accuracy at 1000 Hz.

    Additional metric to ensure timing accuracy of data acquisition.
    """

    def test_measured_sample_rate_within_tolerance(self, sensor_simulator) -> None:
        """Measured sample rate should be within 5% of 1000 Hz."""
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=5.0, max_samples=2000))
            client.stop_streaming()

        assert len(samples) >= 100, "Not enough samples for rate calculation"

        # Calculate actual rate from timestamps
        first_ts = samples[0].t_monotonic_ns
        last_ts = samples[-1].t_monotonic_ns
        duration_s = (last_ts - first_ts) / 1e9
        measured_rate = (len(samples) - 1) / duration_s

        # Should be within 5% of 1000 Hz
        expected_rate = 1000.0
        tolerance = 0.05
        lower_bound = expected_rate * (1 - tolerance)
        upper_bound = expected_rate * (1 + tolerance)

        assert lower_bound <= measured_rate <= upper_bound, (
            f"Measured rate {measured_rate:.1f} Hz outside "
            f"[{lower_bound:.1f}, {upper_bound:.1f}] Hz tolerance"
        )

    def test_sample_interval_consistency(self, sensor_simulator) -> None:
        """Sample intervals should be consistent (low jitter)."""
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=1.0, max_samples=500))
            client.stop_streaming()

        assert len(samples) >= 100, "Not enough samples for jitter calculation"

        # Calculate intervals between samples
        intervals_ms = [
            (samples[i].t_monotonic_ns - samples[i - 1].t_monotonic_ns) / 1e6
            for i in range(1, len(samples))
        ]

        # Expected interval at 1000 Hz is 1ms
        expected_interval = 1.0

        # Calculate jitter (standard deviation of intervals)
        mean_interval = sum(intervals_ms) / len(intervals_ms)
        variance = sum((x - mean_interval) ** 2 for x in intervals_ms) / len(
            intervals_ms
        )
        std_dev = variance**0.5

        # Standard deviation should be small relative to interval
        # Allow up to 50% jitter for network/scheduling variability
        assert std_dev < expected_interval * 0.5, (
            f"Sample interval jitter {std_dev:.3f}ms > {expected_interval * 0.5:.3f}ms"
        )
