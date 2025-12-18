"""Tests for MainWindow time window selector integration."""

import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

try:
    import PySide6.QtGui
except ImportError:
    pytest.skip("PySide6 not usable", allow_module_level=True)

from gsdv.ui.main_window import MainWindow, TimeWindowSelector
from gsdv.plot.plot_widget import MultiChannelPlot
from gsdv.config.preferences import UserPreferences

@pytest.fixture
def main_window(qtbot):
    """Create a MainWindow instance for testing."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window

class TestMainWindowTimeWindowSelector:
    """Tests for time window selector integration in MainWindow."""

    def test_selector_is_created(self, main_window):
        """TimeWindowSelector is created and added to layout."""
        assert isinstance(main_window.time_window_selector, TimeWindowSelector)

    def test_selector_initialized_from_preferences(self, qtbot):
        """Selector initializes with value from preferences."""
        prefs = UserPreferences(time_window_seconds=60.0)
        window = MainWindow(preferences=prefs)
        qtbot.addWidget(window)
        
        assert window.time_window_selector.window_seconds() == 60.0
        # Check plot also updated
        assert isinstance(window._plot_area, MultiChannelPlot)
        assert window._plot_area._window_seconds == 60.0

    def test_changing_selector_updates_preferences(self, main_window, qtbot):
        """Changing selector updates preferences."""
        # Change to 5 seconds
        main_window.time_window_selector.set_window_seconds(5.0)
        
        assert main_window._preferences.time_window_seconds == 5.0

    def test_changing_selector_updates_plot(self, main_window, qtbot):
        """Changing selector updates plot widget."""
        # Change to 30 seconds
        main_window.time_window_selector.set_window_seconds(30.0)
        
        assert main_window._plot_area._window_seconds == 30.0

    def test_plot_area_is_multi_channel_plot(self, main_window):
        """Plot area is initialized as MultiChannelPlot."""
        assert isinstance(main_window._plot_area, MultiChannelPlot)

    def test_plot_area_has_correct_settings(self, qtbot):
        """Plot area has unit initialized from preferences."""
        prefs = UserPreferences(force_unit="kgf")
        window = MainWindow(preferences=prefs)
        qtbot.addWidget(window)
        
        assert window._plot_area._force_unit == "kgf"