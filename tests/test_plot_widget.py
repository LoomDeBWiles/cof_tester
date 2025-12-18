"""Tests for MultiChannelPlot widget."""

import numpy as np
import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

import pyqtgraph as pg

try:
    import PySide6.QtGui
except ImportError:
    pytest.skip("PySide6 not usable", allow_module_level=True)

from gsdv.acquisition.ring_buffer import RingBuffer
from gsdv.plot.plot_widget import MultiChannelPlot


@pytest.fixture
def ring_buffer():
    """Create a ring buffer with some test data."""
    buffer = RingBuffer(capacity=1000)
    return buffer


@pytest.fixture
def populated_buffer():
    """Create a ring buffer populated with test data."""
    buffer = RingBuffer(capacity=1000)
    base_time = 1_000_000_000_000  # 1 second in nanoseconds
    for i in range(100):
        buffer.append(
            t_monotonic_ns=base_time + i * 1_000_000,  # 1ms between samples
            rdt_sequence=i,
            ft_sequence=i,
            status=0,
            counts=(100 + i, 200 + i, 300 + i, 400 + i, 500 + i, 600 + i),
        )
    return buffer


@pytest.fixture
def plot_widget(qtbot, ring_buffer):
    """Create a MultiChannelPlot widget for testing."""
    widget = MultiChannelPlot(buffer=ring_buffer)
    qtbot.addWidget(widget)
    return widget


class TestMultiChannelPlotInitialization:
    """Tests for MultiChannelPlot initialization."""

    def test_init_creates_six_lines(self, qtbot):
        """Init creates 6 lines (one for each channel)."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        assert len(widget._lines) == 6
        for ch in MultiChannelPlot.CHANNEL_NAMES:
            assert ch in widget._lines
            assert isinstance(widget._lines[ch], pg.PlotDataItem)

    def test_buffer_is_stored(self, qtbot, ring_buffer):
        """Buffer passed at init is stored."""
        widget = MultiChannelPlot(buffer=ring_buffer)
        qtbot.addWidget(widget)
        assert widget._buffer is ring_buffer

    def test_default_window_seconds(self, qtbot):
        """Default window is 10 seconds."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        assert widget._window_seconds == 10.0

    def test_default_calibration_factors(self, qtbot):
        """Default calibration factors are 1.0."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        assert widget._counts_per_force == 1.0
        assert widget._counts_per_torque == 1.0

    def test_timer_not_running_on_init(self, qtbot):
        """Timer is not running immediately after init."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        assert not widget.is_running()


class TestMultiChannelPlotConfiguration:
    """Tests for MultiChannelPlot configuration methods."""

    def test_set_buffer(self, qtbot):
        """set_buffer stores the buffer."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        buffer = RingBuffer(capacity=100)
        widget.set_buffer(buffer)
        assert widget._buffer is buffer

    def test_set_calibration_valid(self, qtbot):
        """set_calibration updates factors."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        widget.set_calibration(100.0, 200.0)
        assert widget._counts_per_force == 100.0
        assert widget._counts_per_torque == 200.0

    def test_set_calibration_invalid_raises(self, qtbot):
        """set_calibration raises for non-positive values."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="positive"):
            widget.set_calibration(0, 100)
        with pytest.raises(ValueError, match="positive"):
            widget.set_calibration(100, -1)

    def test_set_units(self, qtbot):
        """set_units updates internal state."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        widget.set_units("kN", "Nm")
        assert widget._force_unit == "kN"
        assert widget._torque_unit == "Nm"

    def test_set_channel_visible(self, qtbot):
        """set_channel_visible toggles visibility."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        widget.set_channel_visible("Fx", False)
        assert not widget._lines["Fx"].isVisible()
        widget.set_channel_visible("Fx", True)
        assert widget._lines["Fx"].isVisible()

    def test_set_sample_rate(self, qtbot):
        """set_sample_rate updates rate."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        widget.set_sample_rate(500.0)
        assert widget._sample_rate == 500.0

    def test_set_window_seconds(self, qtbot):
        """set_window_seconds updates window."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        widget.set_window_seconds(5.0)
        assert widget._window_seconds == 5.0


class TestMultiChannelPlotTimerControl:
    """Tests for MultiChannelPlot timer start/stop."""

    def test_start_starts_timer(self, qtbot):
        """start() starts the timer."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        widget.start()
        assert widget.is_running()
        widget.stop()

    def test_stop_stops_timer(self, qtbot):
        """stop() stops the timer."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        widget.start()
        widget.stop()
        assert not widget.is_running()


class TestMultiChannelPlotDataUpdate:
    """Tests for MultiChannelPlot data update."""

    def test_update_populates_all_channels(self, qtbot, populated_buffer):
        """_update_plot populates all visible lines with data."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        widget._update_plot()

        for ch in MultiChannelPlot.CHANNEL_NAMES:
            x_data, y_data = widget._lines[ch].getData()
            assert len(x_data) > 0
            assert len(y_data) > 0

    def test_update_applies_calibration(self, qtbot, populated_buffer):
        """_update_plot applies correct calibration factors."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        
        # Set distinct factors
        # Force: divide by 10. Torque: divide by 100.
        widget.set_calibration(10.0, 100.0)
        widget._update_plot()

        # Check Fx (channel 0) -> 100 + i. First val 100. 100 / 10 = 10.0
        _, y_fx = widget._lines["Fx"].getData()
        assert y_fx[0] == 10.0

        # Check Tx (channel 3) -> 400 + i. First val 400. 400 / 100 = 4.0
        _, y_tx = widget._lines["Tx"].getData()
        assert y_tx[0] == 4.0

    def test_update_skips_hidden_channels(self, qtbot, populated_buffer):
        """_update_plot does not update hidden lines (optimization check)."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        
        # Hide Fx
        widget.set_channel_visible("Fx", False)
        # Ensure Fx has no data initially (it's empty by default)
        x_data, _ = widget._lines["Fx"].getData()
        if x_data is None: x_data = [] # pyqtgraph might return None
        assert len(x_data) == 0

        widget._update_plot()

        # Fx should still be empty
        x_data, _ = widget._lines["Fx"].getData()
        if x_data is None: x_data = []
        assert len(x_data) == 0

        # Fy should have data
        x_data_fy, _ = widget._lines["Fy"].getData()
        assert len(x_data_fy) > 0

    def test_clear_removes_data(self, qtbot, populated_buffer):
        """clear() removes data from all lines."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        widget._update_plot()
        widget.clear()

        for ch in MultiChannelPlot.CHANNEL_NAMES:
            x_data, y_data = widget._lines[ch].getData()
            assert len(x_data) == 0
            assert len(y_data) == 0


class TestMultiChannelPlotTimestampConversion:
    """Tests for timestamp conversion logic."""

    def test_timestamps_to_relative_seconds_multiple(self, qtbot):
        """Multiple timestamps are relative to last sample."""
        widget = MultiChannelPlot()
        qtbot.addWidget(widget)
        timestamps = np.array([
            1_000_000_000_000,
            2_000_000_000_000,
            3_000_000_000_000,
        ], dtype=np.int64)
        result = widget._timestamps_to_relative_seconds(timestamps)

        assert len(result) == 3
        assert result[2] == pytest.approx(0.0)
