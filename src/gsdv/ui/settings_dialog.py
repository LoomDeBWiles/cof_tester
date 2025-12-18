"""Settings dialog for application preferences."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gsdv.config.preferences import (
    BiasMode,
    ForceUnit,
    LogFormat,
    TorqueUnit,
    UserPreferences,
)
from gsdv.processing.filters import MAX_CUTOFF_HZ, MIN_CUTOFF_HZ


class ConnectionTab(QWidget):
    """Connection settings tab (Section 14.1)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Network group
        network_group = QGroupBox("Network")
        network_layout = QFormLayout(network_group)

        self._last_ip = QLineEdit()
        self._last_ip.setPlaceholderText("192.168.1.1")
        network_layout.addRow("Last IP:", self._last_ip)

        self._udp_port = QSpinBox()
        self._udp_port.setRange(1, 65535)
        self._udp_port.setValue(49152)
        network_layout.addRow("UDP Port:", self._udp_port)

        self._tcp_port = QSpinBox()
        self._tcp_port.setRange(1, 65535)
        self._tcp_port.setValue(49151)
        network_layout.addRow("TCP Port:", self._tcp_port)

        self._http_port = QSpinBox()
        self._http_port.setRange(1, 65535)
        self._http_port.setValue(80)
        network_layout.addRow("HTTP Port:", self._http_port)

        layout.addWidget(network_group)

        # Timeout group
        timeout_group = QGroupBox("Timeout")
        timeout_layout = QFormLayout(timeout_group)

        self._connect_timeout = QSpinBox()
        self._connect_timeout.setRange(100, 30000)
        self._connect_timeout.setSuffix(" ms")
        self._connect_timeout.setValue(2000)
        timeout_layout.addRow("Connect Timeout:", self._connect_timeout)

        self._auto_reconnect = QCheckBox("Auto-reconnect on disconnect")
        self._auto_reconnect.setChecked(True)
        timeout_layout.addRow(self._auto_reconnect)

        layout.addWidget(timeout_group)

        # Discovery group
        discovery_group = QGroupBox("Discovery")
        discovery_layout = QVBoxLayout(discovery_group)

        discovery_layout.addWidget(QLabel("Subnets to scan:"))

        self._discovery_subnets = QListWidget()
        self._discovery_subnets.setMaximumHeight(100)
        discovery_layout.addWidget(self._discovery_subnets)

        subnet_input_layout = QHBoxLayout()
        self._subnet_input = QLineEdit()
        self._subnet_input.setPlaceholderText("192.168.1.0/24")
        subnet_input_layout.addWidget(self._subnet_input)

        self._add_subnet_btn = QPushButton("Add")
        self._add_subnet_btn.clicked.connect(self._add_subnet)
        subnet_input_layout.addWidget(self._add_subnet_btn)

        self._remove_subnet_btn = QPushButton("Remove")
        self._remove_subnet_btn.clicked.connect(self._remove_subnet)
        subnet_input_layout.addWidget(self._remove_subnet_btn)

        discovery_layout.addLayout(subnet_input_layout)

        layout.addWidget(discovery_group)
        layout.addStretch()

    def _add_subnet(self) -> None:
        """Add subnet from input field to the list."""
        subnet = self._subnet_input.text().strip()
        if subnet:
            self._discovery_subnets.addItem(subnet)
            self._subnet_input.clear()

    def _remove_subnet(self) -> None:
        """Remove selected subnet from the list."""
        current_row = self._discovery_subnets.currentRow()
        if current_row >= 0:
            self._discovery_subnets.takeItem(current_row)

    def load_preferences(self, prefs: UserPreferences) -> None:
        """Load values from preferences."""
        self._last_ip.setText(prefs.last_ip)
        self._udp_port.setValue(prefs.udp_port)
        self._tcp_port.setValue(prefs.tcp_port)
        self._http_port.setValue(prefs.http_port)
        self._connect_timeout.setValue(prefs.connect_timeout_ms)
        self._auto_reconnect.setChecked(prefs.auto_reconnect)
        self._discovery_subnets.clear()
        for subnet in prefs.discovery_subnets:
            self._discovery_subnets.addItem(subnet)

    def save_preferences(self, prefs: UserPreferences) -> None:
        """Save values to preferences."""
        prefs.last_ip = self._last_ip.text()
        prefs.udp_port = self._udp_port.value()
        prefs.tcp_port = self._tcp_port.value()
        prefs.http_port = self._http_port.value()
        prefs.connect_timeout_ms = self._connect_timeout.value()
        prefs.auto_reconnect = self._auto_reconnect.isChecked()
        prefs.discovery_subnets = [
            self._discovery_subnets.item(i).text()
            for i in range(self._discovery_subnets.count())
        ]


class DisplayTab(QWidget):
    """Display settings tab (Sections 14.2, 14.3, 14.4)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Visualization group
        viz_group = QGroupBox("Visualization")
        viz_layout = QFormLayout(viz_group)

        self._time_window = QDoubleSpinBox()
        self._time_window.setRange(1.0, 300.0)
        self._time_window.setSuffix(" s")
        self._time_window.setDecimals(1)
        self._time_window.setValue(10.0)
        viz_layout.addRow("Time Window:", self._time_window)

        self._y_autoscale = QCheckBox("Auto-scale Y axis")
        self._y_autoscale.setChecked(True)
        self._y_autoscale.stateChanged.connect(self._on_autoscale_changed)
        viz_layout.addRow(self._y_autoscale)

        self._y_manual_min = QDoubleSpinBox()
        self._y_manual_min.setRange(-1000000.0, 1000000.0)
        self._y_manual_min.setDecimals(2)
        self._y_manual_min.setValue(0.0)
        viz_layout.addRow("Y-axis Min:", self._y_manual_min)

        self._y_manual_max = QDoubleSpinBox()
        self._y_manual_max.setRange(-1000000.0, 1000000.0)
        self._y_manual_max.setDecimals(2)
        self._y_manual_max.setValue(100.0)
        viz_layout.addRow("Y-axis Max:", self._y_manual_max)

        self._show_grid = QCheckBox("Show grid")
        self._show_grid.setChecked(True)
        viz_layout.addRow(self._show_grid)

        self._show_crosshair = QCheckBox("Show crosshair")
        self._show_crosshair.setChecked(False)
        viz_layout.addRow(self._show_crosshair)

        self._max_points = QSpinBox()
        self._max_points.setRange(1000, 100000)
        self._max_points.setSingleStep(1000)
        self._max_points.setValue(10000)
        viz_layout.addRow("Max Points/Channel:", self._max_points)

        layout.addWidget(viz_group)

        # Units group
        units_group = QGroupBox("Units")
        units_layout = QFormLayout(units_group)

        self._force_unit = QComboBox()
        for unit in ForceUnit:
            self._force_unit.addItem(unit.value, unit.value)
        units_layout.addRow("Force Unit:", self._force_unit)

        self._torque_unit = QComboBox()
        for unit in TorqueUnit:
            self._torque_unit.addItem(unit.value, unit.value)
        units_layout.addRow("Torque Unit:", self._torque_unit)

        layout.addWidget(units_group)

        # Filtering group
        filter_group = QGroupBox("Filtering")
        filter_layout = QFormLayout(filter_group)

        self._filter_enabled = QCheckBox("Enable low-pass filter")
        self._filter_enabled.setChecked(False)
        filter_layout.addRow(self._filter_enabled)

        self._filter_cutoff = QDoubleSpinBox()
        self._filter_cutoff.setRange(MIN_CUTOFF_HZ, MAX_CUTOFF_HZ)
        self._filter_cutoff.setSuffix(" Hz")
        self._filter_cutoff.setDecimals(1)
        self._filter_cutoff.setValue(MAX_CUTOFF_HZ)
        filter_layout.addRow("Cutoff Frequency:", self._filter_cutoff)

        layout.addWidget(filter_group)
        layout.addStretch()

    def _on_autoscale_changed(self) -> None:
        """Update visibility of manual Y-axis range controls based on autoscale state."""
        autoscale_enabled = self._y_autoscale.isChecked()
        self._y_manual_min.setEnabled(not autoscale_enabled)
        self._y_manual_max.setEnabled(not autoscale_enabled)

    def load_preferences(self, prefs: UserPreferences) -> None:
        """Load values from preferences."""
        self._time_window.setValue(prefs.time_window_seconds)
        self._y_autoscale.setChecked(prefs.y_autoscale)

        if prefs.y_manual_min is not None:
            self._y_manual_min.setValue(prefs.y_manual_min)
        if prefs.y_manual_max is not None:
            self._y_manual_max.setValue(prefs.y_manual_max)

        self._on_autoscale_changed()

        self._show_grid.setChecked(prefs.show_grid)
        self._show_crosshair.setChecked(prefs.show_crosshair)
        self._max_points.setValue(prefs.plot_max_points_per_channel)

        index = self._force_unit.findData(prefs.force_unit)
        if index >= 0:
            self._force_unit.setCurrentIndex(index)

        index = self._torque_unit.findData(prefs.torque_unit)
        if index >= 0:
            self._torque_unit.setCurrentIndex(index)

        self._filter_enabled.setChecked(prefs.filter_enabled)
        self._filter_cutoff.setValue(prefs.filter_cutoff_hz)

    def save_preferences(self, prefs: UserPreferences) -> None:
        """Save values to preferences."""
        prefs.time_window_seconds = self._time_window.value()
        prefs.y_autoscale = self._y_autoscale.isChecked()
        prefs.y_manual_min = self._y_manual_min.value()
        prefs.y_manual_max = self._y_manual_max.value()
        prefs.show_grid = self._show_grid.isChecked()
        prefs.show_crosshair = self._show_crosshair.isChecked()
        prefs.plot_max_points_per_channel = self._max_points.value()
        prefs.force_unit = self._force_unit.currentData()
        prefs.torque_unit = self._torque_unit.currentData()
        prefs.filter_enabled = self._filter_enabled.isChecked()
        prefs.filter_cutoff_hz = self._filter_cutoff.value()


class RecordingTab(QWidget):
    """Recording settings tab (Section 14.6)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Output group
        output_group = QGroupBox("Output")
        output_layout = QFormLayout(output_group)

        self._filename_prefix = QLineEdit()
        self._filename_prefix.setPlaceholderText("recording")
        output_layout.addRow("Filename Prefix:", self._filename_prefix)

        self._log_format = QComboBox()
        for fmt in LogFormat:
            self._log_format.addItem(fmt.value, fmt.value)
        output_layout.addRow("Log Format:", self._log_format)

        layout.addWidget(output_group)

        # Performance group
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout(perf_group)

        self._flush_interval = QSpinBox()
        self._flush_interval.setRange(50, 5000)
        self._flush_interval.setSuffix(" ms")
        self._flush_interval.setValue(250)
        perf_layout.addRow("Flush Interval:", self._flush_interval)

        self._decimation_factor = QSpinBox()
        self._decimation_factor.setRange(1, 100)
        self._decimation_factor.setValue(1)
        perf_layout.addRow("Decimation Factor:", self._decimation_factor)

        layout.addWidget(perf_group)

        # Rotation group
        rotation_group = QGroupBox("File Rotation")
        rotation_layout = QFormLayout(rotation_group)

        self._rotation_enabled = QCheckBox("Enable file rotation")
        self._rotation_enabled.setChecked(True)
        rotation_layout.addRow(self._rotation_enabled)

        self._rotate_interval = QSpinBox()
        self._rotate_interval.setRange(1, 1440)
        self._rotate_interval.setSuffix(" min")
        self._rotate_interval.setValue(60)
        rotation_layout.addRow("Rotate Interval:", self._rotate_interval)

        self._rotate_max_bytes = QSpinBox()
        self._rotate_max_bytes.setRange(1, 10000)
        self._rotate_max_bytes.setSuffix(" MB")
        self._rotate_max_bytes.setValue(2000)
        rotation_layout.addRow("Max File Size:", self._rotate_max_bytes)

        layout.addWidget(rotation_group)
        layout.addStretch()

    def load_preferences(self, prefs: UserPreferences) -> None:
        """Load values from preferences."""
        self._filename_prefix.setText(prefs.filename_prefix)

        index = self._log_format.findData(prefs.log_format)
        if index >= 0:
            self._log_format.setCurrentIndex(index)

        self._flush_interval.setValue(prefs.flush_interval_ms)
        self._decimation_factor.setValue(prefs.log_decimation_factor)
        self._rotation_enabled.setChecked(prefs.rotation_enabled)
        self._rotate_interval.setValue(prefs.rotate_interval_minutes)
        self._rotate_max_bytes.setValue(prefs.rotate_max_bytes // 1_000_000)

    def save_preferences(self, prefs: UserPreferences) -> None:
        """Save values to preferences."""
        prefs.filename_prefix = self._filename_prefix.text()
        prefs.log_format = self._log_format.currentData()
        prefs.flush_interval_ms = self._flush_interval.value()
        prefs.log_decimation_factor = self._decimation_factor.value()
        prefs.rotation_enabled = self._rotation_enabled.isChecked()
        prefs.rotate_interval_minutes = self._rotate_interval.value()
        prefs.rotate_max_bytes = self._rotate_max_bytes.value() * 1_000_000


class AdvancedTab(QWidget):
    """Advanced settings tab (Sections 14.5, 14.7)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Bias group
        bias_group = QGroupBox("Bias/Tare")
        bias_layout = QFormLayout(bias_group)

        self._bias_mode = QComboBox()
        self._bias_mode.addItem("Device (hardware)", BiasMode.device.value)
        self._bias_mode.addItem("Software", BiasMode.soft.value)
        bias_layout.addRow("Bias Mode:", self._bias_mode)

        layout.addWidget(bias_group)

        # Tool Transform group
        transform_group = QGroupBox("Tool Transform")
        transform_layout = QFormLayout(transform_group)

        transform_layout.addRow(QLabel("Translation (mm):"))

        translation_widget = QWidget()
        translation_layout = QHBoxLayout(translation_widget)
        translation_layout.setContentsMargins(0, 0, 0, 0)

        self._transform_dx = QDoubleSpinBox()
        self._transform_dx.setRange(-327.67, 327.67)
        self._transform_dx.setDecimals(2)
        self._transform_dx.setPrefix("dX: ")
        translation_layout.addWidget(self._transform_dx)

        self._transform_dy = QDoubleSpinBox()
        self._transform_dy.setRange(-327.67, 327.67)
        self._transform_dy.setDecimals(2)
        self._transform_dy.setPrefix("dY: ")
        translation_layout.addWidget(self._transform_dy)

        self._transform_dz = QDoubleSpinBox()
        self._transform_dz.setRange(-327.67, 327.67)
        self._transform_dz.setDecimals(2)
        self._transform_dz.setPrefix("dZ: ")
        translation_layout.addWidget(self._transform_dz)

        transform_layout.addRow(translation_widget)

        transform_layout.addRow(QLabel("Rotation (degrees):"))

        rotation_widget = QWidget()
        rotation_layout = QHBoxLayout(rotation_widget)
        rotation_layout.setContentsMargins(0, 0, 0, 0)

        self._transform_rx = QDoubleSpinBox()
        self._transform_rx.setRange(-327.67, 327.67)
        self._transform_rx.setDecimals(2)
        self._transform_rx.setPrefix("rX: ")
        rotation_layout.addWidget(self._transform_rx)

        self._transform_ry = QDoubleSpinBox()
        self._transform_ry.setRange(-327.67, 327.67)
        self._transform_ry.setDecimals(2)
        self._transform_ry.setPrefix("rY: ")
        rotation_layout.addWidget(self._transform_ry)

        self._transform_rz = QDoubleSpinBox()
        self._transform_rz.setRange(-327.67, 327.67)
        self._transform_rz.setDecimals(2)
        self._transform_rz.setPrefix("rZ: ")
        rotation_layout.addWidget(self._transform_rz)

        transform_layout.addRow(rotation_widget)

        layout.addWidget(transform_group)

        # Theme group
        theme_group = QGroupBox("Appearance")
        theme_layout = QFormLayout(theme_group)

        self._theme = QComboBox()
        self._theme.addItem("Dark", "dark")
        self._theme.addItem("Light", "light")
        theme_layout.addRow("Theme:", self._theme)

        layout.addWidget(theme_group)
        layout.addStretch()

    def load_preferences(self, prefs: UserPreferences) -> None:
        """Load values from preferences."""
        index = self._bias_mode.findData(prefs.bias_mode)
        if index >= 0:
            self._bias_mode.setCurrentIndex(index)

        self._transform_dx.setValue(prefs.transform_dx)
        self._transform_dy.setValue(prefs.transform_dy)
        self._transform_dz.setValue(prefs.transform_dz)
        self._transform_rx.setValue(prefs.transform_rx)
        self._transform_ry.setValue(prefs.transform_ry)
        self._transform_rz.setValue(prefs.transform_rz)

        index = self._theme.findData(prefs.theme)
        if index >= 0:
            self._theme.setCurrentIndex(index)

    def save_preferences(self, prefs: UserPreferences) -> None:
        """Save values to preferences."""
        prefs.bias_mode = self._bias_mode.currentData()
        prefs.transform_dx = self._transform_dx.value()
        prefs.transform_dy = self._transform_dy.value()
        prefs.transform_dz = self._transform_dz.value()
        prefs.transform_rx = self._transform_rx.value()
        prefs.transform_ry = self._transform_ry.value()
        prefs.transform_rz = self._transform_rz.value()
        prefs.theme = self._theme.currentData()


class SettingsDialog(QDialog):
    """Settings dialog with tabbed interface (Section 8.2).

    Provides a tabbed interface for configuring application settings:
    - Connection: network and timeout settings
    - Display: visualization, units, and filtering
    - Recording: output format and file rotation
    - Advanced: bias mode, tool transform, and theme

    Signals:
        settings_applied: Emitted when settings are applied (OK or Apply clicked).
    """

    settings_applied = Signal()

    def __init__(
        self,
        preferences: UserPreferences,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preferences = preferences
        self._setup_ui()
        self._load_preferences()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 450)
        self.resize(550, 500)

        layout = QVBoxLayout(self)

        # Tab widget
        self._tab_widget = QTabWidget()

        self._connection_tab = ConnectionTab()
        self._tab_widget.addTab(self._connection_tab, "Connection")

        self._display_tab = DisplayTab()
        self._tab_widget.addTab(self._display_tab, "Display")

        self._recording_tab = RecordingTab()
        self._tab_widget.addTab(self._recording_tab, "Recording")

        self._advanced_tab = AdvancedTab()
        self._tab_widget.addTab(self._advanced_tab, "Advanced")

        layout.addWidget(self._tab_widget)

        # Button box
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        self._button_box.accepted.connect(self._on_ok)
        self._button_box.rejected.connect(self.reject)
        self._button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._on_apply
        )

        layout.addWidget(self._button_box)

    def _load_preferences(self) -> None:
        """Load preferences into all tabs."""
        self._connection_tab.load_preferences(self._preferences)
        self._display_tab.load_preferences(self._preferences)
        self._recording_tab.load_preferences(self._preferences)
        self._advanced_tab.load_preferences(self._preferences)

    def _save_preferences(self) -> None:
        """Save preferences from all tabs."""
        self._connection_tab.save_preferences(self._preferences)
        self._display_tab.save_preferences(self._preferences)
        self._recording_tab.save_preferences(self._preferences)
        self._advanced_tab.save_preferences(self._preferences)

    def _on_ok(self) -> None:
        """Handle OK button click."""
        self._save_preferences()
        self.settings_applied.emit()
        self.accept()

    def _on_apply(self) -> None:
        """Handle Apply button click."""
        self._save_preferences()
        self.settings_applied.emit()

    def preferences(self) -> UserPreferences:
        """Return the preferences object being edited."""
        return self._preferences
