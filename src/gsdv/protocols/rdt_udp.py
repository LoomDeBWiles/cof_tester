"""UDP RDT (Raw Data Transfer) streaming protocol implementation.

This module implements the UDP-based Real-time Data Transfer protocol for
communicating with ATI NETrs force/torque sensors. The protocol uses
big-endian byte ordering for all multi-byte values.

Protocol details (per ATI documentation):
- Port: 49152
- Request packet: 8 bytes (header, command, sample_count)
- Response packet: 36 bytes (sequence numbers, status, 6x int32 counts)
"""

import socket
import struct
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterator, Optional

from gsdv.models import SampleRecord


class RdtCommand(IntEnum):
    """UDP RDT command codes."""

    STOP = 0x0000
    START_REALTIME = 0x0002
    START_BUFFERED = 0x0003
    SET_BIAS = 0x0042


# Protocol constants
RDT_PORT = 49152
RDT_HEADER = 0x1234
RDT_REQUEST_SIZE = 8
RDT_RESPONSE_SIZE = 36

# Struct formats (big-endian)
REQUEST_FORMAT = ">HHI"  # header (uint16), command (uint16), sample_count (uint32)
RESPONSE_FORMAT = ">IIIiiiiii"  # rdt_seq, ft_seq, status, Fx, Fy, Fz, Tx, Ty, Tz


@dataclass
class RdtStatistics:
    """Statistics for RDT streaming session."""

    packets_received: int = 0
    packets_lost: int = 0
    last_rdt_sequence: int = -1


def build_rdt_request(command: RdtCommand, sample_count: int = 0) -> bytes:
    """Build an RDT request packet.

    Args:
        command: The RDT command to send.
        sample_count: Number of samples to request (0 = infinite streaming).

    Returns:
        8-byte request packet.
    """
    return struct.pack(REQUEST_FORMAT, RDT_HEADER, command, sample_count)


def parse_rdt_response(data: bytes) -> tuple[int, int, int, tuple[int, int, int, int, int, int]]:
    """Parse an RDT response packet.

    Args:
        data: 36-byte response packet from sensor.

    Returns:
        Tuple of (rdt_sequence, ft_sequence, status, counts_tuple).

    Raises:
        ValueError: If packet size is incorrect.
    """
    if len(data) != RDT_RESPONSE_SIZE:
        raise ValueError(f"Invalid RDT response size: expected {RDT_RESPONSE_SIZE}, got {len(data)}")

    unpacked = struct.unpack(RESPONSE_FORMAT, data)
    rdt_sequence = unpacked[0]
    ft_sequence = unpacked[1]
    status = unpacked[2]
    counts: tuple[int, int, int, int, int, int] = (
        unpacked[3], unpacked[4], unpacked[5],
        unpacked[6], unpacked[7], unpacked[8],
    )

    return rdt_sequence, ft_sequence, status, counts


class RdtClient:
    """UDP RDT streaming client for ATI NETrs sensors.

    This client manages the UDP connection to a sensor and provides
    methods for starting/stopping streaming and receiving samples.

    Example:
        >>> client = RdtClient("192.168.1.1")
        >>> client.start_streaming()
        >>> for sample in client.receive_samples(timeout=1.0):
        ...     print(sample.counts)
        >>> client.stop_streaming()
        >>> client.close()
    """

    def __init__(
        self,
        ip: str,
        port: int = RDT_PORT,
        receive_buffer_size: int = 2_097_152,  # 2MB buffer for 1000Hz streaming
    ) -> None:
        """Initialize RDT client.

        Args:
            ip: Sensor IP address.
            port: UDP port (default 49152).
            receive_buffer_size: Socket receive buffer size in bytes (default 2MB).
                At 1000Hz with 36-byte packets, 2MB holds ~58k packets (~58 seconds).
        """
        self._ip = ip
        self._port = port
        self._socket: Optional[socket.socket] = None
        self._receive_buffer_size = receive_buffer_size
        self._streaming = False
        self._stats = RdtStatistics()

    @property
    def ip(self) -> str:
        """Sensor IP address."""
        return self._ip

    @property
    def port(self) -> int:
        """UDP port."""
        return self._port

    @property
    def is_streaming(self) -> bool:
        """Whether streaming is active."""
        return self._streaming

    @property
    def statistics(self) -> RdtStatistics:
        """Current streaming statistics."""
        return self._stats

    def _ensure_socket(self) -> socket.socket:
        """Ensure socket is created and bound."""
        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._receive_buffer_size)
            self._socket.bind(("", 0))  # Bind to any available port
        return self._socket

    def _send_command(self, command: RdtCommand, sample_count: int = 0) -> None:
        """Send an RDT command to the sensor."""
        sock = self._ensure_socket()
        request = build_rdt_request(command, sample_count)
        sock.sendto(request, (self._ip, self._port))

    def start_streaming(self, sample_count: int = 0) -> None:
        """Start real-time data streaming.

        Args:
            sample_count: Number of samples to request (0 = infinite).
        """
        self._stats = RdtStatistics()
        self._send_command(RdtCommand.START_REALTIME, sample_count)
        self._streaming = True

    def stop_streaming(self) -> None:
        """Stop data streaming."""
        self._send_command(RdtCommand.STOP)
        self._streaming = False

    def send_bias(self) -> None:
        """Send bias/tare command to zero the sensor."""
        self._send_command(RdtCommand.SET_BIAS)

    def receive_samples(
        self,
        timeout: Optional[float] = None,
        max_samples: Optional[int] = None,
    ) -> Iterator[SampleRecord]:
        """Receive samples from the sensor.

        Args:
            timeout: Socket timeout in seconds (None = blocking).
            max_samples: Maximum number of samples to receive (None = unlimited).

        Yields:
            SampleRecord for each received packet.

        Raises:
            socket.timeout: If timeout expires without receiving data.
        """
        sock = self._ensure_socket()
        sock.settimeout(timeout)

        samples_received = 0
        while max_samples is None or samples_received < max_samples:
            try:
                data, _ = sock.recvfrom(RDT_RESPONSE_SIZE)
            except socket.timeout:
                break

            t_monotonic_ns = time.monotonic_ns()
            rdt_sequence, ft_sequence, status, counts = parse_rdt_response(data)

            # Track packet loss
            self._stats.packets_received += 1
            if self._stats.last_rdt_sequence >= 0:
                expected = (self._stats.last_rdt_sequence + 1) & 0xFFFFFFFF
                if rdt_sequence != expected:
                    # Handle wrap-around and calculate gap
                    if rdt_sequence > expected:
                        lost = rdt_sequence - expected
                    else:
                        # Sequence wrapped
                        lost = (0xFFFFFFFF - expected) + rdt_sequence + 1
                    self._stats.packets_lost += lost
            self._stats.last_rdt_sequence = rdt_sequence

            yield SampleRecord(
                t_monotonic_ns=t_monotonic_ns,
                rdt_sequence=rdt_sequence,
                ft_sequence=ft_sequence,
                status=status,
                counts=counts,
            )
            samples_received += 1

    def close(self) -> None:
        """Close the UDP socket."""
        if self._streaming:
            self.stop_streaming()
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> "RdtClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()
