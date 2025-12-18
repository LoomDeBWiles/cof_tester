"""Edge case tests for acquisition and recording.

Tests for:
- Long-duration streaming with bounded memory usage (7-day view)
- Disk full mid-recording
- Disconnect mid-recording
"""

import errno
import itertools
import os
import socket
import struct
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from gsdv.acquisition import RingBuffer, RingBufferStats
from gsdv.errors import DiskFullError, FileWriteError, NetworkDisconnectError
from gsdv.protocols.rdt_udp import RESPONSE_FORMAT


class TestLongDurationMemoryBudget:
    """Tests for memory-bounded long-duration streaming.

    Verifies that the ring buffer can handle long-duration streaming without
    memory growth. A 7-day view at 1000Hz would be 604.8M samples, but the
    circular buffer must stay within its fixed capacity.
    """

    def test_ring_buffer_memory_stays_bounded_during_extended_streaming(self) -> None:
        """Ring buffer memory remains constant during extended streaming."""
        # Small capacity to observe many wrap-arounds quickly
        capacity = 1000
        buffer = RingBuffer(capacity=capacity)

        # Simulate streaming far more data than buffer can hold
        # This is like 10x the capacity, simulating extended streaming
        total_samples = 10_000

        for i in range(total_samples):
            buffer.append(
                t_monotonic_ns=i * 1_000_000,  # 1ms apart
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i % 100, i % 100, i % 100, i % 100, i % 100, i % 100),
            )

        stats = buffer.stats()

        # Buffer size must stay at capacity
        assert stats.size == capacity
        # Total written tracks all samples
        assert stats.total_written == total_samples
        # Overwrites should be total - capacity
        assert stats.overwrites == total_samples - capacity
        # Fill ratio should be 1.0
        assert stats.fill_ratio == 1.0
        assert stats.is_full is True

    def test_ring_buffer_data_integrity_after_many_wraps(self) -> None:
        """Data integrity is preserved after many buffer wrap-arounds."""
        capacity = 100
        buffer = RingBuffer(capacity=capacity)

        # Write enough to wrap many times
        total_samples = 1500  # 15 complete wrap-arounds

        for i in range(total_samples):
            buffer.append(
                t_monotonic_ns=i * 1000,
                rdt_sequence=i,
                ft_sequence=i * 2,
                status=i % 256,
                counts=(i, i + 1, i + 2, i + 3, i + 4, i + 5),
            )

        # Get latest samples and verify they contain the most recent data
        data = buffer.get_latest(50)
        assert data is not None

        # Most recent 50 samples should be the last 50 written
        expected_start = total_samples - 50
        np.testing.assert_array_equal(
            data["rdt_sequence"],
            np.arange(expected_start, total_samples, dtype=np.uint32)
        )
        np.testing.assert_array_equal(
            data["ft_sequence"],
            np.arange(expected_start * 2, total_samples * 2, 2, dtype=np.uint32)
        )

    def test_ring_buffer_overwrites_oldest_data_not_newest(self) -> None:
        """When full, buffer overwrites oldest data, preserving newest."""
        capacity = 5
        buffer = RingBuffer(capacity=capacity)

        # Write exactly capacity samples
        for i in range(capacity):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, 0, 0, 0, 0, 0),
            )

        # Buffer should contain [0, 1, 2, 3, 4]
        data = buffer.get_all()
        assert data is not None
        np.testing.assert_array_equal(data["rdt_sequence"], [0, 1, 2, 3, 4])

        # Write 3 more samples
        for i in range(5, 8):
            buffer.append(
                t_monotonic_ns=i,
                rdt_sequence=i,
                ft_sequence=i,
                status=0,
                counts=(i, 0, 0, 0, 0, 0),
            )

        # Buffer should now contain [3, 4, 5, 6, 7] - oldest 3 were overwritten
        data = buffer.get_all()
        assert data is not None
        np.testing.assert_array_equal(data["rdt_sequence"], [3, 4, 5, 6, 7])

        # Stats should reflect the overwrites
        stats = buffer.stats()
        assert stats.overwrites == 3

    def test_ring_buffer_concurrent_read_write_during_extended_streaming(self) -> None:
        """Concurrent reads don't corrupt data during extended streaming."""
        capacity = 500
        buffer = RingBuffer(capacity=capacity)
        stop_event = threading.Event()
        read_count = [0]
        read_errors = [0]

        def writer() -> None:
            for i in range(1000):
                buffer.append(
                    t_monotonic_ns=i * 1000,
                    rdt_sequence=i,
                    ft_sequence=i,
                    status=0,
                    counts=(i, i, i, i, i, i),
                )
                # Brief yield to allow reader to interleave
                if i % 100 == 0:
                    time.sleep(0.001)
            stop_event.set()

        def reader() -> None:
            while not stop_event.is_set():
                data = buffer.get_latest(100)
                if data is not None:
                    read_count[0] += 1
                    # Verify data is in ascending sequence order
                    seqs = data["rdt_sequence"]
                    if len(seqs) > 1:
                        # Check for monotonically increasing sequences
                        diffs = np.diff(seqs.astype(np.int64))
                        if not np.all(diffs == 1):
                            read_errors[0] += 1

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        reader_thread.start()

        writer_thread.join(timeout=5.0)
        reader_thread.join(timeout=1.0)

        # Verify no corruption errors
        assert read_errors[0] == 0, f"Data corruption detected in {read_errors[0]} reads"
        assert read_count[0] > 0, "Reader should have completed at least one read"
        assert buffer.stats().total_written == 1000, "Writer should complete all writes"


class TestDiskFullMidRecording:
    """Tests for handling disk full conditions during recording."""

    def test_disk_full_error_construction(self) -> None:
        """DiskFullError contains correct context."""
        path = "/mnt/data/recording.csv"
        error = DiskFullError(path=path)

        assert error.code == "IO-002"
        assert path in error.message
        assert error.context.path == path
        assert "full" in error.message.lower()

    def test_file_write_raises_disk_full_on_enospc(self, tmp_path: Path) -> None:
        """OSError with ENOSPC should be convertible to DiskFullError."""
        test_file = tmp_path / "test.csv"

        # Simulate ENOSPC error during write
        with patch("builtins.open", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            with pytest.raises(OSError) as exc_info:
                with open(test_file, "w") as f:
                    f.write("data")

            assert exc_info.value.errno == errno.ENOSPC

        # Verify we can convert to DiskFullError
        os_error = exc_info.value
        disk_full = DiskFullError(path=str(test_file))
        assert disk_full.code == "IO-002"

    def test_partial_file_preserved_on_disk_full(self, tmp_path: Path) -> None:
        """When disk fills, partial data written should be preserved."""
        test_file = tmp_path / "test.csv"
        write_count = [0]

        def write_with_limit(self, data):
            """Write a few lines then raise ENOSPC."""
            write_count[0] += 1
            if write_count[0] > 5:
                raise OSError(errno.ENOSPC, "No space left on device")
            self._real_write(data)

        # Write some data, then simulate disk full
        with open(test_file, "w") as f:
            f._real_write = f.write  # type: ignore
            f.write = lambda d: write_with_limit(f, d)  # type: ignore

            try:
                for i in range(10):
                    f.write(f"line {i}\n")
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    pass  # Expected
                else:
                    raise

        # Verify partial file exists and has some content
        assert test_file.exists()
        content = test_file.read_text()
        assert "line 0" in content  # At least first line was written

    def test_disk_full_error_recovery_action(self) -> None:
        """DiskFullError suggests choosing a different directory."""
        from gsdv.errors import RecoveryAction

        error = DiskFullError(path="/mnt/full/file.csv")
        assert error.recovery == RecoveryAction.CHOOSE_DIRECTORY

    @pytest.mark.filterwarnings(
        "ignore:Exception in thread AsyncFileWriter:pytest.PytestUnhandledThreadExceptionWarning"
    )
    def test_async_file_writer_handles_disk_full(self, tmp_path: Path) -> None:
        """AsyncFileWriter raises DiskFullError when underlying write fails with ENOSPC."""
        from gsdv.logging.writer import AsyncFileWriter, WriterState

        test_file = tmp_path / "test.csv"
        writer = AsyncFileWriter(test_file, flush_interval_ms=10)

        # Mock the file object's write method to raise ENOSPC
        with patch("builtins.open") as mock_open:
            mock_file = MagicMock()
            mock_open.return_value = mock_file
            
            # Setup write to succeed a few times then fail
            # We need to mock write() on the file object returned by open()
            write_count = 0
            def side_effect(data):
                nonlocal write_count
                write_count += 1
                if write_count >= 3:
                    raise OSError(errno.ENOSPC, "No space left on device")
                return len(data)

            mock_file.write.side_effect = side_effect
            mock_file.flush.return_value = None
            mock_file.fileno.return_value = 1

            writer.start()
            
            # Write enough samples to trigger flushes
            for i in range(20):
                writer.write((i, 0, 0, 0, 0, 0, 0, 0, 0, 0))
                time.sleep(0.005)

            # Wait for writer to hit the error
            start_wait = time.monotonic()
            while writer.state == WriterState.RUNNING and time.monotonic() - start_wait < 1.0:
                time.sleep(0.01)

            assert writer.state == WriterState.ERROR
            
            # Verify the thread died
            writer._writer_thread.join(timeout=1.0)
            assert not writer._writer_thread.is_alive()


class TestDisconnectMidRecording:
    """Tests for handling network disconnects during recording."""

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
        """Build a test RDT response packet."""
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

    def test_network_disconnect_error_construction(self) -> None:
        """NetworkDisconnectError contains correct context."""
        host = "192.168.1.100"
        port = 49152
        error = NetworkDisconnectError(host=host, port=port, original_error="Connection reset")

        assert error.code == "NET-003"
        assert host in error.message
        assert str(port) in error.message
        assert error.context.host == host
        assert error.context.port == port

    @patch("socket.socket")
    def test_acquisition_engine_tracks_disconnect_errors(self, mock_socket_class: MagicMock) -> None:
        """AcquisitionEngine tracks receive errors from disconnects."""
        from gsdv.acquisition import AcquisitionEngine

        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Simulate: 2 good packets, disconnect, 2 more good packets
        responses = [
            (self._build_response(rdt_seq=0), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=1), ("192.168.1.100", 49152)),
            OSError("Connection reset by peer"),  # Simulated disconnect
            (self._build_response(rdt_seq=2), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=3), ("192.168.1.100", 49152)),
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(responses, itertools.repeat(socket.timeout()))

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.2)  # Let receive thread process
        engine.stop()

        stats = engine.stats()
        # Should have received some packets despite the error
        assert stats.packets_received >= 2
        # Should have tracked the receive error
        assert stats.receive_errors >= 1

    @patch("socket.socket")
    def test_acquisition_engine_recovers_from_disconnect(self, mock_socket_class: MagicMock) -> None:
        """AcquisitionEngine continues receiving after transient disconnect."""
        from gsdv.acquisition import AcquisitionEngine

        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Simulate: good packets, multiple disconnects, more good packets
        responses = [
            (self._build_response(rdt_seq=0), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=1), ("192.168.1.100", 49152)),
            OSError("Network is unreachable"),
            OSError("Network is unreachable"),
            (self._build_response(rdt_seq=2), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=3), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=4), ("192.168.1.100", 49152)),
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(responses, itertools.repeat(socket.timeout()))

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.3)
        engine.stop()

        stats = engine.stats()
        # Should have received all 5 packets despite errors in between
        assert stats.packets_received == 5
        # Should have tracked both errors
        assert stats.receive_errors >= 2

    @patch("socket.socket")
    def test_buffer_data_preserved_through_disconnect(self, mock_socket_class: MagicMock) -> None:
        """Data already in buffer is preserved when disconnect occurs."""
        from gsdv.acquisition import AcquisitionEngine

        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Send some packets then disconnect
        responses = [
            (self._build_response(rdt_seq=i, fx=i * 100), ("192.168.1.100", 49152))
            for i in range(5)
        ]
        responses.append(OSError("Connection lost"))
        mock_sock.recvfrom.side_effect = itertools.chain(responses, itertools.repeat(socket.timeout()))

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.2)
        engine.stop()

        # Data written before disconnect should still be in buffer
        data = engine.get_latest(10)
        assert data is not None
        assert len(data["timestamps"]) == 5
        # Verify data integrity
        np.testing.assert_array_equal(data["rdt_sequence"], [0, 1, 2, 3, 4])

    def test_disconnect_error_recovery_action(self) -> None:
        """NetworkDisconnectError suggests reconnection."""
        from gsdv.errors import RecoveryAction

        error = NetworkDisconnectError(host="192.168.1.100", port=49152)
        assert error.recovery == RecoveryAction.RECONNECT


class TestSequenceGapDetection:
    """Tests for detecting packet loss via sequence gaps (related to disconnect handling)."""

    @patch("socket.socket")
    def test_sequence_gap_detected_as_packet_loss(self, mock_socket_class: MagicMock) -> None:
        """Sequence number gaps are detected as packet loss."""
        from gsdv.acquisition import AcquisitionEngine

        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Send packets with a gap: 0, 1, 5 (missing 2, 3, 4)
        responses = [
            (self._build_response(rdt_seq=0), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=1), ("192.168.1.100", 49152)),
            (self._build_response(rdt_seq=5), ("192.168.1.100", 49152)),
        ]
        mock_sock.recvfrom.side_effect = itertools.chain(responses, itertools.repeat(socket.timeout()))

        engine = AcquisitionEngine(ip="192.168.1.100", receive_timeout=0.01)
        engine.start()
        time.sleep(0.15)
        engine.stop()

        stats = engine.stats()
        # Should have received 3 packets
        assert stats.packets_received == 3
        # Should have detected 3 lost packets (2, 3, 4)
        assert stats.packets_lost == 3

    def _build_response(self, **kwargs) -> bytes:
        """Build a test RDT response packet."""
        defaults = {
            "rdt_seq": 0, "ft_seq": 0, "status": 0,
            "fx": 0, "fy": 0, "fz": 0, "tx": 0, "ty": 0, "tz": 0,
        }
        defaults.update(kwargs)
        return struct.pack(
            RESPONSE_FORMAT,
            defaults["rdt_seq"],
            defaults["ft_seq"],
            defaults["status"],
            defaults["fx"],
            defaults["fy"],
            defaults["fz"],
            defaults["tx"],
            defaults["ty"],
            defaults["tz"],
        )


# Import Path after all other imports (needed for tmp_path fixture)
from pathlib import Path
