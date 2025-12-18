"""Real-time multi-channel plot widget using pyqtgraph.

Provides a PlotWidget for displaying time-series force/torque data from
the acquisition engine. Designed for 30fps refresh with autoscale.
"""

from typing import Any, Optional, Tuple, Dict

import numpy as np
import pyqtgraph as pg
from numpy.typing import NDArray
from PySide6.QtCore import QTimer, QPointF
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel


class MultiChannelPlot(QWidget):
    """Multi-channel real-time plot widget.

    Displays time-series data from a ring buffer for all 6 channels (Fx, Fy, Fz,
    Tx, Ty, Tz). Updates at 30fps via QTimer.

    The plot shows time on the X-axis (in seconds, relative to the most recent
    sample) and the channel values on the Y-axis. Autoscale is enabled by default.

    Example:
        >>> buffer = RingBuffer(capacity=60000)
        >>> plot = MultiChannelPlot(buffer=buffer)
        >>> plot.set_calibration(cpf=100.0, cpt=1000.0)
        >>> plot.start()
    """

    CHANNEL_NAMES = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")
    CHANNEL_COLORS = {
        "Fx": "#F44336",  # Red
        "Fy": "#4CAF50",  # Green
        "Fz": "#2196F3",  # Blue
        "Tx": "#FF9800",  # Orange
        "Ty": "#9C27B0",  # Purple
        "Tz": "#009688",  # Teal
    }
    DEFAULT_WINDOW_SECONDS = 10.0
    TARGET_FPS = 30

    def __init__(
        self,
        buffer: Optional[object] = None,
        sample_rate: float = 1000.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the plot widget.

        Args:
            buffer: Ring buffer to read data from.
            sample_rate: Sampling rate in Hz (default: 1000.0).
            parent: Parent widget.
        """
        super().__init__(parent)
        self._buffer = buffer
        self._sample_rate = sample_rate
        self._window_seconds = self.DEFAULT_WINDOW_SECONDS
        
        # Calibration factors (counts per unit)
        self._counts_per_force = 1.0
        self._counts_per_torque = 1.0
        
        # Units
        self._force_unit = ""
        self._torque_unit = ""

        # Y-axis scaling state
        self._y_autoscale = True
        self._y_range_min: Optional[float] = None
        self._y_range_max: Optional[float] = None

        # Curves
        self._lines: Dict[str, pg.PlotDataItem] = {}

        # Grid and crosshair state
        self._grid_enabled = True
        self._crosshair_enabled = False

        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self) -> None:
        """Set up the plot widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Configure pyqtgraph for performance
        pg.setConfigOptions(antialias=False, useOpenGL=False)

        # Create PlotWidget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        layout.addWidget(self._plot_widget)

        # Get PlotItem for axis configuration
        self._plot_item = self._plot_widget.getPlotItem()

        # Configure axes
        self._plot_item.setLabel("bottom", "Time", units="s")
        self._plot_item.setLabel("left", "Value") # Generic label as units mix

        # Enable autoscale by default (Y-axis only since X is time-windowed)
        self._plot_item.enableAutoRange(axis="y")
        
        # Add Legend
        self._legend = self._plot_item.addLegend(offset=(10, 10))

        # Create the line plot items
        for channel in self.CHANNEL_NAMES:
            pen = pg.mkPen(color=self.CHANNEL_COLORS[channel], width=1.5)
            # Create curve but don't add to legend automatically yet, 
            # as pyqtgraph adds it if name is provided.
            line = self._plot_item.plot(name=channel, pen=pen)
            line.setClipToView(True)
            line.setDownsampling(auto=True, method="peak")
            self._lines[channel] = line

        # Show grid by default
        self._plot_item.showGrid(x=True, y=True, alpha=0.3)

        # Set up crosshair lines (hidden by default)
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('y', width=1))
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('y', width=1))
        self._plot_item.addItem(self._vline, ignoreBounds=True)
        self._plot_item.addItem(self._hline, ignoreBounds=True)
        self._vline.setVisible(False)
        self._hline.setVisible(False)

        # Coordinate label for crosshair
        self._coord_label = QLabel(self)
        self._coord_label.setStyleSheet(
            "background-color: rgba(0, 0, 0, 180); color: yellow; "
            "padding: 4px; border-radius: 3px; font-size: 11px;"
        )
        self._coord_label.setVisible(False)

        # Connect mouse move signal
        self._plot_item.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _setup_timer(self) -> None:
        """Set up the update timer for 30fps refresh."""
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self.TARGET_FPS))
        self._timer.timeout.connect(self._update_plot)

    def set_buffer(self, buffer: object) -> None:
        """Set the data buffer to read data from.

        Args:
            buffer: Either a RingBuffer (raw-only) or MultiResolutionBuffer (tiered).
        """
        self._buffer = buffer

    def set_calibration(self, cpf: float, cpt: float) -> None:
        """Set the calibration factors.

        Args:
            cpf: Counts per force unit.
            cpt: Counts per torque unit.
        """
        if cpf <= 0 or cpt <= 0:
            raise ValueError("Calibration factors must be positive")
        self._counts_per_force = cpf
        self._counts_per_torque = cpt

    def set_units(self, force_unit: str, torque_unit: str) -> None:
        """Set the display units.
        
        Args:
            force_unit: Unit string for force (e.g., "N").
            torque_unit: Unit string for torque (e.g., "N-m").
        """
        self._force_unit = force_unit
        self._torque_unit = torque_unit
        # We could update Y label, but since it's mixed, we might just leave "Value"
        # or do "Force ({force_unit}) / Torque ({torque_unit})"
        label = "Value"
        if force_unit and torque_unit:
             label = f"Force ({force_unit}) / Torque ({torque_unit})"
        elif force_unit:
             label = f"Force ({force_unit})"
        elif torque_unit:
             label = f"Torque ({torque_unit})"
        
        self._plot_item.setLabel("left", label)

    def set_channel_visible(self, channel: str, visible: bool) -> None:
        """Set the visibility of a channel.
        
        Args:
            channel: Channel name (Fx, Fy, Fz, Tx, Ty, Tz).
            visible: Whether the channel should be visible.
        """
        if channel in self._lines:
            self._lines[channel].setVisible(visible)

    def set_sample_rate(self, rate_hz: float) -> None:
        """Set the sampling rate.

        Args:
            rate_hz: Sampling rate in Hz.
        """
        if rate_hz <= 0:
            raise ValueError(f"sample_rate must be positive, got {rate_hz}")
        self._sample_rate = rate_hz

    def set_window_seconds(self, seconds: float) -> None:
        """Set the time window displayed on the X-axis.

        Args:
            seconds: Window duration in seconds.
        """
        if seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {seconds}")
        self._window_seconds = seconds

    def enable_y_autoscale(self) -> None:
        """Enable automatic Y-axis scaling based on data range."""
        self._y_autoscale = True
        self._y_range_min = None
        self._y_range_max = None
        self._plot_item.enableAutoRange(axis="y")

    def set_y_range(self, y_min: float, y_max: float) -> None:
        """Set a manual Y-axis range, disabling autoscale.

        Args:
            y_min: Minimum Y value to display.
            y_max: Maximum Y value to display.
        """
        if y_min >= y_max:
            raise ValueError(f"y_min must be less than y_max, got y_min={y_min}, y_max={y_max}")
        self._y_autoscale = False
        self._y_range_min = y_min
        self._y_range_max = y_max
        self._plot_item.disableAutoRange(axis="y")
        self._plot_item.setYRange(y_min, y_max, padding=0)

    def is_y_autoscale_enabled(self) -> bool:
        """Return whether Y-axis autoscale is enabled."""
        return self._y_autoscale

    def get_y_range(self) -> Optional[Tuple[float, float]]:
        """Return the current manual Y-axis range, or None if autoscaling."""
        if self._y_autoscale:
            return None
        return (self._y_range_min, self._y_range_max)

    def set_grid_enabled(self, enabled: bool) -> None:
        """Enable or disable the plot grid.

        Args:
            enabled: True to show grid, False to hide it.
        """
        self._grid_enabled = enabled
        self._plot_item.showGrid(x=enabled, y=enabled, alpha=0.3)

    def is_grid_enabled(self) -> bool:
        """Return whether the grid is currently enabled."""
        return self._grid_enabled

    def set_crosshair_enabled(self, enabled: bool) -> None:
        """Enable or disable the crosshair cursor.

        Args:
            enabled: True to show crosshair, False to hide it.
        """
        self._crosshair_enabled = enabled
        if not enabled:
            self._vline.setVisible(False)
            self._hline.setVisible(False)
            self._coord_label.setVisible(False)

    def is_crosshair_enabled(self) -> bool:
        """Return whether the crosshair is currently enabled."""
        return self._crosshair_enabled

    def _on_mouse_moved(self, pos: QPointF) -> None:
        """Handle mouse movement to update crosshair position.

        Args:
            pos: Mouse position in scene coordinates.
        """
        if not self._crosshair_enabled:
            return

        if self._plot_item.sceneBoundingRect().contains(pos):
            vb = self._plot_item.vb
            mouse_point = vb.mapSceneToView(pos)
            x = mouse_point.x()
            y = mouse_point.y()

            # Update crosshair lines
            self._vline.setPos(x)
            self._hline.setPos(y)
            self._vline.setVisible(True)
            self._hline.setVisible(True)

            # Update coordinate label
            self._coord_label.setText(f"t={x:.3f}s, y={y:.3f}")
            self._coord_label.adjustSize()

            # Position label near cursor but avoid edges
            widget_pos = self._plot_widget.mapFromScene(pos)
            label_x = int(widget_pos.x() + 10)
            label_y = int(widget_pos.y() + 10)

            # Keep label within widget bounds
            max_x = self.width() - self._coord_label.width() - 5
            max_y = self.height() - self._coord_label.height() - 5
            label_x = min(label_x, max_x)
            label_y = min(label_y, max_y)

            self._coord_label.move(label_x, label_y)
            self._coord_label.setVisible(True)
        else:
            self._vline.setVisible(False)
            self._hline.setVisible(False)
            self._coord_label.setVisible(False)

    def start(self) -> None:
        """Start the plot update timer."""
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        """Stop the plot update timer."""
        self._timer.stop()

    def is_running(self) -> bool:
        """Return whether the plot is actively updating."""
        return self._timer.isActive()

    def clear(self) -> None:
        """Clear the plot data."""
        for line in self._lines.values():
            line.setData([], [])

    def _update_plot(self) -> None:
        """Update the plot with latest data from the buffer."""
        if self._buffer is None:
            return

        data: Any
        if hasattr(self._buffer, "get_window_data"):
            data = self._buffer.get_window_data(self._window_seconds)  # type: ignore[attr-defined]
        else:
            # Calculate how many samples to fetch for the window
            n_samples = int(self._window_seconds * self._sample_rate)
            data = self._buffer.get_latest(n_samples)

        if data is None:
            return

        # MultiResolutionBuffer shape
        if isinstance(data, dict) and "kind" in data:
            kind = data["kind"]
            if kind == "raw":
                self._update_raw_plot(data)
                return
            if kind == "minmax":
                self._update_minmax_plot(data)
                return
            raise ValueError(f"Unknown plot data kind: {kind!r}")

        # RingBuffer shape
        self._update_raw_plot(data)

    def _update_raw_plot(self, data: dict[str, Any]) -> None:
        timestamps = data["timestamps"]
        counts = data["counts"]

        if len(timestamps) == 0:
            return

        # Convert timestamps to relative seconds from most recent
        t_seconds = self._timestamps_to_relative_seconds(timestamps)

        # Update each channel
        for i, channel in enumerate(self.CHANNEL_NAMES):
            line = self._lines[channel]
            if not line.isVisible():
                continue

            # Determine calibration factor
            if channel in ("Fx", "Fy", "Fz"):
                cpf = self._counts_per_force
            else:
                cpf = self._counts_per_torque

            y_values = counts[:, i].astype(np.float64) / cpf
            line.setData(t_seconds, y_values, connect="all")

    def _update_minmax_plot(self, data: dict[str, Any]) -> None:
        t_ref_ns = int(data["t_ref_ns"])
        t_start_ns: NDArray[np.int64] = data["t_start_ns"]
        t_end_ns: NDArray[np.int64] = data["t_end_ns"]
        counts_min: NDArray[np.int32] = data["counts_min"]
        counts_max: NDArray[np.int32] = data["counts_max"]

        if len(t_start_ns) == 0:
            return

        # Plot min/max as vertical segments per bucket (connect="pairs").
        t_mid_ns = (t_start_ns.astype(np.int64) + t_end_ns.astype(np.int64)) // 2
        t_mid_seconds = (t_mid_ns - t_ref_ns).astype(np.float64) / 1e9
        x_pairs = np.repeat(t_mid_seconds, 2)

        for i, channel in enumerate(self.CHANNEL_NAMES):
            line = self._lines[channel]
            if not line.isVisible():
                continue

            if channel in ("Fx", "Fy", "Fz"):
                cpf = self._counts_per_force
            else:
                cpf = self._counts_per_torque

            y_min = counts_min[:, i].astype(np.float64) / cpf
            y_max = counts_max[:, i].astype(np.float64) / cpf
            y_pairs = np.column_stack([y_min, y_max]).reshape(-1)
            line.setData(x_pairs, y_pairs, connect="pairs")

    def _timestamps_to_relative_seconds(
        self, timestamps: NDArray[np.int64]
    ) -> NDArray[np.float64]:
        """Convert monotonic nanosecond timestamps to relative seconds.

        The most recent sample is at t=0, with older samples at negative times.

        Args:
            timestamps: Array of monotonic timestamps in nanoseconds.

        Returns:
            Array of times in seconds relative to most recent sample.
        """
        if len(timestamps) == 0:
            return np.array([], dtype=np.float64)

        # Most recent timestamp is the reference point
        t_ref = timestamps[-1]
        return (timestamps - t_ref).astype(np.float64) / 1e9
