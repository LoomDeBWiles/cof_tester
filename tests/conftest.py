"""Pytest configuration for GSDV tests."""

import socket
import time

import pytest


def _qt_is_available() -> bool:
    """Check if Qt is fully available (Python bindings and native libraries)."""
    try:
        from PySide6 import QtCore  # noqa: F401
        from PySide6 import QtGui  # noqa: F401
        from PySide6 import QtWidgets  # noqa: F401

        return True
    except (ImportError, OSError, Exception):
        return False


def pytest_configure(config):
    """Disable pytest-qt if Qt is not available."""
    if not _qt_is_available():
        try:
            config.pluginmanager.set_blocked("pytest-qt")
            config.pluginmanager.set_blocked("pytestqt")
            config.pluginmanager.set_blocked("pytest_qt")
        except Exception:
            pass


# Disable Qt test modules if Qt is not available
collect_ignore = []
if not _qt_is_available():
    collect_ignore.append("test_connection_panel.py")
    collect_ignore.append("test_integration_simulator.py")
    collect_ignore.append("test_issue_rw5_repro.py")
    collect_ignore.append("test_main_window.py")
    collect_ignore.append("test_plot_widget.py")
    collect_ignore.append("test_ui_accessibility.py")


def _acquisition_engine_available() -> bool:
    """Check if the acquisition engine module is implemented."""
    try:
        from gsdv.acquisition import AcquisitionEngine  # noqa: F401

        return True
    except ImportError:
        return False


# Disable acquisition tests if module not yet implemented
if not _acquisition_engine_available():
    collect_ignore.append("test_acquisition.py")


def _find_available_ports(count: int = 3, start: int = 59000) -> list[int]:
    """Find available ports for the simulator.

    Scans from start port upward to find unused ports.
    Tests both TCP and UDP availability.
    """
    ports = []
    port = start
    while len(ports) < count and port < 65535:
        tcp_ok = False
        udp_ok = False

        # Check TCP
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                tcp_ok = True
            except OSError:
                pass

        # Check UDP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                udp_ok = True
            except OSError:
                pass

        if tcp_ok and udp_ok:
            ports.append(port)

        port += 1
    return ports


@pytest.fixture
def sensor_simulator():
    """Provide a running sensor simulator for integration tests.

    The simulator is started before the test and stopped after.
    Uses dynamically allocated ports to avoid conflicts.

    Yields:
        SensorSimulator: A running simulator instance with config accessible via .config

    Example:
        def test_streaming(sensor_simulator):
            with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
                client.start_streaming()
                # ... test code ...
    """
    from gsdv.diagnostics.sensor_simulator import SensorSimulator, SimulatorConfig

    # Find available ports
    ports = _find_available_ports(3)
    if len(ports) < 3:
        pytest.skip("Could not find 3 available ports for simulator")

    config = SimulatorConfig(
        udp_port=ports[0],
        tcp_port=ports[1],
        http_port=ports[2],
        seed=42,  # Deterministic for reproducible tests
    )

    sim = SensorSimulator(config)
    sim.start()

    # Give threads time to start
    time.sleep(0.1)

    yield sim

    # Ensure cleanup
    sim.stop()
    # Give sockets time to release
    time.sleep(0.05)


def _create_simulator_with_faults(**fault_kwargs):
    """Helper to create a simulator with specific fault configuration."""
    from gsdv.diagnostics.sensor_simulator import (
        FaultConfig,
        SensorSimulator,
        SimulatorConfig,
    )

    ports = _find_available_ports(3)
    if len(ports) < 3:
        pytest.skip("Could not find 3 available ports for simulator")

    fault_config = FaultConfig(**fault_kwargs)
    config = SimulatorConfig(
        udp_port=ports[0],
        tcp_port=ports[1],
        http_port=ports[2],
        sample_rate_hz=500,  # Higher rate to observe fault effects
        seed=42,
        faults=fault_config,
    )

    sim = SensorSimulator(config)
    sim.start()
    time.sleep(0.1)
    return sim


@pytest.fixture
def sensor_simulator_with_loss():
    """Simulator with 50% packet loss for testing loss handling."""
    sim = _create_simulator_with_faults(loss_probability=0.5)
    yield sim
    sim.stop()
    time.sleep(0.05)


@pytest.fixture
def sensor_simulator_with_reorder():
    """Simulator with packet reordering for testing out-of-order handling."""
    sim = _create_simulator_with_faults(reorder_probability=0.3, reorder_delay_packets=3)
    yield sim
    sim.stop()
    time.sleep(0.05)


@pytest.fixture
def sensor_simulator_with_burst_loss():
    """Simulator with burst packet loss for testing gap handling."""
    sim = _create_simulator_with_faults(burst_loss_probability=0.2, burst_loss_length=5)
    yield sim
    sim.stop()
    time.sleep(0.05)


@pytest.fixture
def sensor_simulator_with_disconnect():
    """Simulator with random disconnects for testing reconnection."""
    sim = _create_simulator_with_faults(
        disconnect_probability=0.1, disconnect_duration_ms=50
    )
    yield sim
    sim.stop()
    time.sleep(0.05)
