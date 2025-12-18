"""TCP command interface for calibration, bias, and tool transform.

This module implements the TCP command protocol for ATI NETrs sensors.
It supports reading calibration data, setting tool transforms, and
bias/tare operations via the TCP fallback mechanism.

Protocol details (per ATI documentation):
- Port: 49151
- READCALINFO: 20-byte request (no header), 24-byte response
- WRITETRANSFORM: 20-byte request
- READFT with bias: 20-byte request with sysCommands bit
"""

import socket
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from gsdv.models import CalibrationInfo


class TcpCommand(IntEnum):
    """TCP command codes."""

    READFT = 0x00
    READCALINFO = 0x01
    WRITETRANSFORM = 0x02


class TransformDistUnits(IntEnum):
    """Distance units for tool transform."""

    MM = 3


class TransformAngleUnits(IntEnum):
    """Angle units for tool transform."""

    DEGREES = 1


# Protocol constants
TCP_PORT = 49151
TCP_RESPONSE_HEADER = 0x1234
CALINFO_REQUEST_SIZE = 20
CALINFO_RESPONSE_SIZE = 24
TRANSFORM_REQUEST_SIZE = 20
READFT_REQUEST_SIZE = 20

# Struct formats (big-endian)
CALINFO_RESPONSE_FORMAT = ">HBBII6H"  # header, forceUnits, torqueUnits, cpf, cpt, 6x scaleFactors


@dataclass
class ToolTransform:
    """Tool transform parameters.

    Distances in mm, angles in degrees.
    """

    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    rz: float = 0.0


def build_calinfo_request() -> bytes:
    """Build a READCALINFO request packet.

    Returns:
        20-byte request packet.
    """
    request = bytearray(CALINFO_REQUEST_SIZE)
    request[0] = TcpCommand.READCALINFO
    return bytes(request)


def parse_calinfo_response(data: bytes) -> CalibrationInfo:
    """Parse a READCALINFO response packet.

    Args:
        data: 24-byte response from sensor.

    Returns:
        CalibrationInfo with parsed values.

    Raises:
        ValueError: If response is invalid.
    """
    if len(data) != CALINFO_RESPONSE_SIZE:
        raise ValueError(f"Invalid calibration response size: expected {CALINFO_RESPONSE_SIZE}, got {len(data)}")

    unpacked = struct.unpack(CALINFO_RESPONSE_FORMAT, data)
    header = unpacked[0]
    if header != TCP_RESPONSE_HEADER:
        raise ValueError(f"Invalid response header: expected 0x{TCP_RESPONSE_HEADER:04X}, got 0x{header:04X}")

    force_units_code = unpacked[1]
    torque_units_code = unpacked[2]
    counts_per_force = float(unpacked[3])
    counts_per_torque = float(unpacked[4])

    return CalibrationInfo(
        counts_per_force=counts_per_force,
        counts_per_torque=counts_per_torque,
        force_units_code=force_units_code,
        torque_units_code=torque_units_code,
    )


def build_transform_request(transform: ToolTransform) -> bytes:
    """Build a WRITETRANSFORM request packet.

    Args:
        transform: Tool transform parameters.

    Returns:
        20-byte request packet.
    """
    request = bytearray(TRANSFORM_REQUEST_SIZE)
    request[0] = TcpCommand.WRITETRANSFORM
    request[1] = TransformDistUnits.MM
    request[2] = TransformAngleUnits.DEGREES

    # Pack transform values as int16 * 100 (big-endian)
    values = [
        int(transform.dx * 100),
        int(transform.dy * 100),
        int(transform.dz * 100),
        int(transform.rx * 100),
        int(transform.ry * 100),
        int(transform.rz * 100),
    ]
    struct.pack_into(">6h", request, 3, *values)

    return bytes(request)


def build_bias_request() -> bytes:
    """Build a READFT request with bias flag set.

    This is the TCP fallback for bias/tare when UDP bias command fails.

    Returns:
        20-byte request packet.
    """
    request = bytearray(READFT_REQUEST_SIZE)
    request[0] = TcpCommand.READFT
    # MCEnable at offset 0x10 (16): 0x0000
    # sysCommands at offset 0x12 (18): 0x0001 (bit 0 = bias)
    struct.pack_into(">H", request, 16, 0x0000)  # MCEnable
    struct.pack_into(">H", request, 18, 0x0001)  # sysCommands with bias bit
    return bytes(request)


class TcpCommandClient:
    """TCP command client for ATI NETrs sensors.

    This client handles TCP-based commands for calibration retrieval,
    tool transform configuration, and bias operations.

    Example:
        >>> client = TcpCommandClient("192.168.1.1")
        >>> cal = client.read_calibration()
        >>> print(f"CPF: {cal.counts_per_force}, CPT: {cal.counts_per_torque}")
        >>> client.close()
    """

    def __init__(
        self,
        ip: str,
        port: int = TCP_PORT,
        timeout: float = 2.0,
    ) -> None:
        """Initialize TCP command client.

        Args:
            ip: Sensor IP address.
            port: TCP port (default 49151).
            timeout: Socket timeout in seconds.
        """
        self._ip = ip
        self._port = port
        self._timeout = timeout
        self._socket: Optional[socket.socket] = None

    @property
    def ip(self) -> str:
        """Sensor IP address."""
        return self._ip

    @property
    def port(self) -> int:
        """TCP port."""
        return self._port

    def _ensure_connected(self) -> socket.socket:
        """Ensure socket is connected."""
        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self._timeout)
            self._socket.connect((self._ip, self._port))
        return self._socket

    def _send_receive(self, request: bytes, response_size: int) -> bytes:
        """Send request and receive response.

        Args:
            request: Request bytes to send.
            response_size: Expected response size.

        Returns:
            Response bytes.

        Raises:
            socket.timeout: If operation times out.
            ConnectionError: If connection is lost.
        """
        sock = self._ensure_connected()
        sock.sendall(request)

        response = b""
        while len(response) < response_size:
            chunk = sock.recv(response_size - len(response))
            if not chunk:
                raise ConnectionError("Connection closed by sensor")
            response += chunk

        return response

    def read_calibration(self) -> CalibrationInfo:
        """Read calibration data from the sensor.

        Returns:
            CalibrationInfo with sensor calibration values.

        Raises:
            socket.timeout: If operation times out.
            ValueError: If response is invalid.
        """
        request = build_calinfo_request()
        response = self._send_receive(request, CALINFO_RESPONSE_SIZE)
        return parse_calinfo_response(response)

    def write_transform(self, transform: ToolTransform) -> None:
        """Write tool transform to the sensor.

        Args:
            transform: Tool transform parameters.

        Note:
            This command does not return a response from the sensor.
        """
        request = build_transform_request(transform)
        sock = self._ensure_connected()
        sock.sendall(request)

    def send_bias(self) -> None:
        """Send bias/tare command via TCP fallback.

        This uses the READFT command with the bias bit set as a
        fallback when UDP bias is not available.
        """
        request = build_bias_request()
        sock = self._ensure_connected()
        sock.sendall(request)

    def close(self) -> None:
        """Close the TCP connection."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> "TcpCommandClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()
