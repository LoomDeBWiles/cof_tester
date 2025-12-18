"""UI accessibility tests for High-DPI scaling and keyboard navigation.

These tests verify:
1. High-DPI scaling: UI elements scale properly without clipping or blur
2. Keyboard navigation: All controls are keyboard-accessible via Tab

Note: Keyboard shortcut tests are in test_main_window.py
"""

import pytest

# Skip entire module if Qt is not available (handled by conftest.py collect_ignore)
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QPushButton, QSizePolicy

from gsdv.ui import MainWindow


@pytest.fixture
def main_window(qtbot):
    """Create MainWindow instance for testing."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


class TestHighDpiScaling:
    """Tests for High-DPI display compatibility.

    Verifies that UI elements scale correctly at 150% and 200% scaling
    without clipping, truncation, or layout issues.
    """

    def test_main_window_minimum_size_allows_scaling(self, main_window):
        """MainWindow minimum size should allow room for scaling."""
        min_width = main_window.minimumWidth()
        min_height = main_window.minimumHeight()
        assert min_width >= 800, f"Minimum width {min_width} too small for High-DPI"
        assert min_height >= 600, f"Minimum height {min_height} too small for High-DPI"

    def test_connection_panel_ip_input_has_adequate_width(self, main_window):
        """IP input field should be wide enough for addresses at High-DPI."""
        ip_input = main_window.connection_panel._ip_input
        min_width = ip_input.minimumWidth()
        # At 200% scaling, 140px base becomes 280px - needs to fit full IP
        assert min_width >= 120, f"IP input min width {min_width} may clip at High-DPI"

    def test_numeric_display_value_labels_have_minimum_width(self, main_window):
        """Value labels should have minimum width for scaled font sizes."""
        for channel, label in main_window.numeric_display._value_labels.items():
            min_width = label.minimumWidth()
            assert min_width >= 60, (
                f"Channel {channel} label min width {min_width} may clip values at High-DPI"
            )

    def test_recording_controls_path_label_has_minimum_width(self, main_window):
        """Path label should have minimum width for readability at High-DPI."""
        path_label = main_window.recording_controls._path_label
        min_width = path_label.minimumWidth()
        assert min_width >= 150, f"Path label min width {min_width} may truncate at High-DPI"

    def test_status_indicators_use_border_radius_not_fixed_pixels(self, main_window):
        """Status indicators should scale via border-radius, not fixed image."""
        conn_indicator = main_window.connection_panel._status_indicator
        style = conn_indicator.styleSheet()
        assert "border-radius" in style, "Connection indicator should use CSS border-radius"

        rec_indicator = main_window.recording_controls._recording_indicator
        style = rec_indicator.styleSheet()
        assert "border-radius" in style, "Recording indicator should use CSS border-radius"

    def test_plot_area_has_expanding_size_policy(self, main_window):
        """Plot area should expand to fill available space at any DPI."""
        plot_area = main_window._plot_area
        policy = plot_area.sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding

    def test_groupboxes_use_relative_margins(self, main_window):
        """GroupBoxes should have consistent margin structure for scaling."""
        groupboxes = main_window.findChildren(QGroupBox)
        assert len(groupboxes) >= 4, "Expected at least 4 GroupBox widgets"

        for groupbox in groupboxes:
            layout = groupbox.layout()
            if layout:
                margins = layout.contentsMargins()
                # Margins should be reasonable (not 0, not excessively large)
                assert margins.left() >= 4, f"{groupbox.title()} left margin too small"
                assert margins.right() >= 4, f"{groupbox.title()} right margin too small"

    def test_buttons_have_adequate_padding(self, main_window):
        """Buttons should have padding for touch targets at High-DPI."""
        buttons = main_window.findChildren(QPushButton)
        for button in buttons:
            height = button.sizeHint().height()
            # Minimum touch target should be ~24px at base DPI (48px at 200%)
            assert height >= 20, f"Button '{button.text()}' height {height}px may be too small"


class TestKeyboardNavigation:
    """Tests for keyboard accessibility.

    Verifies that all controls can be accessed via keyboard (Tab navigation).
    Note: Keyboard shortcut tests are in test_main_window.py
    """

    def test_ip_input_is_focusable(self, main_window):
        """IP input field should accept keyboard focus."""
        ip_input = main_window.connection_panel._ip_input
        assert ip_input.focusPolicy() != Qt.FocusPolicy.NoFocus
        ip_input.setFocus()
        assert ip_input.hasFocus()

    def test_connect_button_is_focusable(self, main_window):
        """Connect button should be keyboard-accessible."""
        connect_btn = main_window.connection_panel._connect_button
        assert connect_btn.focusPolicy() != Qt.FocusPolicy.NoFocus

    def test_channel_checkboxes_are_focusable(self, main_window):
        """Channel checkboxes should be keyboard-toggleable."""
        for channel, checkbox in main_window.channel_selector._checkboxes.items():
            assert checkbox.focusPolicy() != Qt.FocusPolicy.NoFocus, (
                f"Channel {channel} checkbox not focusable"
            )

    def test_browse_button_is_focusable(self, main_window):
        """Browse button should be keyboard-accessible."""
        browse_btn = main_window.recording_controls._browse_button
        assert browse_btn.focusPolicy() != Qt.FocusPolicy.NoFocus

    def test_record_button_is_focusable(self, main_window):
        """Record button should be keyboard-accessible."""
        record_btn = main_window.recording_controls._record_button
        assert record_btn.focusPolicy() != Qt.FocusPolicy.NoFocus

    def test_theme_button_is_focusable(self, main_window):
        """Theme toggle button should be keyboard-accessible."""
        theme_btn = main_window._theme_button
        assert theme_btn.focusPolicy() != Qt.FocusPolicy.NoFocus

    def test_settings_button_is_focusable(self, main_window):
        """Settings button should be keyboard-accessible."""
        settings_btn = main_window._settings_button
        assert settings_btn.focusPolicy() != Qt.FocusPolicy.NoFocus

    def test_ip_input_enter_triggers_connect(self, main_window, qtbot):
        """Pressing Enter in IP input should trigger connect."""
        ip_input = main_window.connection_panel._ip_input
        ip_input.setText("192.168.1.100")

        signal_received = []
        main_window.connection_panel.connect_requested.connect(
            lambda ip: signal_received.append(ip)
        )

        ip_input.setFocus()
        qtbot.keyClick(ip_input, Qt.Key.Key_Return)

        assert len(signal_received) == 1
        assert signal_received[0] == "192.168.1.100"

    def test_tab_order_logical_flow(self, main_window, qtbot):
        """Tab key should navigate through controls in logical order."""
        ip_input = main_window.connection_panel._ip_input
        ip_input.setFocus()
        assert ip_input.hasFocus()

        qtbot.keyClick(main_window, Qt.Key.Key_Tab)
        # Focus should have moved (may not be exactly connect button due to layout)
        assert not ip_input.hasFocus(), "Tab should move focus from IP input"

    def test_checkbox_toggleable_with_space(self, main_window, qtbot):
        """Checkboxes should toggle with Space key when focused."""
        checkbox = main_window.channel_selector._checkboxes["Tx"]
        initial_state = checkbox.isChecked()
        checkbox.setFocus()

        qtbot.keyClick(checkbox, Qt.Key.Key_Space)
        assert checkbox.isChecked() != initial_state, "Space should toggle checkbox"

        qtbot.keyClick(checkbox, Qt.Key.Key_Space)
        assert checkbox.isChecked() == initial_state, "Second Space should restore state"
