"""Status bar diagnostics helpers.

This module provides:
- A small immutable snapshot representing the status bar state.
- A formatter for deriving warnings from acquisition statistics.
- A QtCore-only poller that periodically applies snapshots to a target.

The poller intentionally depends only on ``PySide6.QtCore`` so it can be tested in
headless environments where QtGui/QtWidgets native libraries may be unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from PySide6.QtCore import QObject, QTimer

from gsdv.acquisition import AcquisitionState, AcquisitionStats


@dataclass(frozen=True, slots=True)
class StatusBarSnapshot:
    """UI-ready diagnostic values for the status bar."""

    sample_rate_hz: float
    buffer_fill_percent: float
    packets_lost: int
    dropped_by_app: int
    warning_message: str | None


class StatusBarTarget(Protocol):
    """Duck-typed target that can be updated from a StatusBarSnapshot."""

    def update_sample_rate(self, rate_hz: float) -> None: ...

    def update_buffer_status(self, fill_percent: float) -> None: ...

    def update_packet_loss(self, count: int) -> None: ...

    def update_dropped_count(self, count: int) -> None: ...

    def show_warning(self, message: str) -> None: ...

    def clear_warning(self) -> None: ...


def build_status_warning(stats: AcquisitionStats, *, dropped_by_app: int = 0) -> str | None:
    """Build a single status-bar warning string from current diagnostics."""

    parts: list[str] = []

    if stats.packets_lost > 0:
        parts.append(f"Packet loss: {stats.packets_lost} ({stats.loss_ratio:.1%})")

    if stats.receive_errors > 0:
        parts.append(f"Receive errors: {stats.receive_errors}")

    if dropped_by_app > 0:
        parts.append(f"Dropped by app: {dropped_by_app}")

    return " | ".join(parts) if parts else None


def status_bar_snapshot_from_acquisition(
    stats: AcquisitionStats,
    *,
    dropped_by_app: int = 0,
    show_when_stopped: bool = False,
) -> StatusBarSnapshot | None:
    """Convert acquisition stats into a snapshot for the status bar.

    Args:
        stats: Current acquisition statistics.
        dropped_by_app: Count of samples dropped due to backpressure in the app.
        show_when_stopped: If False (default), returns None unless acquisition is RUNNING.

    Returns:
        StatusBarSnapshot when diagnostics should be displayed, otherwise None.
    """

    if not show_when_stopped and stats.state != AcquisitionState.RUNNING:
        return None

    return StatusBarSnapshot(
        sample_rate_hz=stats.samples_per_second,
        buffer_fill_percent=stats.buffer_stats.fill_ratio * 100.0,
        packets_lost=stats.packets_lost,
        dropped_by_app=dropped_by_app,
        warning_message=build_status_warning(stats, dropped_by_app=dropped_by_app),
    )


class StatusBarPoller(QObject):
    """Periodically pulls a snapshot and applies it to a status bar target."""

    def __init__(
        self,
        *,
        target: StatusBarTarget,
        snapshot_provider: Callable[[], StatusBarSnapshot | None],
        interval_ms: int = 250,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if interval_ms <= 0:
            raise ValueError(f"interval_ms must be positive, got {interval_ms}")

        self._target = target
        self._snapshot_provider = snapshot_provider

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_timeout)

    @property
    def interval_ms(self) -> int:
        """Polling interval in milliseconds."""
        return self._timer.interval()

    def start(self) -> None:
        """Start periodic polling."""
        self._timer.start()

    def stop(self) -> None:
        """Stop periodic polling."""
        self._timer.stop()

    def is_running(self) -> bool:
        """Return whether the poller is currently active."""
        return self._timer.isActive()

    def _on_timeout(self) -> None:
        try:
            snapshot = self._snapshot_provider()
        except Exception as exc:
            # Fail safe: stop the timer so we don't spam the UI.
            self.stop()
            self._best_effort_warning(f"Diagnostics update stopped: {type(exc).__name__}")
            return

        if snapshot is None:
            return

        try:
            self._target.update_sample_rate(snapshot.sample_rate_hz)
            self._target.update_buffer_status(snapshot.buffer_fill_percent)
            self._target.update_packet_loss(snapshot.packets_lost)
            self._target.update_dropped_count(snapshot.dropped_by_app)

            if snapshot.warning_message:
                self._target.show_warning(snapshot.warning_message)
            else:
                self._target.clear_warning()
        except Exception as exc:
            self.stop()
            self._best_effort_warning(f"Diagnostics update stopped: {type(exc).__name__}")

    def _best_effort_warning(self, message: str) -> None:
        try:
            self._target.show_warning(message)
        except Exception:
            # Last resort: ignore UI update failures here.
            return

