"""Tests for diagnostics status bar helpers (non-QtGui)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from gsdv.acquisition import AcquisitionState, AcquisitionStats, RingBufferStats
from gsdv.diagnostics.status_bar import (
    StatusBarPoller,
    StatusBarSnapshot,
    build_status_warning,
    status_bar_snapshot_from_acquisition,
)


def _run_event_loop_ms(duration_ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(duration_ms, loop.quit)
    loop.exec()


class _FakeStatusBarTarget:
    def __init__(self) -> None:
        self.sample_rate_hz: float | None = None
        self.buffer_fill_percent: float | None = None
        self.packets_lost: int | None = None
        self.dropped_by_app: int | None = None
        self.warning_message: str | None = None
        self.clear_warning_calls = 0

    def update_sample_rate(self, rate_hz: float) -> None:
        self.sample_rate_hz = rate_hz

    def update_buffer_status(self, fill_percent: float) -> None:
        self.buffer_fill_percent = fill_percent

    def update_packet_loss(self, count: int) -> None:
        self.packets_lost = count

    def update_dropped_count(self, count: int) -> None:
        self.dropped_by_app = count

    def show_warning(self, message: str) -> None:
        self.warning_message = message

    def clear_warning(self) -> None:
        self.warning_message = None
        self.clear_warning_calls += 1


@pytest.fixture
def base_stats() -> AcquisitionStats:
    buffer_stats = RingBufferStats(capacity=100, size=50, total_written=50, overwrites=0)
    return AcquisitionStats(
        state=AcquisitionState.RUNNING,
        buffer_stats=buffer_stats,
        packets_received=100,
        packets_lost=0,
        receive_errors=0,
        samples_per_second=1000.0,
    )


class TestBuildStatusWarning:
    def test_none_when_no_issues(self, base_stats: AcquisitionStats) -> None:
        assert build_status_warning(base_stats, dropped_by_app=0) is None

    def test_includes_packet_loss_ratio(self, base_stats: AcquisitionStats) -> None:
        stats = replace(base_stats, packets_lost=10, packets_received=90)
        warning = build_status_warning(stats, dropped_by_app=0)
        assert warning is not None
        assert "Packet loss: 10" in warning
        assert "10.0%" in warning

    def test_includes_receive_errors(self, base_stats: AcquisitionStats) -> None:
        stats = replace(base_stats, receive_errors=2)
        warning = build_status_warning(stats, dropped_by_app=0)
        assert warning == "Receive errors: 2"

    def test_includes_dropped_by_app(self, base_stats: AcquisitionStats) -> None:
        warning = build_status_warning(base_stats, dropped_by_app=5)
        assert warning == "Dropped by app: 5"

    def test_combines_multiple_warnings(self, base_stats: AcquisitionStats) -> None:
        stats = replace(base_stats, packets_lost=1, packets_received=9, receive_errors=2)
        warning = build_status_warning(stats, dropped_by_app=3)
        assert warning is not None
        assert "Packet loss: 1" in warning
        assert "Receive errors: 2" in warning
        assert "Dropped by app: 3" in warning


class TestStatusBarSnapshotFromAcquisition:
    def test_returns_none_when_stopped_by_default(self, base_stats: AcquisitionStats) -> None:
        stats = replace(base_stats, state=AcquisitionState.STOPPED)
        assert status_bar_snapshot_from_acquisition(stats) is None

    def test_returns_snapshot_when_running(self, base_stats: AcquisitionStats) -> None:
        snapshot = status_bar_snapshot_from_acquisition(base_stats, dropped_by_app=7)
        assert snapshot is not None
        assert snapshot.sample_rate_hz == 1000.0
        assert snapshot.buffer_fill_percent == 50.0
        assert snapshot.packets_lost == 0
        assert snapshot.dropped_by_app == 7


class TestStatusBarPoller:
    def test_polls_and_updates_target(self) -> None:
        QCoreApplication.instance() or QCoreApplication([])

        target = _FakeStatusBarTarget()
        snapshot = StatusBarSnapshot(
            sample_rate_hz=123.0,
            buffer_fill_percent=42.0,
            packets_lost=3,
            dropped_by_app=4,
            warning_message="Packet loss: 3 (1.0%)",
        )

        poller = StatusBarPoller(target=target, snapshot_provider=lambda: snapshot, interval_ms=10)
        poller.start()

        _run_event_loop_ms(50)

        poller.stop()

        assert target.sample_rate_hz == 123.0
        assert target.buffer_fill_percent == 42.0
        assert target.packets_lost == 3
        assert target.dropped_by_app == 4
        assert target.warning_message == "Packet loss: 3 (1.0%)"

    def test_clears_warning_when_none(self) -> None:
        QCoreApplication.instance() or QCoreApplication([])

        target = _FakeStatusBarTarget()
        snapshot = StatusBarSnapshot(
            sample_rate_hz=1.0,
            buffer_fill_percent=2.0,
            packets_lost=0,
            dropped_by_app=0,
            warning_message=None,
        )

        poller = StatusBarPoller(target=target, snapshot_provider=lambda: snapshot, interval_ms=10)
        poller.start()
        _run_event_loop_ms(50)
        poller.stop()

        assert target.warning_message is None
        assert target.clear_warning_calls > 0
