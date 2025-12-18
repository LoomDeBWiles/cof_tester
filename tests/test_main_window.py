"""Tests for MainWindow keyboard shortcuts."""

import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

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

    def test_stop_shortcut_ctrl_s(self, main_window):
        """Stop shortcut is Ctrl+S."""
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_S)
        action = find_action_by_shortcut(main_window, shortcut)
        assert action is not None, "Stop shortcut (Ctrl+S) not found"
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
        """Ctrl+S shortcut triggers record_stopped signal when recording."""
        signals_received = []
        main_window.recording_controls.record_stopped.connect(
            lambda: signals_received.append("record_stopped")
        )
        main_window.recording_controls.set_output_path("/tmp")
        main_window.recording_controls.set_recording(True)

        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_S)
        action = find_action_by_shortcut(main_window, shortcut)
        action.trigger()

        assert "record_stopped" in signals_received

    def test_stop_shortcut_does_nothing_when_not_recording(self, main_window, qtbot):
        """Ctrl+S shortcut does nothing when not recording."""
        signals_received = []
        main_window.recording_controls.record_stopped.connect(
            lambda: signals_received.append("record_stopped")
        )

        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_S)
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
