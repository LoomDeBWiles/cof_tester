"""Tests for MainWindow keyboard shortcuts."""

import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

try:
    import PySide6.QtGui
except ImportError:
    pytest.skip("PySide6 not usable", allow_module_level=True)

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

from gsdv.config.preferences import UserPreferences
from gsdv.protocols.tcp_cmd import ToolTransform
from gsdv.ui import MainWindow


@pytest.fixture
def main_window(qtbot):
    """Create a MainWindow instance for testing."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def find_action_by_shortcut(window: MainWindow, key_sequence: QKeySequence):
    """Find an action in the window by its shortcut."""
    for action in window.actions():
        if action.shortcut() == key_sequence:
            return action
    return None


class TestKeyboardShortcuts:
    """Tests for FR-30: Keyboard shortcuts for core actions."""

    def test_connect_shortcut_ctrl_enter(self, main_window):
        """Connect shortcut is Ctrl+Enter."""
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return)
        action = find_action_by_shortcut(main_window, shortcut)
        assert action is not None, "Connect shortcut (Ctrl+Enter) not found"
        assert action.text() == "Connect"

    def test_record_shortcut_ctrl_r(self, main_window):
        """Record shortcut is Ctrl+R."""
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_R)
        action = find_action_by_shortcut(main_window, shortcut)
        assert action is not None, "Record shortcut (Ctrl+R) not found"
        assert action.text() == "Record"

    def test_stop_shortcut_ctrl_shift_s(self, main_window):
        """Stop shortcut is Ctrl+Shift+S."""
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_S)
        action = find_action_by_shortcut(main_window, shortcut)
        assert action is not None, "Stop shortcut (Ctrl+Shift+S) not found"
        assert action.text() == "Stop"

    def test_bias_shortcut_ctrl_b(self, main_window):
        """Bias shortcut is Ctrl+B."""
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_B)
        action = find_action_by_shortcut(main_window, shortcut)
        assert action is not None, "Bias shortcut (Ctrl+B) not found"
        assert action.text() == "Bias"

    def test_settings_shortcut_ctrl_comma(self, main_window):
        """Settings shortcut is Ctrl+,."""
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Comma)
        action = find_action_by_shortcut(main_window, shortcut)
        assert action is not None, "Settings shortcut (Ctrl+,) not found"
        assert action.text() == "Settings"

    def test_all_shortcuts_are_unique(self, main_window):
        """All keyboard shortcuts are unique (no duplicates)."""
        shortcuts = []
        for action in main_window.actions():
            shortcut = action.shortcut()
            if not shortcut.isEmpty():
                shortcut_str = shortcut.toString()
                assert shortcut_str not in shortcuts, f"Duplicate shortcut: {shortcut_str}"
                shortcuts.append(shortcut_str)

    def test_connect_shortcut_triggers_connection(self, main_window, qtbot):
        """Ctrl+Enter shortcut triggers connect action."""
        signals_received = []
        main_window.connection_panel.connect_requested.connect(
            lambda ip: signals_received.append(("connect", ip))
        )
        main_window.connection_panel.set_ip("192.168.1.100")

        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return)
        action = find_action_by_shortcut(main_window, shortcut)
        action.trigger()

        assert len(signals_received) == 1
        assert signals_received[0] == ("connect", "192.168.1.100")

    def test_record_shortcut_triggers_recording_start(self, main_window, qtbot):
        """Ctrl+R shortcut triggers record_started signal when not recording."""
        signals_received = []
        main_window.recording_controls.record_started.connect(
            lambda: signals_received.append("record_started")
        )
        main_window.recording_controls.set_output_path("/tmp")

        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_R)
        action = find_action_by_shortcut(main_window, shortcut)
        action.trigger()

        assert "record_started" in signals_received

    def test_record_shortcut_does_nothing_when_already_recording(self, main_window, qtbot):
        """Ctrl+R shortcut does nothing when already recording."""
        signals_received = []
        main_window.recording_controls.record_started.connect(
            lambda: signals_received.append("record_started")
        )
        main_window.recording_controls.set_output_path("/tmp")
        main_window.recording_controls.set_recording(True)

        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_R)
        action = find_action_by_shortcut(main_window, shortcut)
        action.trigger()

        assert "record_started" not in signals_received

    def test_stop_shortcut_triggers_recording_stop(self, main_window, qtbot):
        """Ctrl+Shift+S shortcut triggers record_stopped signal when recording."""
        signals_received = []
        main_window.recording_controls.record_stopped.connect(
            lambda: signals_received.append("record_stopped")
        )
        main_window.recording_controls.set_output_path("/tmp")
        main_window.recording_controls.set_recording(True)

        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_S)
        action = find_action_by_shortcut(main_window, shortcut)
        action.trigger()

        assert "record_stopped" in signals_received

    def test_stop_shortcut_does_nothing_when_not_recording(self, main_window, qtbot):
        """Ctrl+Shift+S shortcut does nothing when not recording."""
        signals_received = []
        main_window.recording_controls.record_stopped.connect(
            lambda: signals_received.append("record_stopped")
        )

        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_S)
        action = find_action_by_shortcut(main_window, shortcut)
        action.trigger()

        assert "record_stopped" not in signals_received

    def test_platform_aware_shortcuts_use_ctrl_modifier(self, main_window):
        """Shortcuts use Qt.Modifier.CTRL which maps to Cmd on macOS."""
        # Qt.Modifier.CTRL is automatically translated to Cmd on macOS
        # This test verifies all shortcuts use the CTRL modifier consistently
        for action in main_window.actions():
            shortcut = action.shortcut()
            if not shortcut.isEmpty():
                # All our shortcuts should use CTRL modifier
                key_combination = shortcut[0]
                assert key_combination.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier


class TestMainWindowTheme:
    """Tests for FR-28: Dark/light theme toggle with persistence."""

    def test_default_theme_is_light(self, main_window):
        """MainWindow starts with light theme by default."""
        assert main_window.current_theme() == MainWindow.LIGHT_THEME

    def test_set_theme_dark(self, main_window):
        """Setting dark theme changes current_theme."""
        main_window.set_theme(MainWindow.DARK_THEME)
        assert main_window.current_theme() == MainWindow.DARK_THEME

    def test_set_theme_light_from_dark(self, main_window):
        """Setting light theme from dark changes current_theme."""
        main_window.set_theme(MainWindow.DARK_THEME)
        main_window.set_theme(MainWindow.LIGHT_THEME)
        assert main_window.current_theme() == MainWindow.LIGHT_THEME

    def test_set_theme_invalid_ignored(self, main_window):
        """Invalid theme values are ignored."""
        main_window.set_theme("invalid_theme")
        assert main_window.current_theme() == MainWindow.LIGHT_THEME

    def test_toggle_theme_from_light_to_dark(self, main_window):
        """Toggling from light theme switches to dark."""
        main_window.toggle_theme()
        assert main_window.current_theme() == MainWindow.DARK_THEME

    def test_toggle_theme_from_dark_to_light(self, main_window):
        """Toggling from dark theme switches to light."""
        main_window.set_theme(MainWindow.DARK_THEME)
        main_window.toggle_theme()
        assert main_window.current_theme() == MainWindow.LIGHT_THEME

    def test_theme_changed_signal_emitted_on_set(self, main_window):
        """theme_changed signal emits when theme is set to different value."""
        received_themes: list[str] = []
        main_window.theme_changed.connect(lambda theme: received_themes.append(theme))

        main_window.set_theme(MainWindow.DARK_THEME)

        assert received_themes == [MainWindow.DARK_THEME]

    def test_theme_changed_signal_not_emitted_when_same(self, main_window):
        """theme_changed signal does not emit when setting same theme."""
        received_themes: list[str] = []
        main_window.theme_changed.connect(lambda theme: received_themes.append(theme))

        main_window.set_theme(MainWindow.LIGHT_THEME)  # Same as default

        assert received_themes == []

    def test_theme_changed_signal_emitted_on_toggle(self, main_window):
        """theme_changed signal emits when theme is toggled."""
        received_themes: list[str] = []
        main_window.theme_changed.connect(lambda theme: received_themes.append(theme))

        main_window.toggle_theme()
        main_window.toggle_theme()

        assert received_themes == [MainWindow.DARK_THEME, MainWindow.LIGHT_THEME]

    def test_theme_button_text_updates_on_toggle(self, main_window):
        """Theme button text shows opposite theme name."""
        # Light theme shows "Dark" button (to switch to dark)
        assert main_window._theme_button.text() == "Dark"

        main_window.toggle_theme()
        # Dark theme shows "Light" button (to switch to light)
        assert main_window._theme_button.text() == "Light"

    def test_theme_constants_have_expected_values(self, main_window):
        """Theme constants match expected string values."""
        assert MainWindow.DARK_THEME == "dark"
        assert MainWindow.LIGHT_THEME == "light"


class TestMainWindowTransform:
    """Tests for FR-27: Tool transform UI and signal."""

    def test_current_transform_returns_default_values(self, main_window):
        """current_transform returns ToolTransform with default zero values."""
        transform = main_window.current_transform
        assert isinstance(transform, ToolTransform)
        assert transform.dx == 0.0
        assert transform.dy == 0.0
        assert transform.dz == 0.0
        assert transform.rx == 0.0
        assert transform.ry == 0.0
        assert transform.rz == 0.0

    def test_current_transform_reflects_preferences(self, qtbot):
        """current_transform returns values from preferences."""
        prefs = UserPreferences(
            transform_dx=10.5,
            transform_dy=20.0,
            transform_dz=-5.0,
            transform_rx=1.5,
            transform_ry=2.5,
            transform_rz=3.5,
        )
        window = MainWindow(preferences=prefs)
        qtbot.addWidget(window)

        transform = window.current_transform
        assert transform.dx == 10.5
        assert transform.dy == 20.0
        assert transform.dz == -5.0
        assert transform.rx == 1.5
        assert transform.ry == 2.5
        assert transform.rz == 3.5

    def test_transform_requested_signal_exists(self, main_window):
        """MainWindow has transform_requested signal."""
        assert hasattr(main_window, "transform_requested")

    def test_transform_requested_signal_can_be_connected(self, main_window):
        """transform_requested signal can be connected to a slot."""
        received = []
        main_window.transform_requested.connect(lambda t: received.append(t))
        # No assertion needed - test passes if connection doesn't raise


class TestStatusBar:
    """Tests for Section 8.2: Status bar with diagnostics."""

    def test_sample_rate_display_initial_state(self, main_window):
        """Sample rate label shows placeholder initially."""
        assert "---" in main_window._sample_rate_label.text()

    def test_update_sample_rate(self, main_window):
        """update_sample_rate updates the displayed rate."""
        main_window.update_sample_rate(1000.0)
        assert "1000.0 Hz" in main_window._sample_rate_label.text()

    def test_buffer_status_display_initial_state(self, main_window):
        """Buffer status label shows placeholder initially."""
        assert "---" in main_window._buffer_status_label.text()

    def test_update_buffer_status(self, main_window):
        """update_buffer_status updates the displayed fill percentage."""
        main_window.update_buffer_status(75.5)
        assert "75%" in main_window._buffer_status_label.text()

    def test_packet_loss_display_initial_state(self, main_window):
        """Packet loss label shows zero initially."""
        assert "0" in main_window._packet_loss_label.text()

    def test_update_packet_loss_zero(self, main_window):
        """update_packet_loss shows zero without styling."""
        main_window.update_packet_loss(0)
        assert "0" in main_window._packet_loss_label.text()
        assert "color" not in main_window._packet_loss_label.styleSheet().lower() or \
               main_window._packet_loss_label.styleSheet() == ""

    def test_update_packet_loss_nonzero_shows_red(self, main_window):
        """update_packet_loss with nonzero shows red styling."""
        main_window.update_packet_loss(5)
        assert "5" in main_window._packet_loss_label.text()
        assert "F44336" in main_window._packet_loss_label.styleSheet()

    def test_dropped_count_display_initial_state(self, main_window):
        """Dropped counter label shows zero initially."""
        assert "0" in main_window._dropped_label.text()

    def test_update_dropped_count_zero(self, main_window):
        """update_dropped_count shows zero without styling."""
        main_window.update_dropped_count(0)
        assert "Dropped: 0" in main_window._dropped_label.text()
        assert "color" not in main_window._dropped_label.styleSheet().lower() or \
               main_window._dropped_label.styleSheet() == ""

    def test_update_dropped_count_nonzero_shows_warning_color(self, main_window):
        """update_dropped_count with nonzero shows warning styling."""
        main_window.update_dropped_count(10)
        assert "Dropped: 10" in main_window._dropped_label.text()
        assert "FF9800" in main_window._dropped_label.styleSheet()

    def test_warning_label_empty_initially(self, main_window):
        """Warning label is empty initially."""
        assert main_window._warning_label.text() == ""

    def test_show_warning(self, main_window):
        """show_warning displays the warning message."""
        main_window.show_warning("High packet loss detected")
        assert main_window._warning_label.text() == "High packet loss detected"

    def test_clear_warning(self, main_window):
        """clear_warning removes the warning message."""
        main_window.show_warning("Some warning")
        main_window.clear_warning()
        assert main_window._warning_label.text() == ""

    def test_show_status_message(self, main_window):
        """show_status_message shows a temporary message."""
        main_window.show_status_message("Test message", timeout_ms=1000)
        assert main_window._status_bar.currentMessage() == "Test message"

    def test_status_bar_has_all_required_elements(self, main_window):
        """Status bar contains all required diagnostic elements."""
        assert hasattr(main_window, "_sample_rate_label")
        assert hasattr(main_window, "_buffer_status_label")
        assert hasattr(main_window, "_packet_loss_label")
        assert hasattr(main_window, "_dropped_label")
        assert hasattr(main_window, "_warning_label")
