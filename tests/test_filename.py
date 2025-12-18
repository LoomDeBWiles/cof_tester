"""Tests for filename generation."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from gsdv.logging.filename import (
    generate_filename,
    generate_filepath,
    is_valid_prefix,
    preview_filename,
    sanitize_prefix,
)


class TestSanitizePrefix:
    """Tests for prefix sanitization."""

    def test_empty_prefix_returns_empty(self) -> None:
        assert sanitize_prefix("") == ""

    def test_safe_prefix_unchanged(self) -> None:
        assert sanitize_prefix("my_data") == "my_data"
        assert sanitize_prefix("test-file") == "test-file"
        assert sanitize_prefix("Sample.v1") == "Sample.v1"

    def test_removes_windows_reserved_chars(self) -> None:
        assert sanitize_prefix("test<>file") == "testfile"
        assert sanitize_prefix('path:name') == "pathname"
        assert sanitize_prefix("file/name") == "filename"
        assert sanitize_prefix("back\\slash") == "backslash"
        assert sanitize_prefix("pipe|char") == "pipechar"
        assert sanitize_prefix("question?mark") == "questionmark"
        assert sanitize_prefix("star*char") == "starchar"

    def test_removes_quotes(self) -> None:
        assert sanitize_prefix('file"name') == "filename"

    def test_removes_control_characters(self) -> None:
        assert sanitize_prefix("test\x00file") == "testfile"
        assert sanitize_prefix("test\x1fdata") == "testdata"

    def test_collapses_multiple_separators(self) -> None:
        assert sanitize_prefix("test__data") == "test_data"
        assert sanitize_prefix("test---data") == "test_data"
        assert sanitize_prefix("test_-_data") == "test_data"

    def test_strips_leading_trailing_dots(self) -> None:
        assert sanitize_prefix(".hidden") == "hidden"
        assert sanitize_prefix("data.") == "data"
        assert sanitize_prefix("...dots...") == "dots"

    def test_strips_whitespace(self) -> None:
        assert sanitize_prefix("  padded  ") == "padded"


class TestIsValidPrefix:
    """Tests for prefix validation."""

    def test_empty_prefix_is_valid(self) -> None:
        assert is_valid_prefix("") is True

    def test_alphanumeric_is_valid(self) -> None:
        assert is_valid_prefix("test123") is True

    def test_underscore_hyphen_dot_valid(self) -> None:
        assert is_valid_prefix("my_data-file.v1") is True

    def test_space_is_invalid(self) -> None:
        assert is_valid_prefix("my data") is False

    def test_special_chars_invalid(self) -> None:
        assert is_valid_prefix("test<file") is False
        assert is_valid_prefix("test:file") is False
        assert is_valid_prefix("test/file") is False


class TestGenerateFilename:
    """Tests for filename generation."""

    def test_basic_csv_filename(self) -> None:
        ts = datetime(2025, 12, 18, 14, 30, 45, tzinfo=timezone.utc)
        result = generate_filename("csv", timestamp=ts)
        assert result == "20251218_143045.csv"

    def test_with_prefix(self) -> None:
        ts = datetime(2025, 1, 5, 9, 5, 0, tzinfo=timezone.utc)
        result = generate_filename("csv", prefix="experiment", timestamp=ts)
        assert result == "experiment_20250105_090500.csv"

    def test_prefix_is_sanitized(self) -> None:
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = generate_filename("csv", prefix="test<>data", timestamp=ts)
        assert result == "testdata_20250615_120000.csv"

    def test_with_part_number(self) -> None:
        ts = datetime(2025, 3, 20, 8, 15, 30, tzinfo=timezone.utc)
        result = generate_filename("csv", timestamp=ts, part_number=1)
        assert result == "20250320_081530_part001.csv"

    def test_with_prefix_and_part_number(self) -> None:
        ts = datetime(2025, 7, 4, 16, 45, 0, tzinfo=timezone.utc)
        result = generate_filename(
            "tsv", prefix="log", timestamp=ts, part_number=42
        )
        assert result == "log_20250704_164500_part042.tsv"

    def test_part_number_max(self) -> None:
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_filename("csv", timestamp=ts, part_number=999)
        assert result == "20250101_000000_part999.csv"

    def test_extension_without_dot(self) -> None:
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_filename("csv", timestamp=ts)
        assert result.endswith(".csv")

    def test_extension_with_dot_normalized(self) -> None:
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = generate_filename(".csv", timestamp=ts)
        assert result.endswith(".csv")
        assert ".." not in result

    def test_empty_extension_raises(self) -> None:
        with pytest.raises(ValueError, match="Extension cannot be empty"):
            generate_filename("")

    def test_part_number_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Part number must be between 1 and 999"):
            generate_filename("csv", part_number=0)

    def test_part_number_too_large_raises(self) -> None:
        with pytest.raises(ValueError, match="Part number must be between 1 and 999"):
            generate_filename("csv", part_number=1000)

    def test_defaults_to_current_time(self) -> None:
        before = datetime.now(timezone.utc).replace(microsecond=0)
        result = generate_filename("csv")
        after = datetime.now(timezone.utc).replace(microsecond=0)

        # Parse the timestamp from the filename
        parts = result.replace(".csv", "").split("_")
        date_str = parts[0]
        time_str = parts[1]
        ts = datetime.strptime(
            f"{date_str}_{time_str}", "%Y%m%d_%H%M%S"
        ).replace(tzinfo=timezone.utc)

        # Allow 1 second tolerance for timing edge cases
        from datetime import timedelta
        assert before - timedelta(seconds=1) <= ts <= after + timedelta(seconds=1)


class TestGenerateFilepath:
    """Tests for filepath generation."""

    def test_combines_directory_and_filename(self) -> None:
        ts = datetime(2025, 12, 18, 14, 30, 45, tzinfo=timezone.utc)
        result = generate_filepath("/data/output", "csv", timestamp=ts)
        assert result == Path("/data/output/20251218_143045.csv")

    def test_with_path_object(self) -> None:
        ts = datetime(2025, 12, 18, 14, 30, 45, tzinfo=timezone.utc)
        result = generate_filepath(Path("/data/output"), "csv", timestamp=ts)
        assert result == Path("/data/output/20251218_143045.csv")

    def test_with_prefix(self) -> None:
        ts = datetime(2025, 12, 18, 14, 30, 45, tzinfo=timezone.utc)
        result = generate_filepath(
            "/data/output", "csv", prefix="test", timestamp=ts
        )
        assert result == Path("/data/output/test_20251218_143045.csv")


class TestPreviewFilename:
    """Tests for filename preview."""

    def test_basic_preview(self) -> None:
        result = preview_filename("csv")
        assert result == "YYYYMMDD_HHMMSS.csv"

    def test_preview_with_prefix(self) -> None:
        result = preview_filename("csv", prefix="experiment")
        assert result == "experiment_YYYYMMDD_HHMMSS.csv"

    def test_preview_sanitizes_prefix(self) -> None:
        result = preview_filename("csv", prefix="test<>data")
        assert result == "testdata_YYYYMMDD_HHMMSS.csv"

    def test_preview_with_extension_dot(self) -> None:
        result = preview_filename(".tsv")
        assert result == "YYYYMMDD_HHMMSS.tsv"


class TestFilenameUniqueness:
    """Tests verifying filename uniqueness properties."""

    def test_different_timestamps_produce_different_filenames(self) -> None:
        ts1 = datetime(2025, 12, 18, 14, 30, 45, tzinfo=timezone.utc)
        ts2 = datetime(2025, 12, 18, 14, 30, 46, tzinfo=timezone.utc)
        name1 = generate_filename("csv", timestamp=ts1)
        name2 = generate_filename("csv", timestamp=ts2)
        assert name1 != name2

    def test_different_prefixes_produce_different_filenames(self) -> None:
        ts = datetime(2025, 12, 18, 14, 30, 45, tzinfo=timezone.utc)
        name1 = generate_filename("csv", prefix="a", timestamp=ts)
        name2 = generate_filename("csv", prefix="b", timestamp=ts)
        assert name1 != name2

    def test_different_parts_produce_different_filenames(self) -> None:
        ts = datetime(2025, 12, 18, 14, 30, 45, tzinfo=timezone.utc)
        name1 = generate_filename("csv", timestamp=ts, part_number=1)
        name2 = generate_filename("csv", timestamp=ts, part_number=2)
        assert name1 != name2
