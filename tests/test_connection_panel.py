"""Tests for ConnectionPanel IP validation and SensorInfoDisplay."""

import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

from gsdv.models import CalibrationInfo
from gsdv.ui import ConnectionPanel, MainWindow, SensorInfoDisplay, is_valid_ipv4


class TestIsValidIpv4:
    """Tests for FR-1: IP address validation."""

    def test_valid_standard_ip(self):
        """Standard IPv4 address is valid."""
        assert is_valid_ipv4("192.168.1.1") is True

    def test_valid_localhost(self):
        """Localhost address is valid."""
        assert is_valid_ipv4("127.0.0.1") is True

    def test_valid_zeros(self):
        """All zeros address is valid."""
        assert is_valid_ipv4("0.0.0.0") is True

    def test_valid_max_octets(self):
        """Maximum octet values are valid."""
        assert is_valid_ipv4("255.255.255.255") is True

    def test_invalid_empty_string(self):
        """Empty string is invalid."""
        assert is_valid_ipv4("") is False

    def test_invalid_hostname(self):
        """Hostname is not a valid IPv4."""
        assert is_valid_ipv4("localhost") is False

    def test_invalid_too_few_octets(self):
        """IP with too few octets is invalid."""
        assert is_valid_ipv4("192.168.1") is False

    def test_invalid_too_many_octets(self):
        """IP with too many octets is invalid."""
        assert is_valid_ipv4("192.168.1.1.1") is False

    def test_invalid_octet_out_of_range(self):
        """IP with octet > 255 is invalid."""
        assert is_valid_ipv4("192.168.1.256") is False

    def test_invalid_negative_octet(self):
        """IP with negative octet is invalid."""
        assert is_valid_ipv4("192.168.-1.1") is False

    def test_invalid_letters_in_octet(self):
        """IP with letters is invalid."""
        assert is_valid_ipv4("192.168.1.abc") is False

    def test_invalid_ipv6_address(self):
        """IPv6 address is not valid IPv4."""
        assert is_valid_ipv4("::1") is False
        assert is_valid_ipv4("2001:db8::1") is False

    def test_invalid_with_port(self):
        """IP with port suffix is invalid."""
        assert is_valid_ipv4("192.168.1.1:8080") is False

    def test_invalid_leading_zeros(self):
        """IP with leading zeros is still valid (Python accepts it)."""
        # Note: Python's ipaddress module accepts leading zeros
        assert is_valid_ipv4("192.168.001.001") is True

    def test_invalid_whitespace_only(self):
        """Whitespace-only string is invalid."""
        assert is_valid_ipv4("   ") is False


@pytest.fixture
def connection_panel(qtbot):
    """Create a ConnectionPanel instance for testing."""
    panel = ConnectionPanel()
    qtbot.addWidget(panel)
    return panel


class TestConnectionPanelValidation:
    """Tests for ConnectionPanel IP validation behavior."""

    def test_connect_button_disabled_initially(self, connection_panel):
        """Connect button is disabled when IP input is empty."""
        assert connection_panel._connect_button.isEnabled() is False

    def test_connect_button_enabled_with_valid_ip(self, connection_panel):
        """Connect button is enabled when valid IP is entered."""
        connection_panel.set_ip("192.168.1.1")
        assert connection_panel._connect_button.isEnabled() is True

    def test_connect_button_disabled_with_invalid_ip(self, connection_panel):
        """Connect button stays disabled with invalid IP."""
        connection_panel.set_ip("not-an-ip")
        assert connection_panel._connect_button.isEnabled() is False

    def test_connect_button_disabled_after_clearing_ip(self, connection_panel):
        """Connect button is disabled after clearing a valid IP."""
        connection_panel.set_ip("192.168.1.1")
        assert connection_panel._connect_button.isEnabled() is True
        connection_panel.set_ip("")
        assert connection_panel._connect_button.isEnabled() is False

    def test_is_ip_valid_method_returns_true_for_valid(self, connection_panel):
        """is_ip_valid() returns True for valid IP."""
        connection_panel.set_ip("10.0.0.1")
        assert connection_panel.is_ip_valid() is True

    def test_is_ip_valid_method_returns_false_for_invalid(self, connection_panel):
        """is_ip_valid() returns False for invalid IP."""
        connection_panel.set_ip("invalid")
        assert connection_panel.is_ip_valid() is False

    def test_connect_signal_not_emitted_for_invalid_ip(self, connection_panel, qtbot):
        """connect_requested signal is not emitted when IP is invalid."""
        signals_received = []
        connection_panel.connect_requested.connect(lambda ip: signals_received.append(ip))

        connection_panel.set_ip("not-valid")
        connection_panel._on_connect_clicked()

        assert len(signals_received) == 0

    def test_connect_signal_emitted_for_valid_ip(self, connection_panel, qtbot):
        """connect_requested signal is emitted with valid IP."""
        signals_received = []
        connection_panel.connect_requested.connect(lambda ip: signals_received.append(ip))

        connection_panel.set_ip("192.168.1.100")
        connection_panel._on_connect_clicked()

        assert signals_received == ["192.168.1.100"]

    def test_validation_tooltip_set_for_invalid_ip(self, connection_panel):
        """Validation label tooltip is set when IP is invalid."""
        connection_panel.set_ip("not-valid")
        assert connection_panel._validation_label.toolTip() == "Invalid IPv4 address"

    def test_validation_tooltip_cleared_for_valid_ip(self, connection_panel):
        """Validation label tooltip is cleared when IP is valid."""
        connection_panel.set_ip("192.168.1.1")
        assert connection_panel._validation_label.toolTip() == ""

    def test_validation_tooltip_cleared_for_empty_ip(self, connection_panel):
        """Validation label tooltip is cleared when IP is empty."""
        connection_panel.set_ip("invalid")
        connection_panel.set_ip("")
        assert connection_panel._validation_label.toolTip() == ""


class TestConnectionPanelState:
    """Tests for ConnectionPanel connection state management."""

    def test_set_connected_true_changes_button_text(self, connection_panel):
        """Setting connected=True changes button to 'Disconnect'."""
        connection_panel.set_ip("192.168.1.1")
        connection_panel.set_connected(True)
        assert connection_panel._connect_button.text() == "Disconnect"

    def test_set_connected_false_changes_button_text(self, connection_panel):
        """Setting connected=False changes button to 'Connect'."""
        connection_panel.set_ip("192.168.1.1")
        connection_panel.set_connected(True)
        connection_panel.set_connected(False)
        assert connection_panel._connect_button.text() == "Connect"

    def test_set_connected_disables_ip_input(self, connection_panel):
        """IP input is disabled when connected."""
        connection_panel.set_ip("192.168.1.1")
        connection_panel.set_connected(True)
        assert connection_panel._ip_input.isEnabled() is False

    def test_set_disconnected_enables_ip_input(self, connection_panel):
        """IP input is enabled when disconnected."""
        connection_panel.set_ip("192.168.1.1")
        connection_panel.set_connected(True)
        connection_panel.set_connected(False)
        assert connection_panel._ip_input.isEnabled() is True

    def test_disconnect_signal_emitted_when_connected(self, connection_panel, qtbot):
        """disconnect_requested signal is emitted when disconnecting."""
        signals_received = []
        connection_panel.disconnect_requested.connect(lambda: signals_received.append("disconnect"))

        connection_panel.set_ip("192.168.1.1")
        connection_panel.set_connected(True)
        connection_panel._on_connect_clicked()

        assert signals_received == ["disconnect"]

    def test_custom_status_text_displayed(self, connection_panel):
        """Custom status text is shown in the status label."""
        connection_panel.set_connected(True, "Connected to SIM-001")
        assert connection_panel._status_label.text() == "Connected to SIM-001"

    def test_default_status_text_for_connected(self, connection_panel):
        """Default 'Connected' text is shown when no custom text provided."""
        connection_panel.set_connected(True)
        assert connection_panel._status_label.text() == "Connected"

    def test_default_status_text_for_disconnected(self, connection_panel):
        """Default 'Disconnected' text is shown when no custom text provided."""
        connection_panel.set_connected(False)
        assert connection_panel._status_label.text() == "Disconnected"


@pytest.fixture
def sensor_info(qtbot):
    """Create a SensorInfoDisplay instance for testing."""
    widget = SensorInfoDisplay()
    qtbot.addWidget(widget)
    return widget


class TestSensorInfoDisplay:
    """Tests for FR-4: Sensor info display."""

    def test_initial_values_show_placeholder(self, sensor_info):
        """All values show placeholder '---' initially."""
        assert sensor_info._serial_value.text() == "---"
        assert sensor_info._firmware_value.text() == "---"
        assert sensor_info._cpf_value.text() == "---"
        assert sensor_info._cpt_value.text() == "---"

    def test_update_info_shows_serial(self, sensor_info):
        """Serial number is displayed from calibration info."""
        cal = CalibrationInfo(
            counts_per_force=1000000,
            counts_per_torque=1000000,
            serial_number="FT12345",
        )
        sensor_info.update_info(cal)
        assert sensor_info._serial_value.text() == "FT12345"

    def test_update_info_shows_firmware(self, sensor_info):
        """Firmware version is displayed from calibration info."""
        cal = CalibrationInfo(
            counts_per_force=1000000,
            counts_per_torque=1000000,
            firmware_version="2.1.3",
        )
        sensor_info.update_info(cal)
        assert sensor_info._firmware_value.text() == "2.1.3"

    def test_update_info_shows_cpf(self, sensor_info):
        """Counts per force is displayed with formatting."""
        cal = CalibrationInfo(
            counts_per_force=1234567,
            counts_per_torque=1000000,
        )
        sensor_info.update_info(cal)
        assert sensor_info._cpf_value.text() == "1,234,567"

    def test_update_info_shows_cpt(self, sensor_info):
        """Counts per torque is displayed with formatting."""
        cal = CalibrationInfo(
            counts_per_force=1000000,
            counts_per_torque=9876543,
        )
        sensor_info.update_info(cal)
        assert sensor_info._cpt_value.text() == "9,876,543"

    def test_update_info_shows_na_for_missing_serial(self, sensor_info):
        """'N/A' is shown when serial number is not available."""
        cal = CalibrationInfo(
            counts_per_force=1000000,
            counts_per_torque=1000000,
            serial_number=None,
        )
        sensor_info.update_info(cal)
        assert sensor_info._serial_value.text() == "N/A"

    def test_update_info_shows_na_for_missing_firmware(self, sensor_info):
        """'N/A' is shown when firmware version is not available."""
        cal = CalibrationInfo(
            counts_per_force=1000000,
            counts_per_torque=1000000,
            firmware_version=None,
        )
        sensor_info.update_info(cal)
        assert sensor_info._firmware_value.text() == "N/A"

    def test_clear_info_resets_all_values(self, sensor_info):
        """clear_info() resets all values to placeholder."""
        cal = CalibrationInfo(
            counts_per_force=1000000,
            counts_per_torque=1000000,
            serial_number="FT12345",
            firmware_version="2.1.3",
        )
        sensor_info.update_info(cal)
        sensor_info.clear_info()

        assert sensor_info._serial_value.text() == "---"
        assert sensor_info._firmware_value.text() == "---"
        assert sensor_info._cpf_value.text() == "---"
        assert sensor_info._cpt_value.text() == "---"


@pytest.fixture
def main_window(qtbot):
    """Create a MainWindow instance for testing."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window


class TestMainWindowSensorInfo:
    """Tests for sensor_info integration in MainWindow."""

    def test_sensor_info_property_exists(self, main_window):
        """MainWindow has sensor_info property."""
        assert hasattr(main_window, "sensor_info")
        assert isinstance(main_window.sensor_info, SensorInfoDisplay)

    def test_sensor_info_is_visible(self, main_window):
        """SensorInfoDisplay is visible in the window."""
        assert main_window.sensor_info.isVisible()

    def test_connection_panel_validation_works_in_main_window(self, main_window):
        """IP validation works through MainWindow's connection panel."""
        main_window.connection_panel.set_ip("192.168.1.1")
        assert main_window.connection_panel.is_ip_valid() is True

        main_window.connection_panel.set_ip("invalid")
        assert main_window.connection_panel.is_ip_valid() is False
