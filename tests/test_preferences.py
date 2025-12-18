"""Tests for preferences storage and persistence."""

import json
import os
import stat
from pathlib import Path

import pytest

from gsdv.config.preferences import (
    APP_NAME,
    PREFERENCES_VERSION,
    BiasMode,
    ForceUnit,
    LogFormat,
    PreferencesStore,
    TorqueUnit,
    UserPreferences,
    get_preferences_dir,
    get_preferences_path,
)


class TestUserPreferences:
    """Tests for UserPreferences dataclass."""

    def test_default_values(self) -> None:
        """Default preferences match specification."""
        prefs = UserPreferences()

        # Metadata
        assert prefs.preferences_version == PREFERENCES_VERSION
        assert prefs.last_updated_utc == ""

        # Connection defaults (Section 14.1)
        assert prefs.last_ip == ""
        assert prefs.udp_port == 49152
        assert prefs.tcp_port == 49151
        assert prefs.http_port == 80
        assert prefs.connect_timeout_ms == 2000

        # Visualization defaults (Section 14.2)
        assert prefs.channels_enabled == ["Fx", "Fy", "Fz"]
        assert prefs.time_window_seconds == 10.0
        assert prefs.y_autoscale is True
        assert prefs.y_manual_min is None
        assert prefs.y_manual_max is None
        assert prefs.show_grid is True
        assert prefs.show_crosshair is False
        assert prefs.plot_max_points_per_channel == 10000

        # Units defaults (Section 14.3)
        assert prefs.force_unit == ForceUnit.N.value
        assert prefs.torque_unit == TorqueUnit.Nm.value

        # Filtering defaults (Section 14.4)
        assert prefs.filter_enabled is False
        assert prefs.filter_cutoff_hz == 120.0

        # Bias defaults (Section 14.5)
        assert prefs.bias_mode == BiasMode.device.value

        # Logging defaults (Section 14.6)
        assert prefs.output_directory == ""
        assert prefs.filename_prefix == ""
        assert prefs.log_format == LogFormat.csv.value
        assert prefs.rotation_enabled is True

        # Transform defaults (Section 14.7)
        assert prefs.transform_dx == 0.0
        assert prefs.transform_dy == 0.0
        assert prefs.transform_dz == 0.0

        # Theme default (FR-28)
        assert prefs.theme == "dark"

    def test_mutable_default_not_shared(self) -> None:
        """Each instance gets its own channels_enabled list."""
        prefs1 = UserPreferences()
        prefs2 = UserPreferences()

        prefs1.channels_enabled.append("Tx")

        assert "Tx" not in prefs2.channels_enabled


class TestPreferencesPath:
    """Tests for preferences path functions."""

    def test_get_preferences_dir_uses_platformdirs(self) -> None:
        """Preferences directory uses platformdirs with correct app name."""
        import platformdirs

        expected = Path(platformdirs.user_config_dir(APP_NAME))
        actual = get_preferences_dir()
        assert actual == expected

    def test_get_preferences_path_filename(self) -> None:
        """Preferences file is named preferences.json."""
        path = get_preferences_path()
        assert path.name == "preferences.json"
        assert path.parent == get_preferences_dir()


class TestPreferencesStore:
    """Tests for PreferencesStore load/save operations."""

    def test_load_returns_defaults_when_file_missing(self, tmp_path: Path) -> None:
        """Loading from non-existent file returns default preferences."""
        prefs_path = tmp_path / "gsdv" / "preferences.json"
        store = PreferencesStore(prefs_path)

        prefs = store.load()

        assert prefs.force_unit == ForceUnit.N.value
        assert prefs.channels_enabled == ["Fx", "Fy", "Fz"]

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Saving creates parent directory if it doesn't exist."""
        prefs_path = tmp_path / "new_dir" / "nested" / "preferences.json"
        store = PreferencesStore(prefs_path)

        store.save(UserPreferences())

        assert prefs_path.exists()
        assert prefs_path.parent.is_dir()

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Preferences survive save/load cycle."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        # Save custom preferences
        prefs = UserPreferences()
        prefs.last_ip = "192.168.1.100"
        prefs.channels_enabled = ["Fx", "Fy", "Fz", "Tx", "Ty", "Tz"]
        prefs.force_unit = ForceUnit.lbf.value
        prefs.torque_unit = TorqueUnit.lbf_ft.value
        prefs.filter_enabled = True
        prefs.filter_cutoff_hz = 50.0
        prefs.theme = "light"
        prefs.transform_dx = 10.5
        prefs.y_autoscale = False
        prefs.y_manual_min = -50.0
        prefs.y_manual_max = 150.0

        store.save(prefs)

        # Load and verify
        loaded = store.load()
        assert loaded.last_ip == "192.168.1.100"
        assert loaded.channels_enabled == ["Fx", "Fy", "Fz", "Tx", "Ty", "Tz"]
        assert loaded.force_unit == ForceUnit.lbf.value
        assert loaded.torque_unit == TorqueUnit.lbf_ft.value
        assert loaded.filter_enabled is True
        assert loaded.filter_cutoff_hz == 50.0
        assert loaded.theme == "light"
        assert loaded.transform_dx == 10.5
        assert loaded.y_autoscale is False
        assert loaded.y_manual_min == -50.0
        assert loaded.y_manual_max == 150.0

    def test_save_updates_timestamp(self, tmp_path: Path) -> None:
        """Saving sets last_updated_utc to current time."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        prefs = UserPreferences()
        assert prefs.last_updated_utc == ""

        store.save(prefs)

        loaded = store.load()
        assert loaded.last_updated_utc != ""
        # Should be ISO format
        assert "T" in loaded.last_updated_utc

    def test_save_sets_version(self, tmp_path: Path) -> None:
        """Saving ensures preferences_version is set."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        prefs = UserPreferences()
        prefs.preferences_version = 0  # Simulate old version

        store.save(prefs)

        loaded = store.load()
        assert loaded.preferences_version == PREFERENCES_VERSION

    def test_load_ignores_unknown_keys(self, tmp_path: Path) -> None:
        """Loading ignores keys not in UserPreferences."""
        prefs_path = tmp_path / "preferences.json"

        # Write JSON with unknown key
        data = {"last_ip": "10.0.0.1", "unknown_future_field": "some_value"}
        prefs_path.write_text(json.dumps(data))

        store = PreferencesStore(prefs_path)
        prefs = store.load()

        assert prefs.last_ip == "10.0.0.1"
        assert not hasattr(prefs, "unknown_future_field")

    def test_load_uses_defaults_for_missing_keys(self, tmp_path: Path) -> None:
        """Loading uses defaults for keys not in file."""
        prefs_path = tmp_path / "preferences.json"

        # Write JSON with only some keys
        data = {"last_ip": "10.0.0.1"}
        prefs_path.write_text(json.dumps(data))

        store = PreferencesStore(prefs_path)
        prefs = store.load()

        assert prefs.last_ip == "10.0.0.1"
        # Other fields have defaults
        assert prefs.force_unit == ForceUnit.N.value
        assert prefs.channels_enabled == ["Fx", "Fy", "Fz"]

    def test_load_returns_defaults_on_invalid_json(self, tmp_path: Path) -> None:
        """Loading invalid JSON returns default preferences."""
        prefs_path = tmp_path / "preferences.json"
        prefs_path.write_text("{ invalid json }")

        store = PreferencesStore(prefs_path)
        prefs = store.load()

        assert prefs.force_unit == ForceUnit.N.value

    def test_save_writes_valid_json(self, tmp_path: Path) -> None:
        """Saved file contains valid, readable JSON."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        store.save(UserPreferences())

        content = prefs_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert "force_unit" in data
        assert data["force_unit"] == "N"

    def test_save_uses_indented_json(self, tmp_path: Path) -> None:
        """Saved JSON is human-readable with indentation."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        store.save(UserPreferences())

        content = prefs_path.read_text()
        # Indented JSON has newlines
        assert "\n" in content
        # And leading spaces
        assert "  " in content

    def test_path_property(self, tmp_path: Path) -> None:
        """Store exposes its path via property."""
        prefs_path = tmp_path / "custom" / "prefs.json"
        store = PreferencesStore(prefs_path)

        assert store.path == prefs_path


class TestAtomicWrite:
    """Tests for atomic write behavior."""

    def test_no_temp_file_left_on_success(self, tmp_path: Path) -> None:
        """Successful save leaves no temp files."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        store.save(UserPreferences())

        files = list(tmp_path.iterdir())
        assert files == [prefs_path]

    def test_save_is_atomic_file_exists_after_save(self, tmp_path: Path) -> None:
        """File exists immediately after save completes."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        store.save(UserPreferences())

        assert prefs_path.exists()
        # File should be readable
        content = prefs_path.read_text()
        assert "preferences_version" in content

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        """Subsequent saves overwrite previous file."""
        prefs_path = tmp_path / "preferences.json"
        store = PreferencesStore(prefs_path)

        prefs1 = UserPreferences()
        prefs1.last_ip = "first"
        store.save(prefs1)

        prefs2 = UserPreferences()
        prefs2.last_ip = "second"
        store.save(prefs2)

        loaded = store.load()
        assert loaded.last_ip == "second"

    def test_save_cleans_up_temp_on_error(self, tmp_path: Path) -> None:
        """Temp file is removed if an error occurs during save."""
        # Create a read-only directory to cause write failure
        prefs_dir = tmp_path / "readonly"
        prefs_dir.mkdir()
        prefs_path = prefs_dir / "preferences.json"

        # Write initial file
        store = PreferencesStore(prefs_path)
        store.save(UserPreferences())

        # Make directory read-only (can't create new temp files)
        os.chmod(prefs_dir, stat.S_IRUSR | stat.S_IXUSR)

        try:
            with pytest.raises(OSError):
                store.save(UserPreferences())

            # No temp files should remain
            files = list(prefs_dir.iterdir())
            temp_files = [f for f in files if f.suffix == ".tmp"]
            assert temp_files == []
        finally:
            # Restore permissions for cleanup
            os.chmod(prefs_dir, stat.S_IRWXU)


class TestEnums:
    """Tests for preference enum types."""

    def test_force_unit_values(self) -> None:
        """ForceUnit has correct values."""
        assert ForceUnit.N.value == "N"
        assert ForceUnit.lbf.value == "lbf"
        assert ForceUnit.kgf.value == "kgf"

    def test_torque_unit_values(self) -> None:
        """TorqueUnit has correct values."""
        assert TorqueUnit.Nm.value == "Nm"
        assert TorqueUnit.Nmm.value == "Nmm"
        assert TorqueUnit.lbf_in.value == "lbf_in"
        assert TorqueUnit.lbf_ft.value == "lbf_ft"

    def test_bias_mode_values(self) -> None:
        """BiasMode has correct values."""
        assert BiasMode.device.value == "device"
        assert BiasMode.soft.value == "soft"

    def test_log_format_values(self) -> None:
        """LogFormat has correct values."""
        assert LogFormat.csv.value == "csv"
        assert LogFormat.tsv.value == "tsv"
        assert LogFormat.excel_compatible.value == "excel_compatible"
