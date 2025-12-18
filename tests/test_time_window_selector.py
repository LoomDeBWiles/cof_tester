"""Tests for TimeWindowSelector widget."""

import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from gsdv.ui.main_window import TimeWindowSelector


@pytest.fixture
def selector(qtbot):
    """Create a TimeWindowSelector instance for testing."""
    widget = TimeWindowSelector()
    qtbot.addWidget(widget)
    return widget


class TestTimeWindowSelector:
    """Tests for TimeWindowSelector widget."""

    def test_initial_state(self, selector):
        """Selector starts with default value (10s)."""
        assert selector.window_seconds() == 10.0
        assert selector._combo.count() == len(TimeWindowSelector.TIME_WINDOWS)

    def test_window_changed_signal(self, selector, qtbot):
        """Signal emitted when selection changes."""
        with qtbot.waitSignal(selector.window_changed, timeout=1000) as blocker:
            # Change to 1s (index 0)
            selector._combo.setCurrentIndex(0)

        assert blocker.args == [1.0]
        assert selector.window_seconds() == 1.0

    def test_set_window_seconds_exact(self, selector):
        """Setting exact seconds updates combo box."""
        selector.set_window_seconds(60.0)  # 1 min
        assert selector.window_seconds() == 60.0
        assert selector._combo.currentText() == "1 min"

    def test_set_window_seconds_closest(self, selector):
        """Setting arbitrary seconds selects closest option."""
        selector.set_window_seconds(12.0)  # Closest to 10s
        assert selector.window_seconds() == 10.0

        selector.set_window_seconds(4000.0)  # Closest to 1 hour (3600)
        assert selector.window_seconds() == 3600.0

    def test_set_window_index(self, selector):
        """Setting index updates selection."""
        selector.set_window_index(0)
        assert selector.window_seconds() == 1.0

    def test_set_window_index_out_of_range(self, selector):
        """Setting invalid index raises IndexError."""
        with pytest.raises(IndexError):
            selector.set_window_index(-1)
        
        with pytest.raises(IndexError):
            selector.set_window_index(100)

    def test_max_range_is_7_days(self, selector):
        """Verify maximum range is 7 days as per requirements."""
        max_seconds = selector.TIME_WINDOWS[-1][1]
        assert max_seconds == 7 * 24 * 3600  # 604800.0
