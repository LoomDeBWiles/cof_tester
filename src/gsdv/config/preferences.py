"""User preferences storage and management.

Implements FR-25 (Preferences Persistence) and FR-31 (Preferences Format and Location).
Preferences are stored as JSON in the OS user config directory via platformdirs,
using atomic writes (temp file + rename) to prevent corruption.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import platformdirs


# Preference format version for migrations
PREFERENCES_VERSION = 1

# App name for platformdirs
APP_NAME = "gsdv"


class ForceUnit(Enum):
    """Force unit options (FR-10)."""

    N = "N"
    lbf = "lbf"
    kgf = "kgf"


class TorqueUnit(Enum):
    """Torque unit options (FR-11)."""

    Nm = "Nm"
    Nmm = "Nmm"
    lbf_in = "lbf_in"
    lbf_ft = "lbf_ft"


class BiasMode(Enum):
    """Bias/tare mode options (FR-8)."""

    device = "device"
    soft = "soft"


class LogFormat(Enum):
    """Log file format options (FR-21)."""

    csv = "csv"
    tsv = "tsv"
    excel_compatible = "excel_compatible"


@dataclass
class UserPreferences:
    """User preferences data model (Section 15.3, Section 14)."""

    # Metadata
    preferences_version: int = PREFERENCES_VERSION
    last_updated_utc: str = ""

    # Connection (Section 14.1)
    last_ip: str = ""
    udp_port: int = 49152
    tcp_port: int = 49151
    http_port: int = 80
    connect_timeout_ms: int = 2000
    auto_reconnect: bool = True
    discovery_subnets: list[str] = field(default_factory=list)

    # Visualization (Section 14.2)
    channels_enabled: list[str] = field(
        default_factory=lambda: ["Fx", "Fy", "Fz"]
    )
    time_window_seconds: float = 10.0
    y_autoscale: bool = True
    y_manual_min: float | None = None
    y_manual_max: float | None = None
    show_grid: bool = True
    show_crosshair: bool = False
    plot_max_points_per_channel: int = 10000

    # Units (Section 14.3)
    force_unit: str = ForceUnit.N.value
    torque_unit: str = TorqueUnit.Nm.value

    # Filtering (Section 14.4)
    filter_enabled: bool = False
    filter_cutoff_hz: float = 120.0

    # Decimation (reduce effective sample rate)
    decimation_factor: int = 10  # 1000Hz / 10 = 100Hz effective rate

    # Bias (Section 14.5)
    bias_mode: str = BiasMode.device.value

    # Logging (Section 14.6)
    output_directory: str = ""
    filename_prefix: str = ""
    log_format: str = LogFormat.csv.value
    flush_interval_ms: int = 250
    log_decimation_factor: int = 1
    rotation_enabled: bool = True
    rotate_interval_minutes: int = 60
    rotate_max_bytes: int = 2_000_000_000

    # Tool Transform (Section 14.7)
    transform_dx: float = 0.0
    transform_dy: float = 0.0
    transform_dz: float = 0.0
    transform_rx: float = 0.0
    transform_ry: float = 0.0
    transform_rz: float = 0.0

    # Theme (FR-28)
    theme: str = "dark"


def get_preferences_dir() -> Path:
    """Return the OS-specific user config directory for gsdv."""
    return Path(platformdirs.user_config_dir(APP_NAME))


def get_preferences_path() -> Path:
    """Return the full path to the preferences.json file."""
    return get_preferences_dir() / "preferences.json"


class PreferencesStore:
    """Handles loading and saving user preferences with atomic writes.

    Example usage:
        store = PreferencesStore()
        prefs = store.load()
        prefs.last_ip = "192.168.1.100"
        store.save(prefs)
    """

    def __init__(self, preferences_path: Path | None = None) -> None:
        """Initialize the preferences store.

        Args:
            preferences_path: Custom path for preferences file. If None, uses
                the default OS config directory location.
        """
        self._path = preferences_path or get_preferences_path()

    @property
    def path(self) -> Path:
        """Return the preferences file path."""
        return self._path

    def load(self) -> UserPreferences:
        """Load preferences from disk.

        Returns:
            UserPreferences with values from disk, or defaults if file
            doesn't exist or is invalid.
        """
        if not self._path.exists():
            return UserPreferences()

        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            return self._from_dict(data)
        except (json.JSONDecodeError, OSError):
            return UserPreferences()

    def save(self, preferences: UserPreferences) -> None:
        """Save preferences to disk using atomic write.

        Writes to a temporary file in the same directory, then renames
        to the target path. This ensures the preferences file is never
        left in a partially-written state.

        Args:
            preferences: The preferences to save.

        Raises:
            OSError: If the directory cannot be created or write fails.
        """
        # Update timestamp
        preferences.last_updated_utc = datetime.now(timezone.utc).isoformat()
        preferences.preferences_version = PREFERENCES_VERSION

        # Ensure directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize to JSON
        data = self._to_dict(preferences)
        content = json.dumps(data, indent=2, ensure_ascii=False)

        # Atomic write: temp file + rename
        dir_fd = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix="preferences_",
                dir=self._path.parent,
            )
            try:
                os.write(fd, content.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)

            # Rename atomically
            os.replace(tmp_path, self._path)

            # Sync directory to ensure rename is durable (Unix only)
            if hasattr(os, "O_DIRECTORY"):
                dir_fd = os.open(self._path.parent, os.O_RDONLY | os.O_DIRECTORY)
                os.fsync(dir_fd)
        except BaseException:
            # Clean up temp file on any error
            if "tmp_path" in locals():
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
        finally:
            if dir_fd is not None:
                os.close(dir_fd)

    def _to_dict(self, preferences: UserPreferences) -> dict[str, Any]:
        """Convert preferences to a dictionary for JSON serialization."""
        return asdict(preferences)

    def _from_dict(self, data: dict[str, Any]) -> UserPreferences:
        """Convert a dictionary to UserPreferences with validation.

        Unknown keys are ignored, missing keys use defaults.
        """
        defaults = UserPreferences()
        valid_fields = {f.name for f in defaults.__dataclass_fields__.values()}

        kwargs = {}
        for key, value in data.items():
            if key in valid_fields:
                kwargs[key] = value

        return UserPreferences(**kwargs)
