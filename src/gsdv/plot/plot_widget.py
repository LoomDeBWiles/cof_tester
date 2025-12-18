"""Real-time single-channel plot widget using pyqtgraph.

Provides a PlotWidget for displaying time-series force/torque data from
the acquisition engine. Designed for 30fps refresh with autoscale.
"""

from typing import Optional

import numpy as np
import pyqtgraph as pg
from numpy.typing import NDArray
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gsdv.acquisition.ring_buffer import RingBuffer


class SingleChannelPlot(QWidget):
    """Single-channel real-time plot widget.

    Displays time-series data from a ring buffer for one channel (Fx, Fy, Fz,
    Tx, Ty, or Tz). Updates at 30fps via QTimer.

    The plot shows time on the X-axis (in seconds, relative to the most recent
    sample) and the channel value on the Y-axis. Autoscale is enabled by default.

    Example:
        >>> buffer = RingBuffer(capacity=60000)
        >>> plot = SingleChannelPlot(buffer=buffer, channel_index=0)
        >>> plot.set_channel_label("Fx")
        >>> plot.set_unit("N")
        >>> plot.start()
    """

    CHANNEL_NAMES = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")
    DEFAULT_WINDOW_SECONDS = 10.0
    TARGET_FPS = 30
    DEFAULT_LINE_COLOR = "#2196F3"

    def __init__(
        self,
        buffer: Optional[RingBuffer] = None,
        channel_index: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the plot widget.

        Args:
            buffer: Ring buffer to read data from.
            channel_index: Index of the channel to display (0-5 for Fx-Tz).
            parent: Parent widget.
        """
        super().__init__(parent)
        self._buffer = buffer
        self._channel_index = channel_index
        self._channel_label = self.CHANNEL_NAMES[channel_index]
        self._unit = ""
        self._window_seconds = self.DEFAULT_WINDOW_SECONDS
        self._counts_per_unit = 1.0

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
        self._update_y_label()

        # Enable autoscale
        self._plot_item.enableAutoRange()

        # Create the line plot item
        self._line = self._plot_item.plot(
            pen=pg.mkPen(color=self.DEFAULT_LINE_COLOR, width=1.5),
        )

        # Show grid
        self._plot_item.showGrid(x=True, y=True, alpha=0.3)

    def _setup_timer(self) -> None:
        """Set up the update timer for 30fps refresh."""
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self.TARGET_FPS))
        self._timer.timeout.connect(self._update_plot)

    def _update_y_label(self) -> None:
        """Update the Y-axis label with channel name and unit."""
        if self._unit:
            self._plot_item.setLabel("left", self._channel_label, units=self._unit)
        else:
            self._plot_item.setLabel("left", self._channel_label)

    def set_buffer(self, buffer: RingBuffer) -> None:
        """Set the ring buffer to read data from.

        Args:
            buffer: Ring buffer containing sample data.
        """
        self._buffer = buffer

    def set_channel_index(self, index: int) -> None:
        """Set which channel to display.

        Args:
            index: Channel index (0-5 for Fx, Fy, Fz, Tx, Ty, Tz).

        Raises:
            ValueError: If index is out of range.
        """
        if not 0 <= index <= 5:
            raise ValueError(f"channel_index must be 0-5, got {index}")
        self._channel_index = index
        self._channel_label = self.CHANNEL_NAMES[index]
        self._update_y_label()

    def set_channel_label(self, label: str) -> None:
        """Set a custom channel label.

        Args:
            label: Label to display on Y-axis.
        """
        self._channel_label = label
        self._update_y_label()

    def set_unit(self, unit: str) -> None:
        """Set the display unit.

        Args:
            unit: Unit string (e.g., "N", "N-m").
        """
        self._unit = unit
        self._update_y_label()

    def set_counts_per_unit(self, cpf: float) -> None:
        """Set the conversion factor from counts to display units.

        Args:
            cpf: Counts per unit (divide counts by this to get display value).
        """
        if cpf <= 0:
            raise ValueError(f"counts_per_unit must be positive, got {cpf}")
        self._counts_per_unit = cpf

    def set_window_seconds(self, seconds: float) -> None:
        """Set the time window displayed on the X-axis.

        Args:
            seconds: Window duration in seconds.
        """
        if seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {seconds}")
        self._window_seconds = seconds

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
        self._line.setData([], [])

    def _update_plot(self) -> None:
        """Update the plot with latest data from the buffer."""
        if self._buffer is None:
            return

        # Calculate how many samples to fetch for the window
        # Assume 1000Hz sample rate
        sample_rate = 1000
        n_samples = int(self._window_seconds * sample_rate)

        data = self._buffer.get_latest(n_samples)
        if data is None:
            return

        timestamps = data["timestamps"]
        counts = data["counts"]

        if len(timestamps) == 0:
            return

        # Convert timestamps to relative seconds from most recent
        t_seconds = self._timestamps_to_relative_seconds(timestamps)

        # Extract the channel values and convert to display units
        y_values = counts[:, self._channel_index].astype(np.float64) / self._counts_per_unit

        self._line.setData(t_seconds, y_values)

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
