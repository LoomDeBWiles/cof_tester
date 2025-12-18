"""Tests for sensor discovery module."""

import ipaddress
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import pytest

from gsdv.protocols.discovery import (
    DiscoveredSensor,
    _extract_xml_field,
    _probe_host,
    discover_sensors,
    get_local_subnets,
    scan_subnet,
)


class TestExtractXmlField:
    """Tests for XML field extraction helper."""

    def test_extract_existing_field(self) -> None:
        xml = "<root><setserial>FT12345</setserial></root>"
        assert _extract_xml_field(xml, "setserial") == "FT12345"

    def test_extract_missing_field(self) -> None:
        xml = "<root><other>value</other></root>"
        assert _extract_xml_field(xml, "setserial") is None

    def test_extract_empty_field(self) -> None:
        xml = "<root><setserial></setserial></root>"
        assert _extract_xml_field(xml, "setserial") is None

    def test_extract_whitespace_field(self) -> None:
        xml = "<root><setserial>  </setserial></root>"
        assert _extract_xml_field(xml, "setserial") is None

    def test_extract_field_with_whitespace(self) -> None:
        xml = "<root><setserial>  FT12345  </setserial></root>"
        assert _extract_xml_field(xml, "setserial") == "FT12345"


class TestDiscoveredSensor:
    """Tests for DiscoveredSensor dataclass."""

    def test_create_with_all_fields(self) -> None:
        sensor = DiscoveredSensor(ip="192.168.1.100", serial_number="FT12345", firmware_version="1.0.0")
        assert sensor.ip == "192.168.1.100"
        assert sensor.serial_number == "FT12345"
        assert sensor.firmware_version == "1.0.0"

    def test_create_with_ip_only(self) -> None:
        sensor = DiscoveredSensor(ip="192.168.1.100")
        assert sensor.ip == "192.168.1.100"
        assert sensor.serial_number is None
        assert sensor.firmware_version is None

    def test_is_frozen(self) -> None:
        sensor = DiscoveredSensor(ip="192.168.1.100")
        with pytest.raises(AttributeError):
            sensor.ip = "192.168.1.101"  # type: ignore[misc]


class TestGetLocalSubnets:
    """Tests for local subnet detection."""

    def test_returns_list(self) -> None:
        subnets = get_local_subnets()
        assert isinstance(subnets, list)
        for subnet in subnets:
            assert isinstance(subnet, ipaddress.IPv4Network)

    def test_excludes_loopback(self) -> None:
        subnets = get_local_subnets()
        for subnet in subnets:
            assert not subnet.is_loopback

    def test_excludes_link_local(self) -> None:
        subnets = get_local_subnets()
        for subnet in subnets:
            assert not subnet.is_link_local


class MockHTTPHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler for testing probe functionality."""

    sensor_xml: Optional[str] = None

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress logging

    def do_GET(self) -> None:
        if self.path == "/netftapi2.xml" and self.sensor_xml:
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.end_headers()
            self.wfile.write(self.sensor_xml.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def mock_sensor_server():
    """Create a mock sensor HTTP server for testing."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<netftapi2>
    <cfgcpf>1000000</cfgcpf>
    <cfgcpt>1000000</cfgcpt>
    <setserial>FT-TEST-001</setserial>
    <setfwver>2.1.0</setfwver>
</netftapi2>"""

    class ConfiguredHandler(MockHTTPHandler):
        sensor_xml = xml

    # Find an available port
    server = HTTPServer(("127.0.0.1", 0), ConfiguredHandler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()


class TestProbeHost:
    """Tests for single host probing."""

    def test_probe_valid_sensor(self, mock_sensor_server: tuple[str, int]) -> None:
        ip, port = mock_sensor_server
        result = _probe_host(ip, port, timeout=1.0)

        assert result is not None
        assert result.ip == ip
        assert result.serial_number == "FT-TEST-001"
        assert result.firmware_version == "2.1.0"

    def test_probe_nonexistent_host(self) -> None:
        # 192.0.2.x is TEST-NET-1, reserved for documentation (RFC 5737)
        result = _probe_host("192.0.2.1", 80, timeout=0.1)
        assert result is None

    def test_probe_wrong_port(self, mock_sensor_server: tuple[str, int]) -> None:
        ip, port = mock_sensor_server
        # Use a different port that won't have a server
        result = _probe_host(ip, port + 1, timeout=0.1)
        assert result is None

    def test_probe_non_sensor_server(self) -> None:
        """Test probing a server that doesn't return sensor XML."""

        class NonSensorHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body>Not a sensor</body></html>")

        server = HTTPServer(("127.0.0.1", 0), NonSensorHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            result = _probe_host("127.0.0.1", port, timeout=1.0)
            assert result is None
        finally:
            server.shutdown()


class TestScanSubnet:
    """Tests for subnet scanning."""

    def test_scan_finds_sensor(self, mock_sensor_server: tuple[str, int]) -> None:
        ip, port = mock_sensor_server

        # Create a tiny /30 network containing the server IP
        network = ipaddress.IPv4Network(f"{ip}/30", strict=False)

        results = scan_subnet(network, port=port, timeout_per_host=1.0, max_workers=4)

        # Should find our mock server
        found_ips = [s.ip for s in results]
        assert ip in found_ips

    def test_scan_empty_subnet(self) -> None:
        # Use TEST-NET-1 which should have no responding hosts
        network = ipaddress.IPv4Network("192.0.2.0/30")
        results = scan_subnet(network, port=80, timeout_per_host=0.05, max_workers=4)
        assert results == []

    def test_scan_progress_callback(self, mock_sensor_server: tuple[str, int]) -> None:
        ip, port = mock_sensor_server
        network = ipaddress.IPv4Network(f"{ip}/30", strict=False)

        progress_calls: list[tuple[int, int]] = []

        def callback(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        scan_subnet(network, port=port, timeout_per_host=1.0, max_workers=4, progress_callback=callback)

        # Should have been called for each host
        assert len(progress_calls) > 0
        # Final call should have completed == total
        final_completed, final_total = progress_calls[-1]
        assert final_completed == final_total


class TestDiscoverSensors:
    """Tests for full discovery function."""

    def test_discover_with_explicit_subnet(self, mock_sensor_server: tuple[str, int]) -> None:
        ip, port = mock_sensor_server
        network = ipaddress.IPv4Network(f"{ip}/30", strict=False)

        results = discover_sensors(port=port, timeout_per_host=1.0, max_workers=4, subnets=[network])

        found_ips = [s.ip for s in results]
        assert ip in found_ips

    def test_discover_empty_subnet_list(self) -> None:
        results = discover_sensors(subnets=[])
        assert results == []

    def test_discover_progress_callback(self, mock_sensor_server: tuple[str, int]) -> None:
        ip, port = mock_sensor_server
        network = ipaddress.IPv4Network(f"{ip}/30", strict=False)

        progress_calls: list[tuple[int, int]] = []

        def callback(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        discover_sensors(
            port=port, timeout_per_host=1.0, max_workers=4, subnets=[network], progress_callback=callback
        )

        assert len(progress_calls) > 0


class TestScanTiming:
    """Tests for scan timing constraints."""

    def test_scan_completes_within_timeout(self) -> None:
        """Verify that scanning a /28 (14 hosts) completes quickly with fast timeout."""
        import time

        network = ipaddress.IPv4Network("192.0.2.0/28")  # 14 hosts in TEST-NET

        start = time.monotonic()
        # Use very short timeout since we expect no responses
        scan_subnet(network, timeout_per_host=0.02, max_workers=14)
        elapsed = time.monotonic() - start

        # Should complete in under 1 second with 14 hosts at 0.02s timeout
        # (parallel execution means ~0.02s total, but allow some overhead)
        assert elapsed < 1.0
