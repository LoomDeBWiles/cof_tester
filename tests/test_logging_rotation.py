"""Tests for AsyncFileWriter log rotation."""

import time
from pathlib import Path

from gsdv.logging.writer import AsyncFileWriter


class TestAsyncFileWriterRotation:
    """Tests for log rotation features."""

    def test_rotates_by_size(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        # Rotate after ~50 bytes
        # Each line "123456789\n" is 10 bytes
        with AsyncFileWriter(
            path,
            rotate_size_bytes=50,
            flush_interval_ms=50,
            formatter=lambda x: str(x[0])
        ) as writer:
            for i in range(10):
                writer.write(("123456789",))
            time.sleep(0.2)

        files = sorted(list(tmp_path.glob("test*.csv")))
        assert len(files) >= 2
        # Check part numbering
        assert "_part001" in files[0].name
        assert "_part002" in files[1].name

    def test_rotates_by_time(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        # Rotate every 0.5 seconds
        with AsyncFileWriter(
            path,
            rotate_interval_s=0.5,
            flush_interval_ms=50
        ) as writer:
            writer.write((1,))
            time.sleep(0.7) # Wait longer than rotation interval
            writer.write((2,))
            time.sleep(0.2)

        files = sorted(list(tmp_path.glob("test*.csv")))
        assert len(files) >= 2
        assert "_part001" in files[0].name
        assert "_part002" in files[1].name

    def test_first_file_has_part_number_if_rotation_enabled(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        with AsyncFileWriter(path, rotate_size_bytes=1000) as writer:
            writer.write((1,))
        
        # Original path should not exist as a file (unless it matches the generated one, which it shouldn't)
        assert not path.exists()
        # Should find part 1
        part1 = tmp_path / "test_part001.csv"
        assert part1.exists()

    def test_no_rotation_uses_original_filename(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        with AsyncFileWriter(path) as writer:
            writer.write((1,))
        
        assert path.exists()
        assert not (tmp_path / "test_part001.csv").exists()

