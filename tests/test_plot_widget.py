"""Tests for SingleChannelPlot widget."""

import numpy as np
import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

from gsdv.acquisition.ring_buffer import RingBuffer
from gsdv.plot.plot_widget import SingleChannelPlot


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
    """Create a SingleChannelPlot widget for testing."""
    widget = SingleChannelPlot(buffer=ring_buffer)
    qtbot.addWidget(widget)
    return widget


class TestSingleChannelPlotInitialization:
    """Tests for SingleChannelPlot initialization."""

    def test_default_channel_index_is_zero(self, qtbot):
        """Default channel index is 0 (Fx)."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        assert widget._channel_index == 0
        assert widget._channel_label == "Fx"

    def test_custom_channel_index(self, qtbot):
        """Can specify a different channel index at init."""
        widget = SingleChannelPlot(channel_index=3)
        qtbot.addWidget(widget)
        assert widget._channel_index == 3
        assert widget._channel_label == "Tx"

    def test_buffer_is_stored(self, qtbot, ring_buffer):
        """Buffer passed at init is stored."""
        widget = SingleChannelPlot(buffer=ring_buffer)
        qtbot.addWidget(widget)
        assert widget._buffer is ring_buffer

    def test_default_window_seconds(self, qtbot):
        """Default window is 10 seconds."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        assert widget._window_seconds == 10.0

    def test_default_counts_per_unit(self, qtbot):
        """Default counts_per_unit is 1.0."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        assert widget._counts_per_unit == 1.0

    def test_default_sample_rate(self, qtbot):
        """Default sample_rate is 1000.0."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        assert widget._sample_rate == 1000.0

    def test_custom_sample_rate(self, qtbot):
        """Can specify custom sample rate at init."""
        widget = SingleChannelPlot(sample_rate=500.0)
        qtbot.addWidget(widget)
        assert widget._sample_rate == 500.0

    def test_timer_not_running_on_init(self, qtbot):
        """Timer is not running immediately after init."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        assert not widget.is_running()


class TestSingleChannelPlotConfiguration:
    """Tests for SingleChannelPlot configuration methods."""

    def test_set_buffer(self, qtbot):
        """set_buffer stores the buffer."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        buffer = RingBuffer(capacity=100)
        widget.set_buffer(buffer)
        assert widget._buffer is buffer

    def test_set_channel_index_valid(self, qtbot):
        """set_channel_index accepts valid indices 0-5."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        for i in range(6):
            widget.set_channel_index(i)
            assert widget._channel_index == i
            assert widget._channel_label == SingleChannelPlot.CHANNEL_NAMES[i]

    def test_set_channel_index_negative_raises(self, qtbot):
        """set_channel_index raises for negative index."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be 0-5"):
            widget.set_channel_index(-1)

    def test_set_channel_index_too_large_raises(self, qtbot):
        """set_channel_index raises for index > 5."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be 0-5"):
            widget.set_channel_index(6)

    def test_set_channel_label_custom(self, qtbot):
        """set_channel_label allows custom labels."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.set_channel_label("Custom Force")
        assert widget._channel_label == "Custom Force"

    def test_set_unit(self, qtbot):
        """set_unit stores the unit."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.set_unit("N")
        assert widget._unit == "N"

    def test_set_counts_per_unit_valid(self, qtbot):
        """set_counts_per_unit accepts positive values."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.set_counts_per_unit(1000.0)
        assert widget._counts_per_unit == 1000.0

    def test_set_counts_per_unit_zero_raises(self, qtbot):
        """set_counts_per_unit raises for zero."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be positive"):
            widget.set_counts_per_unit(0.0)

    def test_set_counts_per_unit_negative_raises(self, qtbot):
        """set_counts_per_unit raises for negative values."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be positive"):
            widget.set_counts_per_unit(-100.0)

    def test_set_sample_rate_valid(self, qtbot):
        """set_sample_rate accepts positive values."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.set_sample_rate(2000.0)
        assert widget._sample_rate == 2000.0

    def test_set_sample_rate_zero_raises(self, qtbot):
        """set_sample_rate raises for zero."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be positive"):
            widget.set_sample_rate(0.0)

    def test_set_sample_rate_negative_raises(self, qtbot):
        """set_sample_rate raises for negative values."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be positive"):
            widget.set_sample_rate(-1.0)

    def test_set_window_seconds_valid(self, qtbot):
        """set_window_seconds accepts positive values."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.set_window_seconds(5.0)
        assert widget._window_seconds == 5.0

    def test_set_window_seconds_zero_raises(self, qtbot):
        """set_window_seconds raises for zero."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be positive"):
            widget.set_window_seconds(0.0)

    def test_set_window_seconds_negative_raises(self, qtbot):
        """set_window_seconds raises for negative values."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        with pytest.raises(ValueError, match="must be positive"):
            widget.set_window_seconds(-1.0)


class TestSingleChannelPlotTimerControl:
    """Tests for SingleChannelPlot timer start/stop."""

    def test_start_starts_timer(self, qtbot):
        """start() starts the timer."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.start()
        assert widget.is_running()
        widget.stop()

    def test_stop_stops_timer(self, qtbot):
        """stop() stops the timer."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.start()
        widget.stop()
        assert not widget.is_running()

    def test_start_is_idempotent(self, qtbot):
        """Calling start() multiple times doesn't break anything."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.start()
        widget.start()
        widget.start()
        assert widget.is_running()
        widget.stop()

    def test_stop_is_idempotent(self, qtbot):
        """Calling stop() multiple times doesn't break anything."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.stop()
        widget.stop()
        assert not widget.is_running()

    def test_timer_interval_for_30fps(self, qtbot):
        """Timer interval is configured for 30fps (~33ms)."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        expected_interval = int(1000 / 30)
        assert widget._timer.interval() == expected_interval


class TestSingleChannelPlotDataUpdate:
    """Tests for SingleChannelPlot data update."""

    def test_update_with_no_buffer_does_not_crash(self, qtbot):
        """_update_plot handles None buffer gracefully."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget._update_plot()  # Should not raise

    def test_update_with_empty_buffer_does_not_crash(self, qtbot, ring_buffer):
        """_update_plot handles empty buffer gracefully."""
        widget = SingleChannelPlot(buffer=ring_buffer)
        qtbot.addWidget(widget)
        widget._update_plot()  # Should not raise

    def test_update_with_data_populates_plot(self, qtbot, populated_buffer):
        """_update_plot populates the line with data."""
        widget = SingleChannelPlot(buffer=populated_buffer, channel_index=0)
        qtbot.addWidget(widget)
        widget._update_plot()

        # The line should have data now
        x_data, y_data = widget._line.getData()
        assert len(x_data) > 0
        assert len(y_data) > 0

    def test_update_extracts_correct_channel(self, qtbot, populated_buffer):
        """_update_plot extracts the correct channel from counts."""
        widget = SingleChannelPlot(buffer=populated_buffer, channel_index=2)
        qtbot.addWidget(widget)
        widget._update_plot()

        _, y_data = widget._line.getData()
        # Channel 2 (Fz) should have values starting from 300
        # The first sample in our test data has counts[2] = 300
        assert y_data[0] == 300.0

    def test_update_applies_counts_per_unit(self, qtbot, populated_buffer):
        """_update_plot applies counts_per_unit conversion."""
        widget = SingleChannelPlot(buffer=populated_buffer, channel_index=0)
        qtbot.addWidget(widget)
        widget.set_counts_per_unit(100.0)
        widget._update_plot()

        _, y_data = widget._line.getData()
        # Channel 0 (Fx) has counts starting from 100
        # With cpf=100, value should be 100/100 = 1.0
        assert y_data[0] == 1.0

    def test_clear_removes_data(self, qtbot, populated_buffer):
        """clear() removes data from the plot."""
        widget = SingleChannelPlot(buffer=populated_buffer, channel_index=0)
        qtbot.addWidget(widget)
        widget._update_plot()
        widget.clear()

        x_data, y_data = widget._line.getData()
        assert len(x_data) == 0
        assert len(y_data) == 0


class TestSingleChannelPlotTimestampConversion:
    """Tests for timestamp conversion logic."""

    def test_timestamps_to_relative_seconds_empty(self, qtbot):
        """Empty timestamps return empty array."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        result = widget._timestamps_to_relative_seconds(np.array([], dtype=np.int64))
        assert len(result) == 0

    def test_timestamps_to_relative_seconds_single(self, qtbot):
        """Single timestamp returns 0.0."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        result = widget._timestamps_to_relative_seconds(np.array([1_000_000_000], dtype=np.int64))
        assert len(result) == 1
        assert result[0] == 0.0

    def test_timestamps_to_relative_seconds_multiple(self, qtbot):
        """Multiple timestamps are relative to last sample."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        # 3 samples, 1 second apart
        timestamps = np.array([
            1_000_000_000_000,  # -2 seconds relative to last
            2_000_000_000_000,  # -1 second relative to last
            3_000_000_000_000,  # 0 (reference)
        ], dtype=np.int64)
        result = widget._timestamps_to_relative_seconds(timestamps)

        assert len(result) == 3
        assert result[0] == pytest.approx(-2.0)
        assert result[1] == pytest.approx(-1.0)
        assert result[2] == pytest.approx(0.0)


class TestSingleChannelPlotAxisLabels:
    """Tests for axis label configuration."""

    def test_x_axis_label_is_time(self, qtbot):
        """X-axis is labeled as Time with units in seconds."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        bottom_axis = widget._plot_item.getAxis("bottom")
        assert bottom_axis.labelText == "Time"
        assert bottom_axis.labelUnits == "s"

    def test_y_axis_label_matches_channel(self, qtbot):
        """Y-axis label matches the channel name."""
        widget = SingleChannelPlot(channel_index=0)
        qtbot.addWidget(widget)
        left_axis = widget._plot_item.getAxis("left")
        assert left_axis.labelText == "Fx"

    def test_y_axis_label_updates_on_channel_change(self, qtbot):
        """Y-axis label updates when channel is changed."""
        widget = SingleChannelPlot(channel_index=0)
        qtbot.addWidget(widget)
        widget.set_channel_index(3)
        left_axis = widget._plot_item.getAxis("left")
        assert left_axis.labelText == "Tx"

    def test_y_axis_units_from_set_unit(self, qtbot):
        """Y-axis shows units set via set_unit()."""
        widget = SingleChannelPlot()
        qtbot.addWidget(widget)
        widget.set_unit("N")
        left_axis = widget._plot_item.getAxis("left")
        assert left_axis.labelUnits == "N"


class TestSingleChannelPlotConstants:
    """Tests for SingleChannelPlot class constants."""

    def test_channel_names_correct(self):
        """CHANNEL_NAMES has correct values."""
        assert SingleChannelPlot.CHANNEL_NAMES == ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")

    def test_default_window_is_ten_seconds(self):
        """DEFAULT_WINDOW_SECONDS is 10."""
        assert SingleChannelPlot.DEFAULT_WINDOW_SECONDS == 10.0

    def test_target_fps_is_thirty(self):
        """TARGET_FPS is 30."""
        assert SingleChannelPlot.TARGET_FPS == 30
