"Main application window."

from __future__ import annotations

import ipaddress
import os
import re
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gsdv.config.preferences import UserPreferences
from gsdv.plot.plot_widget import MultiChannelPlot
from gsdv.protocols.tcp_cmd import ToolTransform
from gsdv.ui.settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from gsdv.models import CalibrationInfo


class ChannelSelector(QGroupBox):
    """Widget for selecting which F/T channels to display."""

    channel_toggled = Signal(str, bool)

    CHANNELS = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Channels", parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        for channel in self.CHANNELS:
            checkbox = QCheckBox(channel)
            checkbox.setChecked(True) # Default all visible
            checkbox.toggled.connect(
                lambda checked, ch=channel: self.channel_toggled.emit(ch, checked)
            )
            self._checkboxes[channel] = checkbox
            layout.addWidget(checkbox)

        layout.addStretch()

    def enabled_channels(self) -> list[str]:
        """Return list of currently enabled channel names."""
        return [ch for ch, cb in self._checkboxes.items() if cb.isChecked()]

    def set_channel_enabled(self, channel: str, enabled: bool) -> None:
        """Set the enabled state of a specific channel."""
        if channel in self._checkboxes:
            self._checkboxes[channel].setChecked(enabled)


class TimeWindowSelector(QGroupBox):
    """Widget for selecting the time window for the plot display.

    Provides a dropdown with preset time windows ranging from 1 second
    to 7 days. Emits window_changed signal when the user selects a
    different time window.

    Time windows are organized by resolution tier:
    - Raw buffer (up to 60s): 1s, 5s, 10s, 30s, 60s
    - Tier1 (up to 1hr): 5m, 15m, 30m, 1h
    - Tier2 (up to 24hr): 6h, 12h, 24h
    - Tier3 (up to 7d): 3d, 7d
    """

    window_changed = Signal(float)

    # Preset time windows: (display_label, seconds)
    # Minimum 1s, maximum 7 days (604800s)
    TIME_WINDOWS: tuple[tuple[str, float], ...] = (
        ("1 sec", 1.0),
        ("5 sec", 5.0),
        ("10 sec", 10.0),
        ("30 sec", 30.0),
        ("1 min", 60.0),
        ("5 min", 300.0),
        ("15 min", 900.0),
        ("30 min", 1800.0),
        ("1 hour", 3600.0),
        ("6 hours", 21600.0),
        ("12 hours", 43200.0),
        ("24 hours", 86400.0),
        ("3 days", 259200.0),
        ("7 days", 604800.0),
    )

    DEFAULT_INDEX = 2  # 10 seconds

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Time Window", parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        label = QLabel("Display:")
        layout.addWidget(label)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(100)
        for display_label, _ in self.TIME_WINDOWS:
            self._combo.addItem(display_label)
        self._combo.setCurrentIndex(self.DEFAULT_INDEX)
        self._combo.currentIndexChanged.connect(self._on_index_changed)
        layout.addWidget(self._combo)

        layout.addStretch()

    def _on_index_changed(self, index: int) -> None:
        """Handle combo box selection change."""
        if 0 <= index < len(self.TIME_WINDOWS):
            _, seconds = self.TIME_WINDOWS[index]
            self.window_changed.emit(seconds)

    def window_seconds(self) -> float:
        """Return the currently selected time window in seconds."""
        index = self._combo.currentIndex()
        if 0 <= index < len(self.TIME_WINDOWS):
            return self.TIME_WINDOWS[index][1]
        return self.TIME_WINDOWS[self.DEFAULT_INDEX][1]

    def set_window_seconds(self, seconds: float) -> None:
        """Set the time window by value in seconds.

        If the exact value is not in the preset list, selects the
        closest available window and emits the window_changed signal
        with the snapped value.

        Args:
            seconds: Time window duration in seconds.
        """
        # Find closest match
        closest_index = 0
        closest_diff = abs(self.TIME_WINDOWS[0][1] - seconds)
        for i, (_, window_seconds) in enumerate(self.TIME_WINDOWS):
            diff = abs(window_seconds - seconds)
            if diff < closest_diff:
                closest_diff = diff
                closest_index = i

        # Update combo box
        current_index = self._combo.currentIndex()
        self._combo.setCurrentIndex(closest_index)

        # Emit signal explicitly if index didn't change
        # This ensures connected handlers are always notified of the (potentially snapped) value
        if current_index == closest_index:
            _, snapped_seconds = self.TIME_WINDOWS[closest_index]
            self.window_changed.emit(snapped_seconds)

    def set_window_index(self, index: int) -> None:
        """Set the time window by index.

        Args:
            index: Index into TIME_WINDOWS list.

        Raises:
            IndexError: If index is out of range.
        """
        if not 0 <= index < len(self.TIME_WINDOWS):
            raise IndexError(f"Index {index} out of range (0-{len(self.TIME_WINDOWS) - 1})")
        self._combo.setCurrentIndex(index)


def is_valid_ipv4(ip_string: str) -> bool:
    """Validate an IPv4 address string.

    Args:
        ip_string: The string to validate as an IPv4 address.

    Returns:
        True if the string is a valid IPv4 address, False otherwise.
    """
    try:
        ipaddress.IPv4Address(ip_string)
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


class ConnectionPanel(QGroupBox):
    """Widget for sensor connection controls.

    Provides IP address input with validation, connect/disconnect button,
    and connection status indicator.

    Signals:
        connect_requested: Emitted when user requests connection with valid IP.
        disconnect_requested: Emitted when user requests disconnection.
    """

    connect_requested = Signal(str)
    disconnect_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Connection", parent)
        self._connected = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        ip_label = QLabel("Sensor IP:")
        layout.addWidget(ip_label)

        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("192.168.1.1")
        self._ip_input.setMinimumWidth(140)
        self._ip_input.returnPressed.connect(self._on_connect_clicked)
        self._ip_input.textChanged.connect(self._on_ip_text_changed)
        layout.addWidget(self._ip_input)

        self._validation_label = QLabel()
        self._validation_label.setFixedWidth(16)
        layout.addWidget(self._validation_label)

        self._connect_button = QPushButton("Connect")
        self._connect_button.clicked.connect(self._on_connect_clicked)
        self._connect_button.setEnabled(False)
        layout.addWidget(self._connect_button)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self._status_indicator = QLabel()
        self._status_indicator.setFixedSize(12, 12)
        self._update_status_indicator()
        layout.addWidget(self._status_indicator)

        self._status_label = QLabel("Disconnected")
        layout.addWidget(self._status_label)

        layout.addStretch()

    def _on_ip_text_changed(self, text: str) -> None:
        """Handle IP input text changes for validation."""
        ip = text.strip()
        if not ip:
            self._validation_label.setText("")
            self._validation_label.setToolTip("")
            self._connect_button.setEnabled(False)
        elif is_valid_ipv4(ip):
            self._validation_label.setText("")
            self._validation_label.setToolTip("")
            self._connect_button.setEnabled(True)
        else:
            self._validation_label.setText("")
            self._validation_label.setToolTip("Invalid IPv4 address")
            self._connect_button.setEnabled(False)

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
        else:
            ip = self._ip_input.text().strip()
            if ip and is_valid_ipv4(ip):
                self.connect_requested.emit(ip)

    def _update_status_indicator(self) -> None:
        color = "#4CAF50" if self._connected else "#9E9E9E"
        self._status_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 6px;"
        )

    def is_ip_valid(self) -> bool:
        """Check if the current IP input is a valid IPv4 address."""
        return is_valid_ipv4(self._ip_input.text().strip())

    def set_connected(self, connected: bool, status_text: str = "") -> None:
        """Update connection state display."""
        self._connected = connected
        self._connect_button.setText("Disconnect" if connected else "Connect")
        self._connect_button.setEnabled(connected or self.is_ip_valid())
        self._ip_input.setEnabled(not connected)
        self._status_label.setText(status_text or ("Connected" if connected else "Disconnected"))
        self._update_status_indicator()

    def get_ip(self) -> str:
        """Return the current IP address text."""
        return self._ip_input.text().strip()

    def set_ip(self, ip: str) -> None:
        """Set the IP address text."""
        self._ip_input.setText(ip)


class SensorInfoDisplay(QGroupBox):
    """Widget displaying sensor identification and calibration information.

    Shows serial number, firmware version, and calibration factors (cpf/cpt)
    when connected to a sensor.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Sensor Info", parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)

        # Serial number
        serial_label = QLabel("Serial:")
        serial_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(serial_label, 0, 0)

        self._serial_value = QLabel("---")
        self._serial_value.setStyleSheet("font-family: monospace;")
        layout.addWidget(self._serial_value, 0, 1)

        # Firmware version
        firmware_label = QLabel("Firmware:")
        firmware_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(firmware_label, 0, 2)

        self._firmware_value = QLabel("---")
        self._firmware_value.setStyleSheet("font-family: monospace;")
        layout.addWidget(self._firmware_value, 0, 3)

        # Counts per force (cpf)
        cpf_label = QLabel("CPF:")
        cpf_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cpf_label.setToolTip("Counts per force (calibration factor)")
        layout.addWidget(cpf_label, 1, 0)

        self._cpf_value = QLabel("---")
        self._cpf_value.setStyleSheet("font-family: monospace;")
        self._cpf_value.setToolTip("Counts per force (calibration factor)")
        layout.addWidget(self._cpf_value, 1, 1)

        # Counts per torque (cpt)
        cpt_label = QLabel("CPT:")
        cpt_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cpt_label.setToolTip("Counts per torque (calibration factor)")
        layout.addWidget(cpt_label, 1, 2)

        self._cpt_value = QLabel("---")
        self._cpt_value.setStyleSheet("font-family: monospace;")
        self._cpt_value.setToolTip("Counts per torque (calibration factor)")
        layout.addWidget(self._cpt_value, 1, 3)

    def update_info(self, calibration: CalibrationInfo) -> None:
        """Update display with calibration information from sensor.

        Args:
            calibration: CalibrationInfo object containing sensor data.
        """
        self._serial_value.setText(calibration.serial_number or "N/A")
        self._firmware_value.setText(calibration.firmware_version or "N/A")
        self._cpf_value.setText(f"{calibration.counts_per_force:,.0f}")
        self._cpt_value.setText(f"{calibration.counts_per_torque:,.0f}")

    def clear_info(self) -> None:
        """Clear all displayed information."""
        self._serial_value.setText("---")
        self._firmware_value.setText("---")
        self._cpf_value.setText("---")
        self._cpt_value.setText("---")


class NumericDisplay(QGroupBox):
    """Widget showing real-time numeric values for each channel."""

    CHANNELS = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")
    FORCE_CHANNELS = ("Fx", "Fy", "Fz")
    TORQUE_CHANNELS = ("Tx", "Ty", "Tz")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Numeric Readout", parent)
        self._labels: dict[str, QLabel] = {}
        self._value_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        for i, channel in enumerate(self.CHANNELS):
            name_label = QLabel(f"{channel}:")
            name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(name_label, i // 3, (i % 3) * 2)

            value_label = QLabel("---")
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value_label.setMinimumWidth(80)
            value_label.setStyleSheet("font-family: monospace;")
            layout.addWidget(value_label, i // 3, (i % 3) * 2 + 1)

            self._labels[channel] = name_label
            self._value_labels[channel] = value_label

    def update_value(self, channel: str, value: float, unit: str) -> None:
        """Update the displayed value for a channel."""
        if channel in self._value_labels:
            self._value_labels[channel].setText(f"{value:+.3f} {unit}")

    def clear_values(self) -> None:
        """Clear all displayed values."""
        for label in self._value_labels.values():
            label.setText("---")


class RecordingControls(QGroupBox):
    """Widget for data recording controls."""

    record_started = Signal()
    record_stopped = Signal()
    folder_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Recording", parent)
        self._recording = False
        self._output_path = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        folder_label = QLabel("Output:")
        layout.addWidget(folder_label)

        self._path_label = QLabel("Not selected")
        self._path_label.setMinimumWidth(200)
        self._path_label.setStyleSheet("color: gray;")
        layout.addWidget(self._path_label)

        self._browse_button = QPushButton("Browse...")
        self._browse_button.clicked.connect(self._on_browse_clicked)
        layout.addWidget(self._browse_button)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self._record_button = QPushButton("Record")
        self._record_button.setMinimumWidth(80)
        self._record_button.clicked.connect(self._on_record_clicked)
        self._record_button.setEnabled(False)
        layout.addWidget(self._record_button)

        self._recording_indicator = QLabel()
        self._recording_indicator.setFixedSize(12, 12)
        self._update_recording_indicator()
        layout.addWidget(self._recording_indicator)

        self._duration_label = QLabel("")
        self._duration_label.setMinimumWidth(60)
        layout.addWidget(self._duration_label)

        self._size_label = QLabel("")
        self._size_label.setMinimumWidth(80)
        layout.addWidget(self._size_label)

        layout.addStretch()

    def _on_browse_clicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self._output_path or "",
        )
        if folder:
            if not os.access(folder, os.W_OK):
                QMessageBox.warning(
                    self,
                    "Directory Not Writable",
                    f"The selected directory is not writable:\n{folder}\n\n"
                    "Please select a different directory.",
                )
                return
            self.set_output_path(folder)
            self.folder_selected.emit(folder)

    def _on_record_clicked(self) -> None:
        if self._recording:
            self.record_stopped.emit()
        else:
            self.record_started.emit()

    def _update_recording_indicator(self) -> None:
        color = "#F44336" if self._recording else "#9E9E9E"
        self._recording_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 6px;"
        )

    def set_output_path(self, path: str) -> None:
        """Set the output directory path."""
        self._output_path = path
        display_path = path if len(path) < 40 else "..." + path[-37:]
        self._path_label.setText(display_path)
        self._path_label.setToolTip(path)
        self._path_label.setStyleSheet("")
        self._record_button.setEnabled(bool(path))

    def get_output_path(self) -> str:
        """Return the current output directory path."""
        return self._output_path

    def set_recording(self, recording: bool) -> None:
        """Update recording state display."""
        self._recording = recording
        self._record_button.setText("Stop" if recording else "Record")
        self._browse_button.setEnabled(not recording)
        self._update_recording_indicator()
        if not recording:
            self._duration_label.setText("")
            self._size_label.setText("")

    def update_recording_stats(self, duration_seconds: float, file_size_bytes: int) -> None:
        """Update recording duration and file size display."""
        minutes, seconds = divmod(int(duration_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            self._duration_label.setText(f"{hours}:{minutes:02d}:{seconds:02d}")
        else:
            self._duration_label.setText(f"{minutes}:{seconds:02d}")

        if file_size_bytes < 1024:
            size_str = f"{file_size_bytes} B"
        elif file_size_bytes < 1024 * 1024:
            size_str = f"{file_size_bytes / 1024:.1f} KB"
        elif file_size_bytes < 1024 * 1024 * 1024:
            size_str = f"{file_size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{file_size_bytes / (1024 * 1024 * 1024):.2f} GB"

        self._size_label.setText(size_str)


class PlotAreaPlaceholder(QFrame):
    """Placeholder widget for the plot area until PlotWidget is implemented."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        label = QLabel("Plot Area")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 18px;")
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """Main application window for GSDV."""

    # Theme constants
    DARK_THEME = "dark"
    LIGHT_THEME = "light"

    # Signals
    theme_changed = Signal(str)
    bias_requested = Signal()
    display_settings_changed = Signal()  # Emitted when unit or filter settings change
    transform_requested = Signal(ToolTransform)  # Emitted when transform settings change

    def __init__(
        self,
        preferences: UserPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preferences = preferences or UserPreferences()
        self._current_theme = self._preferences.theme
        self._setup_ui()
        self._setup_shortcuts()
        self._apply_theme()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Gamma Sensor Data Viewer")
        self.setMinimumSize(900, 700)
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Header bar with title and settings
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        title_label = QLabel("GSDV")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self._theme_button = QToolButton()
        self._theme_button.setText("Theme")
        self._theme_button.setToolTip("Toggle dark/light theme")
        self._theme_button.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self._theme_button)

        self._settings_button = QToolButton()
        self._settings_button.setText("Settings")
        self._settings_button.setToolTip("Open settings (Ctrl+,)")
        self._settings_button.clicked.connect(self._on_settings_clicked)
        header_layout.addWidget(self._settings_button)

        main_layout.addLayout(header_layout)

        # Connection panel
        self._connection_panel = ConnectionPanel()
        main_layout.addWidget(self._connection_panel)

        # Sensor info display
        self._sensor_info = SensorInfoDisplay()
        main_layout.addWidget(self._sensor_info)

        # Channel selector
        self._channel_selector = ChannelSelector()
        main_layout.addWidget(self._channel_selector)

        # Time window selector
        self._time_window_selector = TimeWindowSelector()
        self._time_window_selector.set_window_seconds(self._preferences.time_window_seconds)

        # Sync preference with actual selector value (in case it snapped to a preset)
        snapped_seconds = self._time_window_selector.window_seconds()
        if snapped_seconds != self._preferences.time_window_seconds:
            self._preferences.time_window_seconds = snapped_seconds

        self._time_window_selector.window_changed.connect(self._on_time_window_changed)
        main_layout.addWidget(self._time_window_selector)

        # Middle section: plot area and numeric display
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(8)

        # Plot area
        self._plot_area = MultiChannelPlot(buffer=None)
        self._plot_area.set_window_seconds(self._preferences.time_window_seconds)
        self._plot_area.set_units(self._preferences.force_unit, self._preferences.torque_unit)
        
        # Connect channel selector
        self._channel_selector.channel_toggled.connect(self._plot_area.set_channel_visible)

        middle_layout.addWidget(self._plot_area, stretch=3)

        # Numeric display on the right
        self._numeric_display = NumericDisplay()
        self._numeric_display.setMaximumWidth(280)
        middle_layout.addWidget(self._numeric_display, stretch=0)

        main_layout.addLayout(middle_layout, stretch=1)

        # Recording controls
        self._recording_controls = RecordingControls()
        main_layout.addWidget(self._recording_controls)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._sample_rate_label = QLabel("Sample Rate: --- Hz")
        self._status_bar.addWidget(self._sample_rate_label)

        self._buffer_status_label = QLabel("Buffer: ---")
        self._status_bar.addWidget(self._buffer_status_label)

        self._packet_loss_label = QLabel("Packet Loss: 0")
        self._status_bar.addWidget(self._packet_loss_label)

        self._dropped_label = QLabel("Dropped: 0")
        self._status_bar.addWidget(self._dropped_label)

        self._warning_label = QLabel("")
        self._warning_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        self._status_bar.addPermanentWidget(self._warning_label)

    def _setup_shortcuts(self) -> None:
        # Connect: Ctrl+Enter
        connect_action = QAction("Connect", self)
        connect_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return))
        connect_action.triggered.connect(self._on_connect_shortcut)
        self.addAction(connect_action)

        # Start recording: Ctrl+R
        record_action = QAction("Record", self)
        record_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_R))
        record_action.triggered.connect(self._on_record_shortcut)
        self.addAction(record_action)

        # Stop recording: Ctrl+S
        stop_action = QAction("Stop", self)
        stop_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_S))
        stop_action.triggered.connect(self._on_stop_shortcut)
        self.addAction(stop_action)

        # Bias/Tare: Ctrl+B
        bias_action = QAction("Bias", self)
        bias_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_B))
        bias_action.triggered.connect(self._on_bias_shortcut)
        self.addAction(bias_action)

        # Settings: Ctrl+, 
        settings_action = QAction("Settings", self)
        settings_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Comma))
        settings_action.triggered.connect(self._on_settings_clicked)
        self.addAction(settings_action)

    def _apply_theme(self) -> None:
        """Apply the current theme to the application."""
        if self._current_theme == self.DARK_THEME:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2b2b2b;
                    color: #e0e0e0;
                }
                QGroupBox {
                    border: 1px solid #555555;
                    border-radius: 4px;
                    margin-top: 8px;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px;
                    color: #a0a0a0;
                }
                QLineEdit {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 4px;
                    color: #e0e0e0;
                }
                QLineEdit:focus {
                    border-color: #6699cc;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 6px 12px;
                    color: #e0e0e0;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
                QPushButton:pressed {
                    background-color: #555555;
                }
                QPushButton:disabled {
                    background-color: #2b2b2b;
                    color: #666666;
                }
                QToolButton {
                    background-color: transparent;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 4px 8px;
                    color: #e0e0e0;
                }
                QToolButton:hover {
                    background-color: #3c3c3c;
                }
                QCheckBox {
                    color: #e0e0e0;
                }
                QCheckBox::indicator {
                    border: 1px solid #555555;
                    border-radius: 2px;
                    background-color: #3c3c3c;
                }
                QCheckBox::indicator:checked {
                    background-color: #6699cc;
                }
                QFrame[frameShape="5"] {
                    color: #555555;
                }
                QStatusBar {
                    background-color: #252525;
                    color: #a0a0a0;
                }
                QLabel {
                    color: #e0e0e0;
                }
            """)
            self._theme_button.setText("Light")
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #f5f5f5;
                    color: #212121;
                }
                QGroupBox {
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    margin-top: 8px;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px;
                    color: #666666;
                }
                QLineEdit {
                    background-color: #ffffff;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                    padding: 4px;
                    color: #212121;
                }
                QLineEdit:focus {
                    border-color: #2196F3;
                }
                QPushButton {
                    background-color: #ffffff;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 6px 12px;
                    color: #212121;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
                QPushButton:pressed {
                    background-color: #bdbdbd;
                }
                QPushButton:disabled {
                    background-color: #f5f5f5;
                    color: #9e9e9e;
                }
                QToolButton {
                    background-color: transparent;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 4px 8px;
                    color: #212121;
                }
                QToolButton:hover {
                    background-color: #e0e0e0;
                }
                QCheckBox {
                    color: #212121;
                }
                QCheckBox::indicator {
                    border: 1px solid #cccccc;
                    border-radius: 2px;
                    background-color: #ffffff;
                }
                QCheckBox::indicator:checked {
                    background-color: #2196F3;
                }
                QFrame[frameShape="5"] {
                    color: #cccccc;
                }
                QStatusBar {
                    background-color: #e0e0e0;
                    color: #666666;
                }
                QLabel {
                    color: #212121;
                }
            """)
            self._theme_button.setText("Dark")

    def toggle_theme(self) -> None:
        """Toggle between dark and light themes."""
        if self._current_theme == self.DARK_THEME:
            new_theme = self.LIGHT_THEME
        else:
            new_theme = self.DARK_THEME
        self.set_theme(new_theme)

    def set_theme(self, theme: str) -> None:
        """Set the theme explicitly.

        Updates preferences and emits theme_changed signal if the theme
        actually changes.
        """
        if theme not in (self.DARK_THEME, self.LIGHT_THEME):
            return
        if theme == self._current_theme:
            return
        self._current_theme = theme
        self._preferences.theme = theme
        self._apply_theme()
        self.theme_changed.emit(theme)

    def current_theme(self) -> str:
        """Return the current theme name."""
        return self._current_theme

    def _on_time_window_changed(self, seconds: float) -> None:
        """Handle time window changes."""
        self._preferences.time_window_seconds = seconds
        self._plot_area.set_window_seconds(seconds)

    def _on_settings_clicked(self) -> None:
        """Handle settings button click."""
        dialog = SettingsDialog(self._preferences, self)
        dialog.settings_applied.connect(self._on_settings_applied)
        dialog.exec()

    def _on_settings_applied(self) -> None:
        """Handle settings changes from the settings dialog.

        Updates the display to reflect new settings:
        - Theme changes are applied immediately
        - Unit preference changes affect how values are displayed
        - Filter settings are stored for use by the processing pipeline
        - Transform settings are sent to the sensor (if connected)
        """
        # Apply theme if changed
        self.set_theme(self._preferences.theme)
        # Apply units to plot
        self._plot_area.set_units(self._preferences.force_unit, self._preferences.torque_unit)
        # Notify listeners that display settings (units, filtering) have changed
        self.display_settings_changed.emit()
        # Emit transform with current values from preferences
        transform = ToolTransform(
            dx=self._preferences.transform_dx,
            dy=self._preferences.transform_dy,
            dz=self._preferences.transform_dz,
            rx=self._preferences.transform_rx,
            ry=self._preferences.transform_ry,
            rz=self._preferences.transform_rz,
        )
        self.transform_requested.emit(transform)
        
    def update_calibration(self, calibration: CalibrationInfo) -> None:
        """Update calibration info in UI widgets.

        Args:
            calibration: CalibrationInfo object containing sensor data.
        """
        self._sensor_info.update_info(calibration)
        self._plot_area.set_calibration(calibration.counts_per_force, calibration.counts_per_torque)

    def _on_connect_shortcut(self) -> None:
        """Handle Ctrl+Enter shortcut for connect."""
        self._connection_panel._on_connect_clicked()

    def _on_record_shortcut(self) -> None:
        """Handle Ctrl+R shortcut for record."""
        if not self._recording_controls._recording:
            self._recording_controls._on_record_clicked()

    def _on_stop_shortcut(self) -> None:
        """Handle Ctrl+S shortcut for stop."""
        if self._recording_controls._recording:
            self._recording_controls._on_record_clicked()

    def _on_bias_shortcut(self) -> None:
        """Handle Ctrl+B shortcut for bias/tare."""
        self.bias_requested.emit()

    # Public API for accessing child widgets
    @property
    def connection_panel(self) -> ConnectionPanel:
        """Return the connection panel widget."""
        return self._connection_panel

    @property
    def channel_selector(self) -> ChannelSelector:
        """Return the channel selector widget."""
        return self._channel_selector

    @property
    def time_window_selector(self) -> TimeWindowSelector:
        """Return the time window selector widget."""
        return self._time_window_selector

    @property
    def plot_controls(self) -> PlotControls:
        """Return the plot controls widget."""
        return self._plot_controls

    @property
    def numeric_display(self) -> NumericDisplay:
        """Return the numeric display widget."""
        return self._numeric_display

    @property
    def recording_controls(self) -> RecordingControls:
        """Return the recording controls widget."""
        return self._recording_controls

    @property
    def sensor_info(self) -> SensorInfoDisplay:
        """Return the sensor info display widget."""
        return self._sensor_info

    def update_sample_rate(self, rate_hz: float) -> None:
        """Update the sample rate display in the status bar."""
        self._sample_rate_label.setText(f"Sample Rate: {rate_hz:.1f} Hz")

    def update_buffer_status(self, fill_percent: float) -> None:
        """Update the buffer status display in the status bar."""
        self._buffer_status_label.setText(f"Buffer: {fill_percent:.0f}%")

    def update_packet_loss(self, count: int) -> None:
        """Update the packet loss counter in the status bar."""
        self._packet_loss_label.setText(f"Packet Loss: {count}")
        if count > 0:
            self._packet_loss_label.setStyleSheet("color: #F44336;")
        else:
            self._packet_loss_label.setStyleSheet("")

    def show_status_message(self, message: str, timeout_ms: int = 3000) -> None:
        """Show a temporary message in the status bar."""
        self._status_bar.showMessage(message, timeout_ms)

    def update_dropped_count(self, count: int) -> None:
        """Update the dropped samples counter in the status bar.

        Dropped samples occur when the app's internal queue fills up faster
        than the processing thread can consume. This indicates the processing
        pipeline is falling behind.
        """
        self._dropped_label.setText(f"Dropped: {count}")
        if count > 0:
            self._dropped_label.setStyleSheet("color: #FF9800;")
        else:
            self._dropped_label.setStyleSheet("")

    def show_warning(self, message: str) -> None:
        """Display a warning message in the status bar.

        Warnings persist until cleared. Use clear_warning() to remove.
        """
        self._warning_label.setText(message)

    def clear_warning(self) -> None:
        """Clear the warning message from the status bar."""
        self._warning_label.setText("")

    @property
    def force_unit(self) -> str:
        """Return the current force unit preference."""
        return self._preferences.force_unit

    @property
    def torque_unit(self) -> str:
        """Return the current torque unit preference."""
        return self._preferences.torque_unit

    @property
    def filter_enabled(self) -> bool:
        """Return whether the low-pass filter is enabled."""
        return self._preferences.filter_enabled

    @property
    def filter_cutoff_hz(self) -> float:
        """Return the filter cutoff frequency in Hz."""
        return self._preferences.filter_cutoff_hz

    @property
    def current_transform(self) -> ToolTransform:
        """Return the current tool transform from preferences."""
        return ToolTransform(
            dx=self._preferences.transform_dx,
            dy=self._preferences.transform_dy,
            dz=self._preferences.transform_dz,
            rx=self._preferences.transform_rx,
            ry=self._preferences.transform_ry,
            rz=self._preferences.transform_rz,
        )