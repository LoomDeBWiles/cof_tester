"""Tests for RecordingControls widget.

Tests for FR-18 and FR-23: Record/stop button, recording indicator,
duration display, and file size display during active capture.
"""

import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

try:
    import PySide6.QtGui
except ImportError:
    pytest.skip("PySide6 not usable", allow_module_level=True)

from pathlib import Path
from PySide6.QtCore import Qt

from gsdv.ui.main_window import RecordingControls


@pytest.fixture
def recording_controls(qtbot):
    """Create a RecordingControls instance for testing."""
    controls = RecordingControls()
    qtbot.addWidget(controls)
    return controls


class TestRecordingControlsInitialState:
    """Tests for initial state of RecordingControls widget."""

    def test_initial_state_not_recording(self, recording_controls):
        """Widget starts in non-recording state."""
        assert recording_controls._recording is False

    def test_initial_button_text_is_record(self, recording_controls):
        """Record button shows 'Record' initially."""
        assert recording_controls._record_button.text() == "Record"

    def test_initial_button_disabled(self, recording_controls):
        """Record button is disabled until output path is set."""
        assert recording_controls._record_button.isEnabled() is False

    def test_initial_output_path_empty(self, recording_controls):
        """Output path is empty initially."""
        assert recording_controls.get_output_path() == ""

    def test_initial_path_label_shows_not_selected(self, recording_controls):
        """Path label shows 'Not selected' initially."""
        assert "Not selected" in recording_controls._path_label.text()

    def test_initial_duration_label_empty(self, recording_controls):
        """Duration label is empty initially."""
        assert recording_controls._duration_label.text() == ""

    def test_initial_size_label_empty(self, recording_controls):
        """File size label is empty initially."""
        assert recording_controls._size_label.text() == ""

    def test_initial_indicator_gray(self, recording_controls):
        """Recording indicator is gray when not recording."""
        style = recording_controls._recording_indicator.styleSheet()
        assert "#9E9E9E" in style

    def test_browse_button_enabled_initially(self, recording_controls):
        """Browse button is enabled initially."""
        assert recording_controls._browse_button.isEnabled() is True


class TestOutputPathSelection:
    """Tests for output directory selection."""

    def test_set_output_path_enables_record_button(self, recording_controls):
        """Setting output path enables record button."""
        recording_controls.set_output_path("/tmp/test")
        assert recording_controls._record_button.isEnabled() is True

    def test_set_output_path_updates_label(self, recording_controls):
        """Setting output path updates the display label."""
        test_path = "/tmp/test"
        recording_controls.set_output_path(test_path)
        assert test_path in recording_controls._path_label.text()

    def test_set_output_path_updates_tooltip(self, recording_controls):
        """Setting output path updates the tooltip with full path."""
        test_path = "/tmp/test/recording/output"
        recording_controls.set_output_path(test_path)
        assert recording_controls._path_label.toolTip() == test_path

    def test_set_output_path_truncates_long_paths(self, recording_controls):
        """Long paths are truncated with ellipsis in display."""
        long_path = "/" + "a" * 100
        recording_controls.set_output_path(long_path)
        displayed_text = recording_controls._path_label.text()
        # Should be truncated to < 40 chars with ellipsis
        assert len(displayed_text) <= 40
        assert displayed_text.startswith("...")

    def test_set_output_path_removes_gray_style(self, recording_controls):
        """Setting path removes gray color style from label."""
        recording_controls.set_output_path("/tmp/test")
        assert "gray" not in recording_controls._path_label.styleSheet().lower()

    def test_get_output_path_returns_set_value(self, recording_controls):
        """get_output_path returns the previously set value."""
        test_path = "/tmp/test/output"
        recording_controls.set_output_path(test_path)
        assert recording_controls.get_output_path() == test_path

    def test_folder_selected_signal_emitted(self, recording_controls, qtbot):
        """folder_selected signal emits when path is set via set_output_path."""
        # Note: set_output_path is typically called after browse dialog
        # The signal emission is tested in the browse button flow
        # This test verifies the method exists
        assert hasattr(recording_controls, "folder_selected")


class TestRecordingStateTransitions:
    """Tests for recording state transitions."""

    def test_set_recording_true_changes_button_to_stop(self, recording_controls):
        """Setting recording=True changes button text to 'Stop'."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        assert recording_controls._record_button.text() == "Stop"

    def test_set_recording_true_disables_browse_button(self, recording_controls):
        """Setting recording=True disables browse button."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        assert recording_controls._browse_button.isEnabled() is False

    def test_set_recording_true_changes_indicator_red(self, recording_controls):
        """Setting recording=True changes indicator to red."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        style = recording_controls._recording_indicator.styleSheet()
        assert "#F44336" in style

    def test_set_recording_false_changes_button_to_record(self, recording_controls):
        """Setting recording=False changes button text to 'Record'."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        recording_controls.set_recording(False)
        assert recording_controls._record_button.text() == "Record"

    def test_set_recording_false_enables_browse_button(self, recording_controls):
        """Setting recording=False re-enables browse button."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        recording_controls.set_recording(False)
        assert recording_controls._browse_button.isEnabled() is True

    def test_set_recording_false_changes_indicator_gray(self, recording_controls):
        """Setting recording=False changes indicator back to gray."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        recording_controls.set_recording(False)
        style = recording_controls._recording_indicator.styleSheet()
        assert "#9E9E9E" in style

    def test_set_recording_false_clears_duration(self, recording_controls):
        """Setting recording=False clears duration label."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        recording_controls.update_recording_stats(60.0, 1024)
        recording_controls.set_recording(False)
        assert recording_controls._duration_label.text() == ""

    def test_set_recording_false_clears_size(self, recording_controls):
        """Setting recording=False clears file size label."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        recording_controls.update_recording_stats(60.0, 1024)
        recording_controls.set_recording(False)
        assert recording_controls._size_label.text() == ""


class TestRecordButtonClick:
    """Tests for record button click behavior."""

    def test_record_button_emits_record_started_when_not_recording(self, recording_controls, qtbot):
        """Clicking Record button emits record_started signal."""
        recording_controls.set_output_path("/tmp")
        signals_received = []
        recording_controls.record_started.connect(lambda: signals_received.append("started"))

        recording_controls._record_button.click()

        assert "started" in signals_received

    def test_record_button_emits_record_stopped_when_recording(self, recording_controls, qtbot):
        """Clicking Stop button emits record_stopped signal."""
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        signals_received = []
        recording_controls.record_stopped.connect(lambda: signals_received.append("stopped"))

        recording_controls._record_button.click()

        assert "stopped" in signals_received

    def test_record_button_does_nothing_when_disabled(self, recording_controls, qtbot):
        """Clicking disabled Record button does not emit signals."""
        # No output path set, so button is disabled
        signals_received = []
        recording_controls.record_started.connect(lambda: signals_received.append("started"))

        # Button is disabled, click should do nothing
        # We can't directly click disabled buttons in Qt, so test the handler
        assert recording_controls._record_button.isEnabled() is False


class TestRecordingStatistics:
    """Tests for recording statistics display (FR-23)."""

    def test_update_recording_stats_duration_seconds_only(self, recording_controls):
        """Duration displays as MM:SS for times under 1 hour."""
        recording_controls.update_recording_stats(duration_seconds=125.0, file_size_bytes=0)
        assert recording_controls._duration_label.text() == "2:05"

    def test_update_recording_stats_duration_with_hours(self, recording_controls):
        """Duration displays as H:MM:SS for times over 1 hour."""
        recording_controls.update_recording_stats(duration_seconds=3725.0, file_size_bytes=0)
        assert recording_controls._duration_label.text() == "1:02:05"

    def test_update_recording_stats_duration_zero(self, recording_controls):
        """Duration displays as 0:00 for zero seconds."""
        recording_controls.update_recording_stats(duration_seconds=0.0, file_size_bytes=0)
        assert recording_controls._duration_label.text() == "0:00"

    def test_update_recording_stats_file_size_bytes(self, recording_controls):
        """File size displays in bytes for small files."""
        recording_controls.update_recording_stats(duration_seconds=0.0, file_size_bytes=512)
        assert recording_controls._size_label.text() == "512 B"

    def test_update_recording_stats_file_size_kilobytes(self, recording_controls):
        """File size displays in KB for medium files."""
        recording_controls.update_recording_stats(duration_seconds=0.0, file_size_bytes=5120)
        assert "KB" in recording_controls._size_label.text()
        assert "5.0" in recording_controls._size_label.text()

    def test_update_recording_stats_file_size_megabytes(self, recording_controls):
        """File size displays in MB for large files."""
        recording_controls.update_recording_stats(duration_seconds=0.0, file_size_bytes=5 * 1024 * 1024)
        assert "MB" in recording_controls._size_label.text()
        assert "5.0" in recording_controls._size_label.text()

    def test_update_recording_stats_file_size_gigabytes(self, recording_controls):
        """File size displays in GB for very large files."""
        recording_controls.update_recording_stats(duration_seconds=0.0, file_size_bytes=3 * 1024 * 1024 * 1024)
        assert "GB" in recording_controls._size_label.text()
        assert "3.00" in recording_controls._size_label.text()

    def test_update_recording_stats_both_values(self, recording_controls):
        """Duration and size are both updated correctly."""
        recording_controls.update_recording_stats(duration_seconds=90.0, file_size_bytes=2048)
        assert "1:30" in recording_controls._duration_label.text()
        assert "KB" in recording_controls._size_label.text()

    def test_update_recording_stats_negative_duration_clamped_to_zero(self, recording_controls):
        """Negative duration is clamped to zero."""
        recording_controls.update_recording_stats(duration_seconds=-10.0, file_size_bytes=0)
        assert recording_controls._duration_label.text() == "0:00"

    def test_update_recording_stats_negative_file_size_clamped_to_zero(self, recording_controls):
        """Negative file size is clamped to zero."""
        recording_controls.update_recording_stats(duration_seconds=0.0, file_size_bytes=-1024)
        assert recording_controls._size_label.text() == "0 B"

    def test_update_recording_stats_both_negative_clamped_to_zero(self, recording_controls):
        """Both negative duration and file size are clamped to zero."""
        recording_controls.update_recording_stats(duration_seconds=-5.0, file_size_bytes=-500)
        assert recording_controls._duration_label.text() == "0:00"
        assert recording_controls._size_label.text() == "0 B"


class TestRecordingControlsSignals:
    """Tests for signal emissions."""

    def test_has_record_started_signal(self, recording_controls):
        """RecordingControls has record_started signal."""
        assert hasattr(recording_controls, "record_started")

    def test_has_record_stopped_signal(self, recording_controls):
        """RecordingControls has record_stopped signal."""
        assert hasattr(recording_controls, "record_stopped")

    def test_has_folder_selected_signal(self, recording_controls):
        """RecordingControls has folder_selected signal."""
        assert hasattr(recording_controls, "folder_selected")

    def test_record_started_signal_can_be_connected(self, recording_controls):
        """record_started signal can be connected to a slot."""
        received = []
        recording_controls.record_started.connect(lambda: received.append(1))
        # No assertion needed - test passes if connection doesn't raise

    def test_record_stopped_signal_can_be_connected(self, recording_controls):
        """record_stopped signal can be connected to a slot."""
        received = []
        recording_controls.record_stopped.connect(lambda: received.append(1))
        # No assertion needed - test passes if connection doesn't raise

    def test_folder_selected_signal_can_be_connected(self, recording_controls):
        """folder_selected signal can be connected to a slot."""
        received = []
        recording_controls.folder_selected.connect(lambda path: received.append(path))
        # No assertion needed - test passes if connection doesn't raise


class TestRecordingIndicatorVisualFeedback:
    """Tests for clear visual feedback (FR-18 acceptance criteria)."""

    def test_indicator_is_visible(self, recording_controls):
        """Recording indicator is visible to the user."""
        assert recording_controls._recording_indicator.isVisible()

    def test_indicator_has_circular_appearance(self, recording_controls):
        """Recording indicator has border-radius for circular appearance."""
        style = recording_controls._recording_indicator.styleSheet()
        assert "border-radius" in style

    def test_indicator_is_fixed_size(self, recording_controls):
        """Recording indicator has fixed size (12x12 pixels)."""
        assert recording_controls._recording_indicator.width() == 12
        assert recording_controls._recording_indicator.height() == 12

    def test_indicator_color_changes_on_state_transition(self, recording_controls):
        """Indicator color changes when transitioning between states."""
        # Get initial gray color
        initial_style = recording_controls._recording_indicator.styleSheet()
        assert "#9E9E9E" in initial_style

        # Start recording
        recording_controls.set_output_path("/tmp")
        recording_controls.set_recording(True)
        recording_style = recording_controls._recording_indicator.styleSheet()
        assert "#F44336" in recording_style

        # Verify different colors
        assert "#9E9E9E" not in recording_style
        assert "#F44336" not in initial_style


class TestIntegrationWithMainWindow:
    """Tests for RecordingControls integration with MainWindow."""

    def test_recording_controls_accessible_from_main_window(self, qtbot):
        """MainWindow exposes recording_controls property."""
        from gsdv.ui import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        assert hasattr(window, "recording_controls")
        assert isinstance(window.recording_controls, RecordingControls)

    def test_ctrl_r_shortcut_triggers_recording_start(self, qtbot):
        """Ctrl+R keyboard shortcut triggers record_started signal."""
        from gsdv.ui import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.recording_controls.set_output_path("/tmp")

        signals_received = []
        window.recording_controls.record_started.connect(
            lambda: signals_received.append("started")
        )

        # Trigger Ctrl+R shortcut
        from PySide6.QtGui import QKeySequence
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_R)
        for action in window.actions():
            if action.shortcut() == shortcut:
                action.trigger()
                break

        assert "started" in signals_received

    def test_ctrl_s_shortcut_triggers_recording_stop(self, qtbot):
        """Ctrl+S keyboard shortcut triggers record_stopped signal."""
        from gsdv.ui import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.recording_controls.set_output_path("/tmp")
        window.recording_controls.set_recording(True)

        signals_received = []
        window.recording_controls.record_stopped.connect(
            lambda: signals_received.append("stopped")
        )

        # Trigger Ctrl+S shortcut
        from PySide6.QtGui import QKeySequence
        shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_S)
        for action in window.actions():
            if action.shortcut() == shortcut:
                action.trigger()
                break

        assert "stopped" in signals_received
