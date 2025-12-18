"""HTTP calibration interface for retrieving sensor calibration data.

This module implements the HTTP-based calibration retrieval for ATI NETrs
sensors. HTTP is the preferred method for calibration data as it provides
more complete information than the TCP interface.

Protocol details (per ATI documentation):
- Port: 80
- Endpoint: GET /netftapi2.xml
- Response: XML with calibration fields
"""

import socket
from typing import Optional
from xml.etree import ElementTree

from gsdv.models import CalibrationInfo


# Protocol constants
HTTP_PORT = 80
CALIBRATION_ENDPOINT = "/netftapi2.xml"
HTTP_TIMEOUT = 5.0


class HttpCalibrationError(Exception):
    """Error during HTTP calibration retrieval."""

    pass


def _http_get(ip: str, port: int, path: str, timeout: float) -> str:
    """Perform a simple HTTP GET request.

    Args:
        ip: Server IP address.
        port: HTTP port.
        path: URL path.
        timeout: Socket timeout in seconds.

    Returns:
        Response body as string.

    Raises:
        HttpCalibrationError: If request fails or response is invalid.
    """
    request = f"GET {path} HTTP/1.1\r\nHost: {ip}\r\nConnection: close\r\n\r\n"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((ip, port))
            sock.sendall(request.encode("ascii"))

            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
        except socket.timeout as e:
            raise HttpCalibrationError(f"Connection timed out: {e}") from e
        except OSError as e:
            raise HttpCalibrationError(f"Connection failed: {e}") from e

    response_str = response.decode("utf-8", errors="replace")

    # Split headers and body
    if "\r\n\r\n" in response_str:
        headers, body = response_str.split("\r\n\r\n", 1)
    elif "\n\n" in response_str:
        headers, body = response_str.split("\n\n", 1)
    else:
        raise HttpCalibrationError("Invalid HTTP response: no header/body separator")

    # Check status
    status_line = headers.split("\r\n")[0] if "\r\n" in headers else headers.split("\n")[0]
    if "200" not in status_line:
        raise HttpCalibrationError(f"HTTP request failed: {status_line}")

    return body


def _find_xml_element(
    root: ElementTree.Element, paths: list[str]
) -> Optional[ElementTree.Element]:
    """Find first matching XML element by XPath from a list of paths.

    This function exists because Element.__bool__() is deprecated in Python 3.14+
    and returns False for elements with no children. Using `or` chaining like
    `root.find(a) or root.find(b)` fails when the first find returns a valid
    childless element.

    Args:
        root: The root element to search from.
        paths: List of XPath expressions to try in order.

    Returns:
        The first matching Element, or None if no paths match.
    """
    for path in paths:
        elem = root.find(path)
        if elem is not None:
            return elem
    return None


def parse_calibration_xml(xml_content: str) -> CalibrationInfo:
    """Parse calibration XML response.

    Args:
        xml_content: XML string from sensor.

    Returns:
        CalibrationInfo with parsed values.

    Raises:
        HttpCalibrationError: If XML is invalid or missing required fields.
    """
    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError as e:
        raise HttpCalibrationError(f"Invalid XML: {e}") from e

    # Find calibration fields - try common element names
    cpf_element = _find_xml_element(root, [".//cfgcpf", ".//countsPerForce", ".//cpf"])
    cpt_element = _find_xml_element(root, [".//cfgcpt", ".//countsPerTorque", ".//cpt"])

    if cpf_element is None or cpf_element.text is None:
        raise HttpCalibrationError("Missing counts_per_force in calibration XML")
    if cpt_element is None or cpt_element.text is None:
        raise HttpCalibrationError("Missing counts_per_torque in calibration XML")

    try:
        counts_per_force = float(cpf_element.text)
        counts_per_torque = float(cpt_element.text)
    except ValueError as e:
        raise HttpCalibrationError(f"Invalid calibration values: {e}") from e

    # Optional fields
    serial_element = _find_xml_element(root, [".//setserial", ".//serial"])
    firmware_element = _find_xml_element(root, [".//setfwver", ".//firmware"])
    force_units_element = _find_xml_element(root, [".//cfgfu", ".//forceUnits"])
    torque_units_element = _find_xml_element(root, [".//cfgtu", ".//torqueUnits"])

    serial_number = serial_element.text if serial_element is not None and serial_element.text else None
    firmware_version = firmware_element.text if firmware_element is not None and firmware_element.text else None

    force_units_code: Optional[int] = None
    if force_units_element is not None and force_units_element.text:
        try:
            force_units_code = int(force_units_element.text)
        except ValueError:
            pass

    torque_units_code: Optional[int] = None
    if torque_units_element is not None and torque_units_element.text:
        try:
            torque_units_code = int(torque_units_element.text)
        except ValueError:
            pass

    return CalibrationInfo(
        counts_per_force=counts_per_force,
        counts_per_torque=counts_per_torque,
        serial_number=serial_number,
        firmware_version=firmware_version,
        force_units_code=force_units_code,
        torque_units_code=torque_units_code,
    )


class HttpCalibrationClient:
    """HTTP calibration client for ATI NETrs sensors.

    This client retrieves calibration data via HTTP, which is the
    preferred method as it provides more complete information.

    Example:
        >>> client = HttpCalibrationClient("192.168.1.1")
        >>> cal = client.get_calibration()
        >>> print(f"CPF: {cal.counts_per_force}, CPT: {cal.counts_per_torque}")
    """

    def __init__(
        self,
        ip: str,
        port: int = HTTP_PORT,
        timeout: float = HTTP_TIMEOUT,
    ) -> None:
        """Initialize HTTP calibration client.

        Args:
            ip: Sensor IP address.
            port: HTTP port (default 80).
            timeout: Request timeout in seconds.
        """
        self._ip = ip
        self._port = port
        self._timeout = timeout

    @property
    def ip(self) -> str:
        """Sensor IP address."""
        return self._ip

    @property
    def port(self) -> int:
        """HTTP port."""
        return self._port

    def get_calibration(self) -> CalibrationInfo:
        """Retrieve calibration data from the sensor.

        Returns:
            CalibrationInfo with sensor calibration values.

        Raises:
            HttpCalibrationError: If request fails or response is invalid.
        """
        xml_content = _http_get(self._ip, self._port, CALIBRATION_ENDPOINT, self._timeout)
        return parse_calibration_xml(xml_content)

    def get_raw_xml(self) -> str:
        """Retrieve raw XML calibration data.

        Returns:
            Raw XML string from sensor.

        Raises:
            HttpCalibrationError: If request fails.
        """
        return _http_get(self._ip, self._port, CALIBRATION_ENDPOINT, self._timeout)


def get_calibration_with_fallback(
    ip: str,
    http_port: int = HTTP_PORT,
    tcp_port: int = 49151,
    timeout: float = HTTP_TIMEOUT,
) -> CalibrationInfo:
    """Get calibration data, preferring HTTP with TCP fallback.

    Args:
        ip: Sensor IP address.
        http_port: HTTP port (default 80).
        tcp_port: TCP port for fallback (default 49151).
        timeout: Request timeout in seconds.

    Returns:
        CalibrationInfo from HTTP or TCP.

    Raises:
        Exception: If both HTTP and TCP fail.
    """
    # Try HTTP first
    try:
        client = HttpCalibrationClient(ip, http_port, timeout)
        return client.get_calibration()
    except HttpCalibrationError:
        pass

    # Fall back to TCP
    from gsdv.protocols.tcp_cmd import TcpCommandClient

    with TcpCommandClient(ip, tcp_port, timeout) as tcp_client:
        return tcp_client.read_calibration()
