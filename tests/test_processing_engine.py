"""Tests for processing engine."""

import queue
import threading
import time

import pytest

from gsdv.models import CalibrationInfo, SampleRecord
from gsdv.processing import ProcessingEngine, SoftZeroOffsets


def make_sample(
    counts: tuple[int, int, int, int, int, int] = (1000, 2000, 3000, 4000, 5000, 6000),
    t_monotonic_ns: int = 1000000,
    rdt_sequence: int = 1,
    ft_sequence: int = 1,
    status: int = 0,
) -> SampleRecord:
    """Create a sample for testing."""
    return SampleRecord(
        t_monotonic_ns=t_monotonic_ns,
        rdt_sequence=rdt_sequence,
        ft_sequence=ft_sequence,
        status=status,
        counts=counts,
    )


def make_calibration(cpf: float = 1000000.0, cpt: float = 1000000.0) -> CalibrationInfo:
    """Create calibration info for testing."""
    return CalibrationInfo(counts_per_force=cpf, counts_per_torque=cpt)


class TestSoftZeroOffsets:
    """Tests for SoftZeroOffsets dataclass."""

    def test_create_with_valid_counts(self) -> None:
        offsets = SoftZeroOffsets(
            force_counts=(100, 200, 300),
            torque_counts=(400, 500, 600),
        )
        assert offsets.force_counts == (100, 200, 300)
        assert offsets.torque_counts == (400, 500, 600)

    def test_rejects_wrong_force_count_length(self) -> None:
        with pytest.raises(ValueError, match="force_counts must have 3 elements"):
            SoftZeroOffsets(
                force_counts=(100, 200),
                torque_counts=(400, 500, 600),
            )

    def test_rejects_wrong_torque_count_length(self) -> None:
        with pytest.raises(ValueError, match="torque_counts must have 3 elements"):
            SoftZeroOffsets(
                force_counts=(100, 200, 300),
                torque_counts=(400, 500, 600, 700),
            )

    def test_from_sample(self) -> None:
        sample = make_sample(counts=(100, 200, 300, 400, 500, 600))
        offsets = SoftZeroOffsets.from_sample(sample)
        assert offsets.force_counts == (100, 200, 300)
        assert offsets.torque_counts == (400, 500, 600)

    def test_zero_factory(self) -> None:
        offsets = SoftZeroOffsets.zero()
        assert offsets.force_counts == (0, 0, 0)
        assert offsets.torque_counts == (0, 0, 0)


class TestProcessingEngineInit:
    """Tests for ProcessingEngine initialization."""

    def test_stores_calibration(self) -> None:
        calibration = make_calibration(cpf=500000.0, cpt=600000.0)
        engine = ProcessingEngine(calibration)
        assert engine.calibration.counts_per_force == 500000.0
        assert engine.calibration.counts_per_torque == 600000.0

    def test_initially_not_running(self) -> None:
        engine = ProcessingEngine(make_calibration())
        assert engine.is_running is False

    def test_initial_soft_zero_is_none(self) -> None:
        engine = ProcessingEngine(make_calibration())
        assert engine.soft_zero is None

    def test_queues_created(self) -> None:
        engine = ProcessingEngine(make_calibration())
        assert engine.input_queue is not None
        assert engine.logger_queue is not None

    def test_custom_queue_sizes(self) -> None:
        engine = ProcessingEngine(
            make_calibration(),
            input_queue_size=50,
            output_queue_size=100,
        )
        # Queue maxsize is set correctly
        assert engine.input_queue.maxsize == 50
        assert engine.logger_queue.maxsize == 100


class TestProcessingEngineConversion:
    """Tests for BL-1 counts to engineering units conversion."""

    def test_converts_counts_to_force_newtons(self) -> None:
        # cpf = 1000000, so 1000000 counts = 1 N
        calibration = make_calibration(cpf=1000000.0, cpt=1000000.0)
        engine = ProcessingEngine(calibration)
        sample = make_sample(counts=(1000000, 2000000, 3000000, 0, 0, 0))

        processed = engine.process_sample(sample)

        assert processed.force_N is not None
        assert processed.force_N[0] == pytest.approx(1.0)
        assert processed.force_N[1] == pytest.approx(2.0)
        assert processed.force_N[2] == pytest.approx(3.0)

    def test_converts_counts_to_torque_newton_meters(self) -> None:
        # cpt = 1000000, so 1000000 counts = 1 N-m
        calibration = make_calibration(cpf=1000000.0, cpt=1000000.0)
        engine = ProcessingEngine(calibration)
        sample = make_sample(counts=(0, 0, 0, 500000, 1000000, 1500000))

        processed = engine.process_sample(sample)

        assert processed.torque_Nm is not None
        assert processed.torque_Nm[0] == pytest.approx(0.5)
        assert processed.torque_Nm[1] == pytest.approx(1.0)
        assert processed.torque_Nm[2] == pytest.approx(1.5)

    def test_preserves_sample_metadata(self) -> None:
        engine = ProcessingEngine(make_calibration())
        sample = make_sample(
            t_monotonic_ns=123456789,
            rdt_sequence=42,
            ft_sequence=100,
            status=5,
        )

        processed = engine.process_sample(sample)

        assert processed.t_monotonic_ns == 123456789
        assert processed.rdt_sequence == 42
        assert processed.ft_sequence == 100
        assert processed.status == 5


class TestProcessingEngineSoftZero:
    """Tests for soft zero offset application."""

    def test_soft_zero_subtracts_force_offsets(self) -> None:
        calibration = make_calibration(cpf=1000.0, cpt=1000.0)
        engine = ProcessingEngine(calibration)
        engine.set_soft_zero(SoftZeroOffsets(
            force_counts=(100, 200, 300),
            torque_counts=(0, 0, 0),
        ))
        sample = make_sample(counts=(1100, 1200, 1300, 0, 0, 0))

        processed = engine.process_sample(sample)

        # After offset: (1000, 1000, 1000) / 1000 = (1.0, 1.0, 1.0)
        assert processed.force_N is not None
        assert processed.force_N[0] == pytest.approx(1.0)
        assert processed.force_N[1] == pytest.approx(1.0)
        assert processed.force_N[2] == pytest.approx(1.0)

    def test_soft_zero_subtracts_torque_offsets(self) -> None:
        calibration = make_calibration(cpf=1000.0, cpt=1000.0)
        engine = ProcessingEngine(calibration)
        engine.set_soft_zero(SoftZeroOffsets(
            force_counts=(0, 0, 0),
            torque_counts=(500, 600, 700),
        ))
        sample = make_sample(counts=(0, 0, 0, 1500, 1600, 1700))

        processed = engine.process_sample(sample)

        # After offset: (1000, 1000, 1000) / 1000 = (1.0, 1.0, 1.0)
        assert processed.torque_Nm is not None
        assert processed.torque_Nm[0] == pytest.approx(1.0)
        assert processed.torque_Nm[1] == pytest.approx(1.0)
        assert processed.torque_Nm[2] == pytest.approx(1.0)

    def test_soft_zero_updates_counts_in_output(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.set_soft_zero(SoftZeroOffsets(
            force_counts=(100, 100, 100),
            torque_counts=(200, 200, 200),
        ))
        sample = make_sample(counts=(500, 600, 700, 800, 900, 1000))

        processed = engine.process_sample(sample)

        # Counts should be adjusted
        assert processed.counts == (400, 500, 600, 600, 700, 800)

    def test_no_soft_zero_when_none(self) -> None:
        engine = ProcessingEngine(make_calibration(cpf=1000.0, cpt=1000.0))
        sample = make_sample(counts=(1000, 2000, 3000, 4000, 5000, 6000))

        processed = engine.process_sample(sample)

        # Counts unchanged
        assert processed.counts == (1000, 2000, 3000, 4000, 5000, 6000)
        assert processed.force_N == pytest.approx((1.0, 2.0, 3.0))

    def test_capture_soft_zero_from_sample(self) -> None:
        engine = ProcessingEngine(make_calibration())
        sample = make_sample(counts=(100, 200, 300, 400, 500, 600))

        offsets = engine.capture_soft_zero(sample)

        assert engine.soft_zero == offsets
        assert offsets.force_counts == (100, 200, 300)
        assert offsets.torque_counts == (400, 500, 600)

    def test_clear_soft_zero(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.set_soft_zero(SoftZeroOffsets.zero())
        assert engine.soft_zero is not None

        engine.clear_soft_zero()

        assert engine.soft_zero is None


class TestProcessingEngineThreading:
    """Tests for processing engine thread model."""

    def test_start_sets_running(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.start()
        assert engine.is_running is True
        engine.stop()

    def test_stop_clears_running(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.start()
        engine.stop()
        assert engine.is_running is False

    def test_start_twice_raises(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.start()
        with pytest.raises(RuntimeError, match="already running"):
            engine.start()
        engine.stop()

    def test_stop_when_not_running_is_safe(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.stop()  # Should not raise
        assert engine.is_running is False

    def test_context_manager(self) -> None:
        calibration = make_calibration()
        with ProcessingEngine(calibration) as engine:
            engine.start()
            assert engine.is_running
        assert engine.is_running is False


class TestProcessingEngineRouting:
    """Tests for sample routing to visualization and logger."""

    def test_submit_sample_queues_for_processing(self) -> None:
        engine = ProcessingEngine(make_calibration())
        sample = make_sample()

        result = engine.submit_sample(sample)

        assert result is True
        assert engine.input_queue.qsize() == 1

    def test_submit_sample_returns_false_when_queue_full(self) -> None:
        engine = ProcessingEngine(make_calibration(), input_queue_size=1)
        engine.submit_sample(make_sample())

        result = engine.submit_sample(make_sample())

        assert result is False
        stats = engine.statistics()
        assert stats["samples_dropped_input"] == 1

    def test_processed_samples_sent_to_logger_queue(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.start()
        sample = make_sample()
        engine.submit_sample(sample)

        # Wait for processing
        time.sleep(0.2)
        engine.stop()

        assert engine.logger_queue.qsize() == 1
        processed = engine.logger_queue.get_nowait()
        assert processed.force_N is not None

    def test_visualization_callback_invoked(self) -> None:
        received: list[SampleRecord] = []

        def callback(sample: SampleRecord) -> None:
            received.append(sample)

        engine = ProcessingEngine(make_calibration())
        engine.set_visualization_callback(callback)
        engine.start()
        engine.submit_sample(make_sample())

        time.sleep(0.2)
        engine.stop()

        assert len(received) == 1
        assert received[0].force_N is not None

    def test_statistics_tracks_processed_samples(self) -> None:
        engine = ProcessingEngine(make_calibration())
        engine.start()

        for i in range(5):
            engine.submit_sample(make_sample(rdt_sequence=i))

        time.sleep(0.2)
        engine.stop()

        stats = engine.statistics()
        assert stats["samples_processed"] == 5

    def test_logger_queue_full_tracks_dropped(self) -> None:
        engine = ProcessingEngine(make_calibration(), output_queue_size=1)
        engine.start()

        # Submit more samples than logger queue can hold
        for i in range(10):
            engine.submit_sample(make_sample(rdt_sequence=i))

        time.sleep(0.3)
        engine.stop()

        stats = engine.statistics()
        # At least some should be dropped
        assert stats["samples_dropped_logger"] >= 1

    def test_set_calibration_updates_conversion(self) -> None:
        engine = ProcessingEngine(make_calibration(cpf=1000.0, cpt=1000.0))
        sample = make_sample(counts=(1000, 0, 0, 0, 0, 0))

        # Initial: 1000 / 1000 = 1.0 N
        processed1 = engine.process_sample(sample)
        assert processed1.force_N[0] == pytest.approx(1.0)

        # Update calibration: 1000 / 500 = 2.0 N
        engine.set_calibration(make_calibration(cpf=500.0, cpt=500.0))
        processed2 = engine.process_sample(sample)
        assert processed2.force_N[0] == pytest.approx(2.0)


class TestProcessingEngineThreadSafety:
    """Tests for thread safety of ProcessingEngine."""

    def test_concurrent_submit_and_process(self) -> None:
        engine = ProcessingEngine(make_calibration())
        received: list[SampleRecord] = []
        lock = threading.Lock()

        def callback(sample: SampleRecord) -> None:
            with lock:
                received.append(sample)

        engine.set_visualization_callback(callback)
        engine.start()

        # Submit samples from multiple threads
        def submit_samples(start: int, count: int) -> None:
            for i in range(count):
                engine.submit_sample(make_sample(rdt_sequence=start + i))

        threads = [
            threading.Thread(target=submit_samples, args=(i * 100, 100))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Wait for processing
        time.sleep(0.5)
        engine.stop()

        # All samples should be processed
        assert len(received) == 400

    def test_soft_zero_change_during_processing(self) -> None:
        engine = ProcessingEngine(make_calibration(cpf=1000.0, cpt=1000.0))
        engine.start()

        # Submit samples while changing soft zero
        for i in range(100):
            engine.submit_sample(make_sample(counts=(1000, 1000, 1000, 1000, 1000, 1000)))
            if i == 50:
                engine.set_soft_zero(SoftZeroOffsets(
                    force_counts=(500, 500, 500),
                    torque_counts=(500, 500, 500),
                ))

        time.sleep(0.3)
        engine.stop()

        # Should complete without errors
        stats = engine.statistics()
        assert stats["samples_processed"] == 100
