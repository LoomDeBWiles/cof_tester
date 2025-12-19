"""Sensor controller for managing connection and data flow."""

import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from gsdv.acquisition.acquisition_engine import AcquisitionEngine
from gsdv.errors import BiasError
from gsdv.models import CalibrationInfo, SampleRecord
from gsdv.protocols import BiasService, RdtStatistics, get_calibration_with_fallback


class ConnectionState:
    """Connection state constants."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


class SensorController(QObject):
    """Controller for sensor connection and data acquisition.

    Manages the lifecycle of sensor connections:
    - Fetching calibration data
    - Starting/stopping the acquisition engine
    - Handling bias operations
    - Propagating samples and errors to the UI

    Signals:
        connection_state_changed(str, str): (state, message) when state changes.
        calibration_loaded(CalibrationInfo): Emitted when calibration is fetched.
        sample_received(SampleRecord): Forwarded from acquisition engine.
        statistics_updated(int, int, float): (packets_received, packets_lost, rate_hz).
        error_occurred(str, str): (error_code, message) for user display.
    """

    connection_state_changed = Signal(str, str)  # state, message
    calibration_loaded = Signal(object)  # CalibrationInfo
    sample_received = Signal(object)  # SampleRecord
    statistics_updated = Signal(int, int, float)  # packets_received, packets_lost, rate_hz
    error_occurred = Signal(str, str)  # error_code, message

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize the sensor controller."""
        super().__init__(parent)
        self._acquisition_engine: Optional[AcquisitionEngine] = None
        self._bias_service: Optional[BiasService] = None
        self._calibration: Optional[CalibrationInfo] = None
        self._current_ip: Optional[str] = None
        self._state = ConnectionState.DISCONNECTED

        # For sample rate calculation
        self._last_stats_time_ns: Optional[int] = None
        self._last_packet_count: int = 0

    @property
    def state(self) -> str:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Whether currently connected and streaming."""
        return self._state == ConnectionState.CONNECTED

    @property
    def calibration(self) -> Optional[CalibrationInfo]:
        """Current calibration data, if connected."""
        return self._calibration

    @property
    def current_ip(self) -> Optional[str]:
        """Currently connected sensor IP."""
        return self._current_ip

    def _set_state(self, state: str, message: str = "") -> None:
        """Update state and emit signal."""
        self._state = state
        self.connection_state_changed.emit(state, message)

    @Slot(str)
    def connect_to_sensor(self, ip: str) -> None:
        """Connect to a sensor at the given IP address.

        Fetches calibration, then starts streaming in a background thread.

        Args:
            ip: Sensor IP address.
        """
        if self._state not in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
            return

        self._set_state(ConnectionState.CONNECTING, f"Connecting to {ip}...")
        self._current_ip = ip

        # Fetch calibration (blocking, but quick)
        try:
            self._calibration = get_calibration_with_fallback(ip)
            self.calibration_loaded.emit(self._calibration)
        except Exception as e:
            self._set_state(ConnectionState.ERROR, f"Calibration failed: {e}")
            self.error_occurred.emit("CAL-004", str(e))
            return

        # Create bias service for this sensor
        self._bias_service = BiasService(ip)

        # Start acquisition engine
        self._acquisition_engine = AcquisitionEngine(ip, self._calibration)
        self._acquisition_engine.sample_received.connect(self._on_sample_received)
        self._acquisition_engine.statistics_updated.connect(self._on_statistics_updated)
        self._acquisition_engine.error_occurred.connect(self._on_acquisition_error)
        self._acquisition_engine.streaming_stopped.connect(self._on_streaming_stopped)

        self._last_stats_time_ns = None
        self._last_packet_count = 0

        self._acquisition_engine.start()
        self._set_state(ConnectionState.CONNECTED, f"Connected to {ip}")

    @Slot()
    def disconnect_from_sensor(self) -> None:
        """Disconnect from the current sensor."""
        if self._state != ConnectionState.CONNECTED:
            return

        self._set_state(ConnectionState.DISCONNECTING, "Disconnecting...")

        if self._acquisition_engine is not None:
            self._acquisition_engine.request_stop()
            # Wait briefly for thread to finish
            if not self._acquisition_engine.wait(2000):  # 2 second timeout
                self._acquisition_engine.terminate()
            self._acquisition_engine = None

        self._bias_service = None
        self._calibration = None
        self._current_ip = None

        self._set_state(ConnectionState.DISCONNECTED, "Disconnected")

    @Slot()
    def apply_bias(self) -> None:
        """Apply bias (tare) to the sensor.

        Uses device bias (hardware tare).
        """
        if self._bias_service is None:
            self.error_occurred.emit("BIAS-001", "Not connected to a sensor")
            return

        try:
            self._bias_service.apply_device_bias()
        except BiasError as e:
            self.error_occurred.emit("CAL-005", str(e))
        except Exception as e:
            self.error_occurred.emit("BIAS-002", str(e))

    def _on_sample_received(self, sample: SampleRecord) -> None:
        """Handle sample from acquisition engine."""
        self.sample_received.emit(sample)

    def _on_statistics_updated(self, stats: RdtStatistics) -> None:
        """Handle statistics update from acquisition engine."""
        current_time_ns = time.monotonic_ns()

        # Calculate sample rate
        rate_hz = 0.0
        if self._last_stats_time_ns is not None:
            elapsed_ns = current_time_ns - self._last_stats_time_ns
            elapsed_s = elapsed_ns / 1e9
            if elapsed_s > 0:
                new_packets = stats.packets_received - self._last_packet_count
                rate_hz = new_packets / elapsed_s

        self._last_stats_time_ns = current_time_ns
        self._last_packet_count = stats.packets_received

        self.statistics_updated.emit(
            stats.packets_received,
            stats.packets_lost,
            rate_hz,
        )

    def _on_acquisition_error(self, error_message: str) -> None:
        """Handle error from acquisition engine."""
        self.error_occurred.emit("ACQ-001", error_message)

    def _on_streaming_stopped(self) -> None:
        """Handle acquisition engine stopping."""
        if self._state == ConnectionState.CONNECTED:
            # Unexpected stop
            self._set_state(ConnectionState.ERROR, "Streaming stopped unexpectedly")
