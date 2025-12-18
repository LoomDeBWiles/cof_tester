"""Tests for NumericDisplay widget and real-time value updates."""

import numpy as np
import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

try:
    import PySide6.QtGui
except ImportError:
    pytest.skip("PySide6 not usable", allow_module_level=True)

from PySide6.QtCore import Qt

from gsdv.acquisition.ring_buffer import RingBuffer
from gsdv.plot.plot_widget import MultiChannelPlot
from gsdv.ui.main_window import NumericDisplay, MainWindow


@pytest.fixture
def numeric_display(qtbot):
    """Create a NumericDisplay widget for testing."""
    widget = NumericDisplay()
    qtbot.addWidget(widget)
    return widget


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


class TestNumericDisplayWidget:
    """Tests for NumericDisplay widget."""

    def test_init_creates_six_labels(self, numeric_display):
        """Init creates 6 value labels (one for each channel)."""
        assert len(numeric_display._value_labels) == 6
        for ch in NumericDisplay.CHANNELS:
            assert ch in numeric_display._value_labels

    def test_initial_values_are_dashes(self, numeric_display):
        """Initial values display as '---'."""
        for label in numeric_display._value_labels.values():
            assert label.text() == "---"

    def test_update_value_updates_label(self, numeric_display):
        """update_value updates the correct label with formatted value and unit."""
        numeric_display.update_value("Fx", 123.456, "N")
        assert numeric_display._value_labels["Fx"].text() == "+123.456 N"

    def test_update_value_with_negative(self, numeric_display):
        """update_value handles negative values correctly."""
        numeric_display.update_value("Fy", -45.789, "N")
        assert numeric_display._value_labels["Fy"].text() == "-45.789 N"

    def test_update_value_with_zero(self, numeric_display):
        """update_value handles zero correctly."""
        numeric_display.update_value("Fz", 0.0, "N")
        assert numeric_display._value_labels["Fz"].text() == "+0.000 N"

    def test_update_all_channels(self, numeric_display):
        """update_value can update all channels independently."""
        test_data = {
            "Fx": (1.234, "N"),
            "Fy": (2.345, "N"),
            "Fz": (3.456, "N"),
            "Tx": (4.567, "N-m"),
            "Ty": (5.678, "N-m"),
            "Tz": (6.789, "N-m"),
        }
        for channel, (value, unit) in test_data.items():
            numeric_display.update_value(channel, value, unit)

        for channel, (value, unit) in test_data.items():
            expected = f"{value:+.3f} {unit}"
            assert numeric_display._value_labels[channel].text() == expected

    def test_clear_values_resets_to_dashes(self, numeric_display):
        """clear_values resets all labels to '---'."""
        numeric_display.update_value("Fx", 123.456, "N")
        numeric_display.update_value("Ty", 789.012, "N-m")

        numeric_display.clear_values()

        for label in numeric_display._value_labels.values():
            assert label.text() == "---"

    def test_update_unknown_channel_does_nothing(self, numeric_display):
        """Updating unknown channel name does nothing (no error)."""
        numeric_display.update_value("InvalidChannel", 123.0, "N")
        # Should not raise an error


class TestPlotWidgetGetLatestValues:
    """Tests for MultiChannelPlot.get_latest_values method."""

    def test_get_latest_values_returns_none_without_buffer(self, qtbot):
        """get_latest_values returns None when no buffer is set."""
        widget = MultiChannelPlot(buffer=None)
        qtbot.addWidget(widget)
        assert widget.get_latest_values() is None

    def test_get_latest_values_returns_none_for_empty_buffer(self, qtbot):
        """get_latest_values returns None for empty buffer."""
        buffer = RingBuffer(capacity=100)
        widget = MultiChannelPlot(buffer=buffer)
        qtbot.addWidget(widget)
        assert widget.get_latest_values() is None

    def test_get_latest_values_returns_dict_with_all_channels(self, qtbot, populated_buffer):
        """get_latest_values returns dict with all 6 channels."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        widget.set_calibration(cpf=100.0, cpt=1000.0)
        widget.set_units("N", "N-m")

        values = widget.get_latest_values()
        assert values is not None
        assert len(values) == 6
        for ch in MultiChannelPlot.CHANNEL_NAMES:
            assert ch in values

    def test_get_latest_values_applies_calibration_for_forces(self, qtbot, populated_buffer):
        """get_latest_values applies force calibration factor correctly."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        widget.set_calibration(cpf=100.0, cpt=1000.0)
        widget.set_units("N", "N-m")

        values = widget.get_latest_values()

        # Latest sample has counts (199, 299, 399, 499, 599, 699)
        # Force channels should be divided by cpf=100.0
        assert values["Fx"][0] == pytest.approx(199 / 100.0)
        assert values["Fy"][0] == pytest.approx(299 / 100.0)
        assert values["Fz"][0] == pytest.approx(399 / 100.0)

    def test_get_latest_values_applies_calibration_for_torques(self, qtbot, populated_buffer):
        """get_latest_values applies torque calibration factor correctly."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        widget.set_calibration(cpf=100.0, cpt=1000.0)
        widget.set_units("N", "N-m")

        values = widget.get_latest_values()

        # Latest sample has counts (199, 299, 399, 499, 599, 699)
        # Torque channels should be divided by cpt=1000.0
        assert values["Tx"][0] == pytest.approx(499 / 1000.0)
        assert values["Ty"][0] == pytest.approx(599 / 1000.0)
        assert values["Tz"][0] == pytest.approx(699 / 1000.0)

    def test_get_latest_values_returns_correct_units(self, qtbot, populated_buffer):
        """get_latest_values returns correct units for each channel."""
        widget = MultiChannelPlot(buffer=populated_buffer)
        qtbot.addWidget(widget)
        widget.set_calibration(cpf=100.0, cpt=1000.0)
        widget.set_units("N", "N-m")

        values = widget.get_latest_values()

        # Force channels should have "N"
        assert values["Fx"][1] == "N"
        assert values["Fy"][1] == "N"
        assert values["Fz"][1] == "N"

        # Torque channels should have "N-m"
        assert values["Tx"][1] == "N-m"
        assert values["Ty"][1] == "N-m"
        assert values["Tz"][1] == "N-m"


class TestMainWindowNumericDisplayIntegration:
    """Tests for integration of numeric display in MainWindow."""

    def test_main_window_has_numeric_display(self, qtbot):
        """MainWindow has a numeric display widget."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window.numeric_display is not None
        assert isinstance(window.numeric_display, NumericDisplay)

    def test_update_numeric_display_method_exists(self, qtbot):
        """MainWindow has _update_numeric_display method."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert hasattr(window, "_update_numeric_display")
        assert callable(window._update_numeric_display)

    def test_update_numeric_display_updates_all_channels(self, qtbot, populated_buffer):
        """_update_numeric_display updates all channels when data is available."""
        window = MainWindow()
        qtbot.addWidget(window)

        # Set up plot widget with buffer and calibration
        window._plot_area.set_buffer(populated_buffer)
        window._plot_area.set_calibration(cpf=100.0, cpt=1000.0)
        window._plot_area.set_units("N", "N-m")

        # Call update method
        window._update_numeric_display()

        # Verify all channels were updated (not showing "---")
        for ch in NumericDisplay.CHANNELS:
            text = window.numeric_display._value_labels[ch].text()
            assert text != "---"
            # Should contain unit
            if ch in ("Fx", "Fy", "Fz"):
                assert "N" in text
            else:
                assert "N-m" in text

    def test_update_numeric_display_handles_no_data(self, qtbot):
        """_update_numeric_display handles case with no data gracefully."""
        window = MainWindow()
        qtbot.addWidget(window)

        # Set up plot widget with empty buffer
        buffer = RingBuffer(capacity=100)
        window._plot_area.set_buffer(buffer)

        # Call update method - should not raise error
        window._update_numeric_display()

        # Values should still be "---"
        for label in window.numeric_display._value_labels.values():
            assert label.text() == "---"

    def test_start_display_updates_starts_timer(self, qtbot):
        """start_display_updates starts the numeric update timer."""
        window = MainWindow()
        qtbot.addWidget(window)

        assert not window._numeric_update_timer.isActive()

        window.start_display_updates()

        assert window._numeric_update_timer.isActive()

    def test_stop_display_updates_stops_timer(self, qtbot):
        """stop_display_updates stops the numeric update timer."""
        window = MainWindow()
        qtbot.addWidget(window)

        window.start_display_updates()
        assert window._numeric_update_timer.isActive()

        window.stop_display_updates()

        assert not window._numeric_update_timer.isActive()

    def test_stop_display_updates_clears_values(self, qtbot, populated_buffer):
        """stop_display_updates clears the numeric display values."""
        window = MainWindow()
        qtbot.addWidget(window)

        # Set up and update with data
        window._plot_area.set_buffer(populated_buffer)
        window._plot_area.set_calibration(cpf=100.0, cpt=1000.0)
        window._plot_area.set_units("N", "N-m")
        window._update_numeric_display()

        # Verify data is shown
        assert window.numeric_display._value_labels["Fx"].text() != "---"

        # Stop updates
        window.stop_display_updates()

        # Values should be cleared
        for label in window.numeric_display._value_labels.values():
            assert label.text() == "---"

    def test_numeric_update_timer_interval_is_30hz(self, qtbot):
        """Numeric update timer is set to 30 Hz (33.3 ms interval)."""
        window = MainWindow()
        qtbot.addWidget(window)
        # 30 Hz = 1000ms / 30 = 33.333... ms, rounded to int(33)
        expected_interval = int(1000 / 30)
        assert window._numeric_update_timer.interval() == expected_interval
