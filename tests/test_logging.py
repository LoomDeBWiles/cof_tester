"""Tests for data logging and file export."""

import gc
import threading
import time
import tracemalloc
from pathlib import Path

import pytest

from gsdv.logging.writer import (
    AsyncFileWriter,
    WriterState,
    WriterStats,
    default_csv_formatter,
)
from gsdv.logging.formats import (
    FORMAT_CSV,
    FORMAT_TSV,
    FORMAT_EXCEL,
    BOM_UTF8,
    csv_formatter,
    tsv_formatter,
    excel_formatter,
    get_column_headers,
    get_metadata_header,
)
from gsdv.models import SampleRecord, CalibrationInfo


class TestWriterStats:
    """Tests for WriterStats dataclass."""

    def test_drop_ratio_no_samples(self) -> None:
        stats = WriterStats(
            state=WriterState.STOPPED,
            samples_written=0,
            samples_dropped=0,
            bytes_written=0,
            flushes=0,
            flush_latency_avg_ms=0.0,
            queue_size=0,
            queue_capacity=100,
        )
        assert stats.drop_ratio == 0.0

    def test_drop_ratio_no_drops(self) -> None:
        stats = WriterStats(
            state=WriterState.RUNNING,
            samples_written=100,
            samples_dropped=0,
            bytes_written=1000,
            flushes=10,
            flush_latency_avg_ms=1.0,
            queue_size=10,
            queue_capacity=100,
        )
        assert stats.drop_ratio == 0.0

    def test_drop_ratio_with_drops(self) -> None:
        stats = WriterStats(
            state=WriterState.RUNNING,
            samples_written=90,
            samples_dropped=10,
            bytes_written=900,
            flushes=9,
            flush_latency_avg_ms=1.0,
            queue_size=0,
            queue_capacity=100,
        )
        assert stats.drop_ratio == 0.1

    def test_queue_fill_ratio_empty(self) -> None:
        stats = WriterStats(
            state=WriterState.RUNNING,
            samples_written=0,
            samples_dropped=0,
            bytes_written=0,
            flushes=0,
            flush_latency_avg_ms=0.0,
            queue_size=0,
            queue_capacity=100,
        )
        assert stats.queue_fill_ratio == 0.0

    def test_queue_fill_ratio_half_full(self) -> None:
        stats = WriterStats(
            state=WriterState.RUNNING,
            samples_written=0,
            samples_dropped=0,
            bytes_written=0,
            flushes=0,
            flush_latency_avg_ms=0.0,
            queue_size=50,
            queue_capacity=100,
        )
        assert stats.queue_fill_ratio == 0.5

    def test_queue_fill_ratio_zero_capacity(self) -> None:
        stats = WriterStats(
            state=WriterState.STOPPED,
            samples_written=0,
            samples_dropped=0,
            bytes_written=0,
            flushes=0,
            flush_latency_avg_ms=0.0,
            queue_size=0,
            queue_capacity=0,
        )
        assert stats.queue_fill_ratio == 0.0


class TestDefaultCsvFormatter:
    """Tests for default_csv_formatter function."""

    def test_formats_tuple_as_csv(self) -> None:
        sample = (1234567890, 1, 100, 0, 10, 20, 30, 40, 50, 60)
        result = default_csv_formatter(sample)
        assert result == "1234567890,1,100,0,10,20,30,40,50,60"

    def test_handles_negative_values(self) -> None:
        sample = (0, 0, 0, 0, -100, -200, -300, 0, 0, 0)
        result = default_csv_formatter(sample)
        assert result == "0,0,0,0,-100,-200,-300,0,0,0"

    def test_handles_empty_tuple(self) -> None:
        sample = ()
        result = default_csv_formatter(sample)
        assert result == ""
    
    def test_handles_string(self) -> None:
        result = default_csv_formatter("test")
        assert result == "test"


class TestAsyncFileWriterInit:
    """Tests for AsyncFileWriter initialization."""

    def test_stores_path(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        writer = AsyncFileWriter(path)
        assert writer.path == path

    def test_default_state_stopped(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        assert writer.state == WriterState.STOPPED

    def test_is_running_initially_false(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        assert writer.is_running is False


class TestAsyncFileWriterStartStop:
    """Tests for AsyncFileWriter start/stop lifecycle."""

    def test_start_changes_state_to_running(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        writer.start()
        assert writer.state == WriterState.RUNNING
        writer.stop()

    def test_stop_changes_state_to_stopped(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        writer.start()
        writer.stop()
        assert writer.state == WriterState.STOPPED

    def test_start_twice_raises_error(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        writer.start()
        with pytest.raises(RuntimeError, match="already running"):
            writer.start()
        writer.stop()

    def test_stop_when_not_running_is_safe(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        writer.stop()
        assert writer.state == WriterState.STOPPED

    def test_context_manager(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        with AsyncFileWriter(path) as writer:
            assert writer.is_running
        assert writer.state == WriterState.STOPPED

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "test.csv"
        with AsyncFileWriter(path) as writer:
            writer.write((1, 2, 3))
        assert path.exists()


class TestAsyncFileWriterWrite:
    """Tests for AsyncFileWriter.write() method."""

    def test_write_returns_true_when_running(self, tmp_path: Path) -> None:
        with AsyncFileWriter(tmp_path / "test.csv") as writer:
            assert writer.write((1, 2, 3)) is True

    def test_write_returns_false_when_stopped(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        assert writer.write((1, 2, 3)) is False

    def test_write_drops_when_queue_full(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv", queue_capacity=10)
        writer.start()
        # Fill the queue beyond capacity
        for i in range(100):
            writer.write((i,))
        stats = writer.stats()
        assert stats.samples_dropped > 0
        writer.stop()

    def test_multiple_writes_all_saved(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        sample_count = 100
        with AsyncFileWriter(path) as writer:
            for i in range(sample_count):
                writer.write((i, i * 2, i * 3))
        # Verify file content
        lines = path.read_text().strip().split("\n")
        assert len(lines) == sample_count


class TestAsyncFileWriterOutput:
    """Tests for AsyncFileWriter file output."""

    def test_writes_header(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        header = "timestamp,rdt_seq,ft_seq,status,fx,fy,fz,tx,ty,tz"
        with AsyncFileWriter(path, header=header) as writer:
            writer.write((1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
        content = path.read_text()
        assert content.startswith(header + "\n")

    def test_header_without_newline_gets_newline(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        with AsyncFileWriter(path, header="col1,col2") as writer:
            writer.write((1, 2))
        content = path.read_text()
        lines = content.split("\n")
        assert lines[0] == "col1,col2"
        assert lines[1] == "1,2"

    def test_custom_formatter(self, tmp_path: Path) -> None:
        path = tmp_path / "test.tsv"

        def tsv_formatter(sample: tuple) -> str:
            return "\t".join(str(v) for v in sample)

        with AsyncFileWriter(path, formatter=tsv_formatter) as writer:
            writer.write((1, 2, 3))
        content = path.read_text().strip()
        assert content == "1\t2\t3"

    def test_data_persisted_after_stop(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        with AsyncFileWriter(path, flush_interval_ms=50) as writer:
            for i in range(50):
                writer.write((i,))
            time.sleep(0.1)  # Allow flush
        # File should exist and have data
        assert path.exists()
        content = path.read_text().strip()
        lines = content.split("\n")
        assert len(lines) == 50
    
    def test_custom_line_terminator(self, tmp_path: Path) -> None:
        path = tmp_path / "test.txt"
        with AsyncFileWriter(path, line_terminator="\r\n") as writer:
            writer.write((1, 2))
            writer.write((3, 4))
        
        with open(path, "rb") as f:
            content = f.read()
            assert b"\r\n" in content
            assert b"1,2\r\n3,4\r\n" == content


class TestAsyncFileWriterStats:
    """Tests for AsyncFileWriter statistics."""

    def test_initial_stats_zero(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        stats = writer.stats()
        assert stats.samples_written == 0
        assert stats.samples_dropped == 0
        assert stats.bytes_written == 0
        assert stats.flushes == 0

    def test_samples_written_tracked(self, tmp_path: Path) -> None:
        with AsyncFileWriter(tmp_path / "test.csv", flush_interval_ms=50) as writer:
            for i in range(100):
                writer.write((i,))
            time.sleep(0.2)  # Allow flushes
            stats = writer.stats()
            # Some samples should be written
            assert stats.samples_written > 0

    def test_bytes_written_tracked(self, tmp_path: Path) -> None:
        with AsyncFileWriter(tmp_path / "test.csv", flush_interval_ms=50) as writer:
            writer.write((12345, 67890))
            time.sleep(0.2)
            stats = writer.stats()
            assert stats.bytes_written > 0

    def test_flushes_counted(self, tmp_path: Path) -> None:
        with AsyncFileWriter(tmp_path / "test.csv", flush_interval_ms=50) as writer:
            for i in range(10):
                writer.write((i,))
            time.sleep(0.3)  # Allow multiple flushes
            stats = writer.stats()
            assert stats.flushes >= 1

    def test_queue_size_reported(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv", queue_capacity=1000)
        # Not started, queue should be empty
        stats = writer.stats()
        assert stats.queue_capacity == 1000


class TestAsyncFileWriterFlushInterval:
    """Tests for flush interval behavior."""

    def test_default_flush_interval_250ms(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv")
        assert writer._flush_interval_s == 0.25

    def test_custom_flush_interval(self, tmp_path: Path) -> None:
        writer = AsyncFileWriter(tmp_path / "test.csv", flush_interval_ms=100)
        assert writer._flush_interval_s == 0.1

    def test_data_flushed_at_interval(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        with AsyncFileWriter(path, flush_interval_ms=50) as writer:
            writer.write((1, 2, 3))
            time.sleep(0.15)  # Wait for flush
            stats = writer.stats()
            assert stats.flushes >= 1


class TestAsyncFileWriterThreadSafety:
    """Tests for AsyncFileWriter thread safety."""

    def test_concurrent_writes(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        num_threads = 4
        writes_per_thread = 250
        total_expected = num_threads * writes_per_thread

        with AsyncFileWriter(path, queue_capacity=total_expected * 2) as writer:

            def write_samples(thread_id: int) -> None:
                for i in range(writes_per_thread):
                    writer.write((thread_id, i))

            threads = [
                threading.Thread(target=write_samples, args=(tid,)) 
                for tid in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # Verify all data written
        lines = path.read_text().strip().split("\n")
        assert len(lines) == total_expected

    def test_concurrent_write_and_stats(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        stop_event = threading.Event()

        with AsyncFileWriter(path, flush_interval_ms=50) as writer:

            def write_loop() -> None:
                i = 0
                while not stop_event.is_set():
                    writer.write((i,))
                    i += 1

            def stats_loop() -> None:
                while not stop_event.is_set():
                    writer.stats()
                    time.sleep(0.01)

            write_thread = threading.Thread(target=write_loop)
            stats_thread = threading.Thread(target=stats_loop)

            write_thread.start()
            stats_thread.start()

            time.sleep(0.2)
            stop_event.set()

            write_thread.join()
            stats_thread.join()

        # Should complete without deadlock
        assert path.exists()


class TestAsyncFileWriter1000HzSustained:
    """Tests for sustained 1000Hz logging (Section 16.3 acceptance criteria)."""

    def test_sustains_1000hz_no_drops(self, tmp_path: Path) -> None:
        """Write 1000 samples/second for 2 seconds with zero drops.

        Section 16.3 requirement: Sustains 1000Hz logging, no dropped samples.
        """
        path = tmp_path / "test.csv"
        sample_count = 2000  # 2 seconds at 1000Hz
        samples_per_batch = 10  # Write in batches like real acquisition

        with AsyncFileWriter(
            path, queue_capacity=5000, flush_interval_ms=250
        ) as writer:
            start_time = time.perf_counter()

            for i in range(0, sample_count, samples_per_batch):
                # Write batch
                for j in range(samples_per_batch):
                    sample_idx = i + j
                    sample = (
                        sample_idx * 1_000_000,  # timestamp_ns
                        sample_idx,  # rdt_seq
                        sample_idx,  # ft_seq
                        0,  # status
                        100,
                        200,
                        300,
                        400,
                        500,
                        600,  # counts
                    )
                    writer.write(sample)

                # Simulate 1000Hz timing (10ms for 10 samples)
                target_time = start_time + (i + samples_per_batch) * 0.001
                sleep_time = target_time - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # Allow final flush
            time.sleep(0.3)
            stats = writer.stats()

        # Verify no drops
        assert stats.samples_dropped == 0, (
            f"Dropped {stats.samples_dropped} samples out of {sample_count}"
        )
        assert stats.samples_written == sample_count, (
            f"Expected {sample_count} samples written, got {stats.samples_written}"
        )

    def test_write_latency_under_1ms(self, tmp_path: Path) -> None:
        """Individual write() calls should complete in under 1ms.

        The write() method must never block the acquisition thread.
        """
        path = tmp_path / "test.csv"
        latencies_us: list[float] = []

        with AsyncFileWriter(path) as writer:
            for i in range(1000):
                sample = (i, i, i, 0, 100, 200, 300, 400, 500, 600)
                start = time.perf_counter_ns()
                writer.write(sample)
                end = time.perf_counter_ns()
                latencies_us.append((end - start) / 1000)

        avg_latency_us = sum(latencies_us) / len(latencies_us)
        max_latency_us = max(latencies_us)

        # Average write should be well under 1ms (typically ~1-10 microseconds)
        assert avg_latency_us < 1000, f"Average write latency {avg_latency_us:.1f}us > 1ms"
        # Max write should still be under 1ms
        assert max_latency_us < 1000, f"Max write latency {max_latency_us:.1f}us > 1ms"


class TestAsyncFileWriterMemory:
    """Tests for memory usage during logging."""

    def test_memory_stable_during_sustained_write(self, tmp_path: Path) -> None:
        """Memory should remain stable during sustained logging."""
        gc.collect()
        tracemalloc.start()

        path = tmp_path / "test.csv"
        with AsyncFileWriter(path, flush_interval_ms=100) as writer:
            # Write 5000 samples (~5 seconds at 1000Hz)
            for i in range(5000):
                sample = (i * 1_000_000, i, i, 0, 100, 200, 300, 400, 500, 600)
                writer.write(sample)
                if i % 100 == 0:
                    time.sleep(0.001)  # Small delay to allow processing

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        # Writer should use minimal memory (< 10 MB)
        assert peak_mb < 10, f"Writer peak memory {peak_mb:.1f} MB > 10 MB"


class TestExportFormats:
    """Tests for CSV/TSV/Excel export formats."""

    @pytest.fixture
    def sample(self) -> SampleRecord:
        return SampleRecord(
            t_monotonic_ns=1000,
            rdt_sequence=1,
            ft_sequence=2,
            status=0,
            counts=(10, 20, 30, 40, 50, 60),
            force_N=(1.1, 2.2, 3.3),
            torque_Nm=(4.4, 5.5, 6.6),
        )

    def test_csv_formatter(self, sample: SampleRecord) -> None:
        line = csv_formatter(sample)
        expected = "1000,1,2,0,10,20,30,40,50,60,1.100000,2.200000,3.300000,4.400000,5.500000,6.600000"
        assert line == expected

    def test_tsv_formatter(self, sample: SampleRecord) -> None:
        line = tsv_formatter(sample)
        expected = "1000\t1\t2\t0\t10\t20\t30\t40\t50\t60\t1.100000\t2.200000\t3.300000\t4.400000\t5.500000\t6.600000"
        assert line == expected

    def test_csv_formatter_handles_none_values(self) -> None:
        # Sample with no forces/torques
        sample = SampleRecord(
            t_monotonic_ns=1000,
            rdt_sequence=1,
            ft_sequence=2,
            status=0,
            counts=(10, 20, 30, 40, 50, 60),
            force_N=None,
            torque_Nm=None,
        )
        line = csv_formatter(sample)
        # Should have empty strings for last 6 columns (requires 6 commas)
        expected = "1000,1,2,0,10,20,30,40,50,60,,,,,,"
        assert line == expected

    def test_metadata_header_csv(self) -> None:
        cal = CalibrationInfo(counts_per_force=100.0, counts_per_torque=20.0)
        ident = {"serial_number": "SN123", "firmware_version": "1.0"}
        
        header = get_metadata_header(FORMAT_CSV, calibration=cal, identity=ident)
        
        lines = header.split("\n")
        assert any("Serial Number: SN123" in line for line in lines)
        assert any("Counts Per Force: 100.0" in line for line in lines)
        # Check column header presence
        assert "t_monotonic_ns,rdt_sequence" in lines[-1]

    def test_metadata_header_excel(self) -> None:
        cal = CalibrationInfo(counts_per_force=100.0, counts_per_torque=20.0)
        ident = {"serial_number": "SN123", "firmware_version": "1.0"}
        
        header = get_metadata_header(FORMAT_EXCEL, calibration=cal, identity=ident)
        
        # Should start with BOM
        assert header.startswith(BOM_UTF8)
        # Should use CRLF
        assert "\r\n" in header
        
        # Check content
        assert "Serial Number: SN123" in header

    def test_integration_excel_writer(self, tmp_path: Path, sample: SampleRecord) -> None:
        """End-to-end test for Excel-compatible export."""
        path = tmp_path / "export.csv"
        
        cal = CalibrationInfo(counts_per_force=100.0, counts_per_torque=20.0)
        ident = {"serial_number": "SN123"}
        header = get_metadata_header(FORMAT_EXCEL, calibration=cal, identity=ident)
        
        with AsyncFileWriter(
            path, 
            formatter=excel_formatter, 
            header=header, 
            line_terminator="\r\n"
        ) as writer:
            writer.write(sample)
            
        # Read back in binary to check BOM and CRLF
        with open(path, "rb") as f:
            content = f.read()
            
        # Check BOM
        assert content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
        
        # Check CRLF
        assert b"\r\n" in content
        
        # Decode and check text content
        text = content.decode("utf-8-sig") # decoding with sig removes BOM
        assert "# Serial Number: SN123" in text
        assert "1000,1,2,0" in text  # Data row presence