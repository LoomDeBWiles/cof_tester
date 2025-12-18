"""Tests for acquisition engine and ring buffer."""

import itertools
import socket
import struct
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from gsdv.acquisition import (
    AcquisitionEngine,
    AcquisitionState,
    AcquisitionStats,
    RingBuffer,
    RingBufferStats,
)
from gsdv.protocols.rdt_udp import RESPONSE_FORMAT


class TestRingBufferStats:
    """Tests for RingBufferStats dataclass."""

    def test_fill_ratio_empty(self) -> None:
        stats = RingBufferStats(capacity=100, size=0, total_written=0, overwrites=0)
        assert stats.fill_ratio == 0.0

    def test_fill_ratio_half_full(self) -> None:
        stats = RingBufferStats(capacity=100, size=50, total_written=50, overwrites=0)
        assert stats.fill_ratio == 0.5

    def test_fill_ratio_full(self) -> None:
        stats = RingBufferStats(capacity=100, size=100, total_written=100, overwrites=0)
        assert stats.fill_ratio == 1.0

    def test_fill_ratio_zero_capacity(self) -> None:
        stats = RingBufferStats(capacity=0, size=0, total_written=0, overwrites=0)
        assert stats.fill_ratio == 0.0

    def test_is_full_false(self) -> None:
        stats = RingBufferStats(capacity=100, size=50, total_written=50, overwrites=0)
        assert stats.is_full is False

    def test_is_full_true(self) -> None:
        stats = RingBufferStats(capacity=100, size=100, total_written=100, overwrites=0)
        assert stats.is_full is True


class TestRingBufferInit:
    """Tests for RingBuffer initialization."""

    def test_capacity_stored(self) -> None:
        buffer = RingBuffer(capacity=1000)
        assert buffer.capacity == 1000

    def test_default_60_seconds_at_1000hz(self) -> None:
        buffer = RingBuffer(capacity=60_000)
        assert buffer.capacity == 60_000

    def test_rejects_zero_capacity(self) -> None:
        with pytest.raises(ValueError, match="capacity must be positive"):
            RingBuffer(capacity=0)

    def test_rejects_negative_capacity(self) -> None:
        with pytest.raises(ValueError, match="capacity must be positive"):
            RingBuffer(capacity=-1)

    def test_stats_initially_empty(self) -> None:
        buffer = RingBuffer(capacity=100)
        stats = buffer.stats()
        assert stats.size == 0
        assert stats.total_written == 0
        assert stats.overwrites == 0


class TestRingBufferAppend:
    """Tests for RingBuffer.append()."""

    def test_append_increments_size(self) -> None:
        buffer = RingBuffer(capacity=100)
        buffer.append(
            t_monotonic_ns=1234567890,
            rdt_sequence=1,
            ft_sequence=100,
            status=0,
            counts=(10, 20, 30, 40, 50, 60),
        )
        assert buffer.stats().size == 1

    def test_append_increments_total_written(self) -> None:
        buffer = RingBuffer(capacity=100)
        buffer.append(
            t_monotonic_ns=1234567890,
            rdt_sequence=1,
            ft_sequence=100,
            status=0,
            counts=(10, 20, 30, 40, 50, 60),
        )
        assert buffer.stats().total_written == 1

    def test_multiple_appends(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i * 1000000,
                rdt_sequence=i,
                ft_sequence=i * 10,
                status=0,
                counts=(i, i, i, i, i, i),
            )
        stats = buffer.stats()
        assert stats.size == 10
        assert stats.total_written == 10

    def test_overwrite_when_full(self) -> None:
        buffer = RingBuffer(capacity=5)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i * 1000000,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, i, i, i, i, i),
            )
        stats = buffer.stats()
        assert stats.size == 5
        assert stats.total_written == 10
        assert stats.overwrites == 5

    def test_fill_ratio_updates(self) -> None:
        buffer = RingBuffer(capacity=10)
        for i in range(5):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(0, 0, 0, 0, 0, 0),
            )
        assert buffer.stats().fill_ratio == 0.5


class TestRingBufferGetLatest:
    """Tests for RingBuffer.get_latest()."""

    def test_returns_none_when_empty(self) -> None:
        buffer = RingBuffer(capacity=100)
        assert buffer.get_latest(10) is None

    def test_returns_all_when_requesting_more_than_available(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(5):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, i, i, i, i, i),
            )
        data = buffer.get_latest(10)
        assert data is not None
        assert len(data["timestamps"]) == 5

    def test_returns_requested_count(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, i, i, i, i, i),
            )
        data = buffer.get_latest(5)
        assert data is not None
        assert len(data["timestamps"]) == 5

    def test_returns_most_recent(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i * 1000,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, i, i, i, i, i),
            )
        data = buffer.get_latest(3)
        assert data is not None
        # Should return samples 7, 8, 9
        np.testing.assert_array_equal(data["rdt_sequence"], [7, 8, 9])

    def test_chronological_order_before_wrap(self) -> None:
        buffer = RingBuffer(capacity=10)
        for i in range(5):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, 0, 0, 0, 0, 0),
            )
        data = buffer.get_latest(5)
        assert data is not None
        np.testing.assert_array_equal(data["rdt_sequence"], [0, 1, 2, 3, 4])

    def test_chronological_order_after_wrap(self) -> None:
        buffer = RingBuffer(capacity=5)
        for i in range(8):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, 0, 0, 0, 0, 0),
            )
        data = buffer.get_latest(5)
        assert data is not None
        # Should return samples 3, 4, 5, 6, 7 in order
        np.testing.assert_array_equal(data["rdt_sequence"], [3, 4, 5, 6, 7])

    def test_returns_copy_not_view(self) -> None:
        buffer = RingBuffer(capacity=10)
        buffer.append(
            t_monotonic_ns=1000,
            rdt_sequence=1,
            ft_sequence=1,
            status=0,
            counts=(1, 2, 3, 4, 5, 6),
        )
        data1 = buffer.get_latest(1)
        data2 = buffer.get_latest(1)
        assert data1 is not None and data2 is not None
        data1["timestamps"][0] = 9999
        assert data2["timestamps"][0] == 1000

    def test_counts_shape(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(5):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, i + 1, i + 2, i + 3, i + 4, i + 5),
            )
        data = buffer.get_latest(3)
        assert data is not None
        assert data["counts"].shape == (3, 6)


class TestRingBufferGetAll:
    """Tests for RingBuffer.get_all()."""

    def test_returns_none_when_empty(self) -> None:
        buffer = RingBuffer(capacity=100)
        assert buffer.get_all() is None

    def test_returns_all_data(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, 0, 0, 0, 0, 0),
            )
        data = buffer.get_all()
        assert data is not None
        assert len(data["timestamps"]) == 10


class TestRingBufferClear:
    """Tests for RingBuffer.clear()."""

    def test_clear_resets_size(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(0, 0, 0, 0, 0, 0),
            )
        buffer.clear()
        assert buffer.stats().size == 0

    def test_clear_resets_total_written(self) -> None:
        buffer = RingBuffer(capacity=100)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(0, 0, 0, 0, 0, 0),
            )
        buffer.clear()
        assert buffer.stats().total_written == 0

    def test_clear_resets_overwrites(self) -> None:
        buffer = RingBuffer(capacity=5)
        for i in range(10):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(0, 0, 0, 0, 0, 0),
            )
        buffer.clear()
        assert buffer.stats().overwrites == 0

    def test_get_latest_returns_none_after_clear(self) -> None:
        buffer = RingBuffer(capacity=100)
        buffer.append(
            t_monotonic_ns=1,
            rdt_sequence=1,
            ft_sequence=1,
            status=0,
            counts=(0, 0, 0, 0, 0, 0),
        )
        buffer.clear()
        assert buffer.get_latest(10) is None


class TestRingBufferThreadSafety:
    """Tests for RingBuffer thread safety."""

    def test_concurrent_appends(self) -> None:
        buffer = RingBuffer(capacity=10000)
        num_threads = 4
        appends_per_thread = 1000

        def append_samples(thread_id: int) -> None:
            for i in range(appends_per_thread):
                buffer.append(
                    t_monotonic_ns=thread_id * 1000000 + i,
                    rdt_sequence=thread_id * 1000 + i,
                    ft_sequence=i,
                    status=0,
                    counts=(thread_id, i, 0, 0, 0, 0),
                )

        threads = [
            threading.Thread(target=append_samples, args=(tid,))
            for tid in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = buffer.stats()
        assert stats.total_written == num_threads * appends_per_thread

    def test_concurrent_read_write(self) -> None:
        buffer = RingBuffer(capacity=1000)
        stop_event = threading.Event()
        read_count = [0]

        def writer() -> None:
            i = 0
            while not stop_event.is_set():
                buffer.append(
                    t_monotonic_ns=i,
                    rdt_sequence=i,
                    ft_sequence=i,
                    status=0,
                    counts=(i, 0, 0, 0, 0, 0),
                )
                i += 1

        def reader() -> None:
            while not stop_event.is_set():
                buffer.get_latest(10)
                read_count[0] += 1

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        reader_thread.start()

        time.sleep(0.1)  # Let them run briefly
        stop_event.set()

        writer_thread.join()
        reader_thread.join()

        # Should complete without deadlock or corruption
        assert read_count[0] > 0
        assert buffer.stats().total_written > 0


class TestAcquisitionStats:
    """Tests for AcquisitionStats dataclass."""

    def test_loss_ratio_no_packets(self) -> None:
        buffer_stats = RingBufferStats(capacity=100, size=0, total_written=0, overwrites=0)
        stats = AcquisitionStats(
            state=AcquisitionState.STOPPED,
            buffer_stats=buffer_stats,
            packets_received=0,
            packets_lost=0,
            receive_errors=0,
            samples_per_second=0.0,
        )
        assert stats.loss_ratio == 0.0

    def test_loss_ratio_no_loss(self) -> None:
        buffer_stats = RingBufferStats(capacity=100, size=100, total_written=100, overwrites=0)
        stats = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=100,
            packets_lost=0,
            receive_errors=0,
            samples_per_second=1000.0,
        )
        assert stats.loss_ratio == 0.0

    def test_loss_ratio_with_loss(self) -> None:
        buffer_stats = RingBufferStats(capacity=100, size=90, total_written=90, overwrites=0)
        stats = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=90,
            packets_lost=10,
            receive_errors=0,
            samples_per_second=900.0,
        )
        assert stats.loss_ratio == 0.1


class TestAcquisitionEngineInit:
    """Tests for AcquisitionEngine initialization."""

    def test_stores_ip(self) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100")
        assert engine.ip == "192.168.1.100"

    def test_default_port(self) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100")
        assert engine.port == 49152

    def test_custom_port(self) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100", port=12345)
        assert engine.port == 12345

    def test_default_buffer_capacity(self) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100")
        assert engine.buffer.capacity == 60_000

    def test_custom_buffer_capacity(self) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100", buffer_capacity=1000)
        assert engine.buffer.capacity == 1000

    def test_initial_state_stopped(self) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100")
        assert engine.state == AcquisitionState.STOPPED

    def test_is_running_initially_false(self) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100")
        assert engine.is_running is False


class TestAcquisitionEngineWithMockedSocket:
    """Tests for AcquisitionEngine with mocked socket."""

    def _build_response(
        self,
        rdt_seq: int = 0,
        ft_seq: int = 0,
        status: int = 0,
        fx: int = 0,
        fy: int = 0,
        fz: int = 0,
        tx: int = 0,
        ty: int = 0,
        tz: int = 0,
    ) -> bytes:
        """Build a test response packet."""
        return struct.pack(
            RESPONSE_FORMAT,
            rdt_seq,
            ft_seq,
            status,
            fx,
            fy,
            fz,
            tx,
            ty,
            tz,
        )

    @patch("socket.socket")
    def test_start_changes_state_to_running(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout()

        engine = AcquisitionEngine(ip="192.168.1.100")
        engine.start()

        assert engine.state == AcquisitionState.RUNNING
        engine.stop()

    @patch("socket.socket")
    def test_stop_changes_state_to_stopped(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout()

        engine = AcquisitionEngine(ip="192.168.1.100")
        engine.start()
        engine.stop()

        assert engine.state == AcquisitionState.STOPPED

    @patch("socket.socket")
    def test_start_twice_raises_error(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout()

        engine = AcquisitionEngine(ip="192.168.1.100")
        engine.start()

        with pytest.raises(RuntimeError, match="already running"):
            engine.start()

        engine.stop()

    @patch("socket.socket")
    def test_stop_when_not_running_is_safe(self, mock_socket_class: MagicMock) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100")
        engine.stop()  # Should not raise
        assert engine.state == AcquisitionState.STOPPED

    @patch("socket.socket")
    def test_receives_samples_into_buffer(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        responses = [
            (self._build_response(rdt_seq=i, fx=i * 10), ("192.168.1.100", 49152))
            for i in range(5)
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(
            responses, itertools.repeat(socket.timeout())
        )

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.1)  # Let receive thread process
        engine.stop()

        stats = engine.stats()
        assert stats.packets_received == 5
        assert stats.buffer_stats.size == 5

    @patch("socket.socket")
    def test_tracks_packet_loss(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Sequence with gap: 0, 5 (lost 1,2,3,4)
        responses = [
            (self._build_response(rdt_seq=0), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=5), ("192.168.1.100", 49152)),
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(
            responses, itertools.repeat(socket.timeout())
        )

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.1)
        engine.stop()

        stats = engine.stats()
        assert stats.packets_lost == 4

    @patch("socket.socket")
    def test_context_manager(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout()

        with AcquisitionEngine(ip="192.168.1.100") as engine:
            engine.start()
            assert engine.is_running

        assert engine.state == AcquisitionState.STOPPED

    @patch("socket.socket")
    def test_get_latest_returns_buffer_data(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        responses = [
            (self._build_response(rdt_seq=i, fx=i * 100, fy=i * 200, fz=i * 300), ("192.168.1.100", 49152))
            for i in range(10)
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(
            responses, itertools.repeat(socket.timeout())
        )

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.1)
        engine.stop()

        data = engine.get_latest(5)
        assert data is not None
        assert len(data["timestamps"]) == 5
        # Most recent 5 samples: 5,6,7,8,9
        np.testing.assert_array_equal(data["rdt_sequence"], [5, 6, 7, 8, 9])

    @patch("socket.socket")
    def test_sample_callback_invoked(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        responses = [
            (self._build_response(rdt_seq=i), ("192.168.1.100", 49152))
            for i in range(5)
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(
            responses, itertools.repeat(socket.timeout())
        )

        received_samples: list = []

        def callback(sample):
            received_samples.append(sample)

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.set_sample_callback(callback)
        engine.start()
        time.sleep(0.2)  # Extra time for callback thread
        engine.stop()

        assert len(received_samples) == 5

    @patch("socket.socket")
    def test_reset_clears_error_state(self, mock_socket_class: MagicMock) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100")
        # Manually set error state (simulating internal error)
        engine._state = AcquisitionState.ERROR
        engine.reset()
        assert engine.state == AcquisitionState.STOPPED

    @patch("socket.socket")
    def test_reset_while_running_raises(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout()

        engine = AcquisitionEngine(ip="192.168.1.100")
        engine.start()

        with pytest.raises(RuntimeError, match="Cannot reset while running"):
            engine.reset()

        engine.stop()

    @patch("socket.socket")
    def test_start_clears_buffer(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock
        mock_sock.recvfrom.side_effect = socket.timeout()

        engine = AcquisitionEngine(ip="192.168.1.100")

        # Manually add data to buffer
        engine.buffer.append(
            t_monotonic_ns=1,
            rdt_sequence=1,
            ft_sequence=1,
            status=0,
            counts=(0, 0, 0, 0, 0, 0),
        )
        assert engine.buffer.stats().size == 1

        engine.start()
        assert engine.buffer.stats().size == 0

        engine.stop()

    @patch("socket.socket")
    def test_stats_includes_buffer_stats(self, mock_socket_class: MagicMock) -> None:
        engine = AcquisitionEngine(ip="192.168.1.100", buffer_capacity=5000)
        stats = engine.stats()
        assert stats.buffer_stats.capacity == 5000

    @patch("socket.socket")
    def test_receive_errors_tracked(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Alternate between OSError and timeout
        errors = [
            OSError("Network error"),
            socket.timeout(),
            OSError("Another error"),
            socket.timeout(),
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(
            errors, itertools.repeat(socket.timeout())
        )

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.15)
        engine.stop()

        stats = engine.stats()
        assert stats.receive_errors >= 1
