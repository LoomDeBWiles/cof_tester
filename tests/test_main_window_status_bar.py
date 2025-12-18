"""Integration tests for status bar with MainWindow.

Tests that the status bar poller can integrate with MainWindow to display
real-time diagnostics including sample rate, buffer fill, packet loss, and warnings.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

try:
    import PySide6.QtGui
except ImportError:
    pytest.skip("PySide6 not usable", allow_module_level=True)

from PySide6.QtCore import QEventLoop, QTimer

from gsdv.acquisition import AcquisitionState, AcquisitionStats, RingBufferStats
from gsdv.diagnostics.status_bar import (
    StatusBarPoller,
    status_bar_snapshot_from_acquisition,
)
from gsdv.ui import MainWindow


def _run_event_loop_ms(duration_ms: int) -> None:
    """Run Qt event loop for a specified duration."""
    loop = QEventLoop()
    QTimer.singleShot(duration_ms, loop.quit)
    loop.exec()


@pytest.fixture
def main_window(qtbot):
    """Create a MainWindow instance for testing."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window


class TestMainWindowStatusBarIntegration:
    """Tests for status bar integration with MainWindow."""

    def test_main_window_implements_status_bar_target_protocol(self, main_window):
        """MainWindow implements all methods required by StatusBarTarget protocol."""
        assert hasattr(main_window, "update_sample_rate")
        assert hasattr(main_window, "update_buffer_status")
        assert hasattr(main_window, "update_packet_loss")
        assert hasattr(main_window, "update_dropped_count")
        assert hasattr(main_window, "show_warning")
        assert hasattr(main_window, "clear_warning")

    def test_status_bar_displays_sample_rate(self, main_window):
        """Status bar updates sample rate display."""
        main_window.update_sample_rate(1000.5)
        assert "1000.5 Hz" in main_window._sample_rate_label.text()

    def test_status_bar_displays_buffer_status(self, main_window):
        """Status bar updates buffer fill percentage."""
        main_window.update_buffer_status(42.3)
        assert "42%" in main_window._buffer_status_label.text()

    def test_status_bar_displays_packet_loss(self, main_window):
        """Status bar updates packet loss counter."""
        main_window.update_packet_loss(0)
        assert "0" in main_window._packet_loss_label.text()

        main_window.update_packet_loss(15)
        assert "15" in main_window._packet_loss_label.text()

    def test_status_bar_packet_loss_turns_red_when_nonzero(self, main_window):
        """Packet loss label turns red when losses occur."""
        main_window.update_packet_loss(0)
        style = main_window._packet_loss_label.styleSheet()
        assert "#F44336" not in style

        main_window.update_packet_loss(5)
        style = main_window._packet_loss_label.styleSheet()
        assert "#F44336" in style

    def test_status_bar_displays_dropped_count(self, main_window):
        """Status bar updates dropped samples counter."""
        main_window.update_dropped_count(0)
        assert "0" in main_window._dropped_label.text()

        main_window.update_dropped_count(23)
        assert "23" in main_window._dropped_label.text()

    def test_status_bar_dropped_turns_orange_when_nonzero(self, main_window):
        """Dropped samples label turns orange when drops occur."""
        main_window.update_dropped_count(0)
        style = main_window._dropped_label.styleSheet()
        assert "#FF9800" not in style

        main_window.update_dropped_count(3)
        style = main_window._dropped_label.styleSheet()
        assert "#FF9800" in style

    def test_status_bar_displays_warning(self, main_window):
        """Status bar shows warning message."""
        main_window.show_warning("Test warning message")
        assert main_window._warning_label.text() == "Test warning message"

    def test_status_bar_clears_warning(self, main_window):
        """Status bar clears warning message."""
        main_window.show_warning("Test warning")
        assert main_window._warning_label.text() == "Test warning"

        main_window.clear_warning()
        assert main_window._warning_label.text() == ""

    def test_poller_integrates_with_main_window(self, main_window, qtbot):
        """StatusBarPoller can poll and update MainWindow status bar."""
        buffer_stats = RingBufferStats(capacity=1000, size=420, total_written=420, overwrites=0)
        stats = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=95,
            packets_lost=5,
            receive_errors=0,
            samples_per_second=999.8,
        )

        def snapshot_provider():
            return status_bar_snapshot_from_acquisition(stats, dropped_by_app=3)

        poller = StatusBarPoller(
            target=main_window,
            snapshot_provider=snapshot_provider,
            interval_ms=50,
        )

        poller.start()
        _run_event_loop_ms(150)
        poller.stop()

        assert "999.8 Hz" in main_window._sample_rate_label.text()
        assert "42%" in main_window._buffer_status_label.text()
        assert "5" in main_window._packet_loss_label.text()
        assert "3" in main_window._dropped_label.text()
        assert "Packet loss: 5 (5.0%)" in main_window._warning_label.text()

    def test_poller_updates_in_real_time(self, main_window, qtbot):
        """StatusBarPoller updates display as stats change."""
        buffer_stats = RingBufferStats(capacity=1000, size=100, total_written=100, overwrites=0)
        stats = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=100,
            packets_lost=0,
            receive_errors=0,
            samples_per_second=1000.0,
        )

        stats_holder = {"current": stats}

        def snapshot_provider():
            return status_bar_snapshot_from_acquisition(stats_holder["current"], dropped_by_app=0)

        poller = StatusBarPoller(
            target=main_window,
            snapshot_provider=snapshot_provider,
            interval_ms=30,
        )

        poller.start()
        _run_event_loop_ms(80)

        assert "10%" in main_window._buffer_status_label.text()
        assert "0" in main_window._packet_loss_label.text()

        buffer_stats = RingBufferStats(capacity=1000, size=500, total_written=500, overwrites=0)
        stats_holder["current"] = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=95,
            packets_lost=5,
            receive_errors=0,
            samples_per_second=1000.0,
        )

        _run_event_loop_ms(80)
        poller.stop()

        assert "50%" in main_window._buffer_status_label.text()
        assert "5" in main_window._packet_loss_label.text()

    def test_poller_clears_warning_when_issues_resolve(self, main_window, qtbot):
        """StatusBarPoller clears warnings when problems are resolved."""
        buffer_stats = RingBufferStats(capacity=1000, size=100, total_written=100, overwrites=0)
        stats_with_loss = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=95,
            packets_lost=5,
            receive_errors=0,
            samples_per_second=1000.0,
        )

        stats_holder = {"current": stats_with_loss}

        def snapshot_provider():
            return status_bar_snapshot_from_acquisition(stats_holder["current"], dropped_by_app=0)

        poller = StatusBarPoller(
            target=main_window,
            snapshot_provider=snapshot_provider,
            interval_ms=30,
        )

        poller.start()
        _run_event_loop_ms(80)

        assert main_window._warning_label.text() != ""

        stats_no_loss = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=100,
            packets_lost=0,
            receive_errors=0,
            samples_per_second=1000.0,
        )
        stats_holder["current"] = stats_no_loss

        _run_event_loop_ms(80)
        poller.stop()

        assert main_window._warning_label.text() == ""

    def test_poller_shows_combined_warnings(self, main_window, qtbot):
        """StatusBarPoller displays combined warnings for multiple issues."""
        buffer_stats = RingBufferStats(capacity=1000, size=100, total_written=100, overwrites=0)
        stats = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=90,
            packets_lost=10,
            receive_errors=2,
            samples_per_second=1000.0,
        )

        def snapshot_provider():
            return status_bar_snapshot_from_acquisition(stats, dropped_by_app=5)

        poller = StatusBarPoller(
            target=main_window,
            snapshot_provider=snapshot_provider,
            interval_ms=50,
        )

        poller.start()
        _run_event_loop_ms(150)
        poller.stop()

        warning_text = main_window._warning_label.text()
        assert "Packet loss: 10" in warning_text
        assert "Receive errors: 2" in warning_text
        assert "Dropped by app: 5" in warning_text

    def test_poller_stops_cleanly(self, main_window, qtbot):
        """StatusBarPoller can be started and stopped multiple times."""
        buffer_stats = RingBufferStats(capacity=1000, size=100, total_written=100, overwrites=0)
        stats = AcquisitionStats(
            state=AcquisitionState.RUNNING,
            buffer_stats=buffer_stats,
            packets_received=100,
            packets_lost=0,
            receive_errors=0,
            samples_per_second=1000.0,
        )

        def snapshot_provider():
            return status_bar_snapshot_from_acquisition(stats, dropped_by_app=0)

        poller = StatusBarPoller(
            target=main_window,
            snapshot_provider=snapshot_provider,
            interval_ms=50,
        )

        assert not poller.is_running()

        poller.start()
        assert poller.is_running()
        _run_event_loop_ms(100)

        poller.stop()
        assert not poller.is_running()

        poller.start()
        assert poller.is_running()
        _run_event_loop_ms(100)

        poller.stop()
        assert not poller.is_running()
