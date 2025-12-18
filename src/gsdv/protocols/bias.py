"""Bias (tare/zero) service for force/torque sensors.

Implements both device-level hardware tare and software-level soft zero:
- Device tare: Sends UDP SET_BIAS command (primary) or TCP bias request (fallback)
- Soft zero: Captures current sample as offset and subtracts from future samples

The soft zero fallback is used when:
- User explicitly selects "soft" bias mode in settings
- Device tare fails and automatic fallback is enabled
"""

import socket
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from gsdv.errors import BiasError
from gsdv.protocols.rdt_udp import RdtClient
from gsdv.protocols.tcp_cmd import TcpCommandClient


@dataclass
class SoftZeroOffset:
    """Software zero offset for app-level tare.

    Stores the counts captured at the moment of soft zero application.
    Apply to samples by subtracting from raw counts before calibration.
    """

    counts: tuple[int, int, int, int, int, int]

    def apply(
        self, sample_counts: tuple[int, int, int, int, int, int]
    ) -> tuple[int, int, int, int, int, int]:
        """Apply the soft zero offset to a sample.

        Args:
            sample_counts: Raw counts [Fx, Fy, Fz, Tx, Ty, Tz].

        Returns:
            Adjusted counts with offset subtracted.
        """
        return (
            sample_counts[0] - self.counts[0],
            sample_counts[1] - self.counts[1],
            sample_counts[2] - self.counts[2],
            sample_counts[3] - self.counts[3],
            sample_counts[4] - self.counts[4],
            sample_counts[5] - self.counts[5],
        )

    def apply_array(self, sample_counts: NDArray[np.int32]) -> NDArray[np.int32]:
        """Apply the soft zero offset to a sample array.

        Args:
            sample_counts: Raw counts array of shape (6,).

        Returns:
            Adjusted counts with offset subtracted.
        """
        offset_arr = np.array(self.counts, dtype=np.int32)
        return sample_counts - offset_arr


def send_device_bias(
    ip: str,
    udp_port: int = 49152,
    tcp_port: int = 49151,
    timeout: float = 2.0,
) -> None:
    """Send device-level bias (tare) command to the sensor.

    Tries UDP SET_BIAS command first (primary method). If that fails,
    falls back to TCP READFT with bias bit set.

    Args:
        ip: Sensor IP address.
        udp_port: UDP RDT port (default 49152).
        tcp_port: TCP command port (default 49151).
        timeout: Timeout for TCP connection in seconds.

    Raises:
        BiasError: If both UDP and TCP bias attempts fail.
    """
    # Try UDP bias first (primary method)
    udp_error: Optional[str] = None
    try:
        with RdtClient(ip, port=udp_port) as rdt_client:
            rdt_client.send_bias()
        return  # Success
    except (OSError, socket.error) as e:
        udp_error = str(e)

    # Fallback to TCP bias
    tcp_error: Optional[str] = None
    try:
        with TcpCommandClient(ip, port=tcp_port, timeout=timeout) as tcp_client:
            tcp_client.send_bias()
        return  # Success
    except (OSError, socket.error, ConnectionError) as e:
        tcp_error = str(e)

    # Both failed
    details = []
    if udp_error:
        details.append(f"UDP: {udp_error}")
    if tcp_error:
        details.append(f"TCP: {tcp_error}")
    raise BiasError(ip, "device tare", "; ".join(details))


def capture_soft_zero(
    current_counts: tuple[int, int, int, int, int, int],
) -> SoftZeroOffset:
    """Capture current counts as the soft zero offset.

    Args:
        current_counts: Current raw counts [Fx, Fy, Fz, Tx, Ty, Tz].

    Returns:
        SoftZeroOffset to apply to future samples.
    """
    return SoftZeroOffset(counts=current_counts)


class BiasService:
    """Manages bias/tare operations for a sensor.

    Supports both device-level hardware tare and app-level soft zero.
    Tracks current soft zero offset and provides methods to apply bias
    based on configured mode.

    Example:
        >>> service = BiasService("192.168.1.1")
        >>> # Device tare
        >>> service.apply_device_bias()
        >>> # Or soft zero with current sample
        >>> service.apply_soft_zero((100, 200, 300, 50, 60, 70))
        >>> # Apply offset to incoming sample
        >>> adjusted = service.adjust_sample((150, 250, 350, 100, 110, 120))
    """

    def __init__(
        self,
        ip: str,
        udp_port: int = 49152,
        tcp_port: int = 49151,
        timeout: float = 2.0,
    ) -> None:
        """Initialize bias service.

        Args:
            ip: Sensor IP address.
            udp_port: UDP RDT port for device bias.
            tcp_port: TCP command port for fallback bias.
            timeout: Timeout for TCP operations in seconds.
        """
        self._ip = ip
        self._udp_port = udp_port
        self._tcp_port = tcp_port
        self._timeout = timeout
        self._soft_zero: Optional[SoftZeroOffset] = None

    @property
    def ip(self) -> str:
        """Sensor IP address."""
        return self._ip

    @property
    def has_soft_zero(self) -> bool:
        """Whether a soft zero offset is currently active."""
        return self._soft_zero is not None

    @property
    def soft_zero_offset(self) -> Optional[SoftZeroOffset]:
        """Current soft zero offset, if any."""
        return self._soft_zero

    def apply_device_bias(self) -> None:
        """Apply device-level hardware tare.

        Sends bias command to sensor via UDP (primary) or TCP (fallback).
        Clears any existing soft zero offset on success.

        Raises:
            BiasError: If device bias cannot be applied.
        """
        send_device_bias(
            self._ip,
            udp_port=self._udp_port,
            tcp_port=self._tcp_port,
            timeout=self._timeout,
        )
        # Clear soft zero since device bias is now active
        self._soft_zero = None

    def apply_soft_zero(
        self, current_counts: tuple[int, int, int, int, int, int]
    ) -> None:
        """Apply software-level zero using current counts.

        Stores the current counts as the offset to subtract from future samples.

        Args:
            current_counts: Current raw counts [Fx, Fy, Fz, Tx, Ty, Tz].
        """
        self._soft_zero = capture_soft_zero(current_counts)

    def clear_soft_zero(self) -> None:
        """Clear any active soft zero offset."""
        self._soft_zero = None

    def apply_bias(
        self,
        mode: str,
        current_counts: Optional[tuple[int, int, int, int, int, int]] = None,
        fallback_on_failure: bool = True,
    ) -> None:
        """Apply bias based on the specified mode.

        Args:
            mode: Bias mode - "device" for hardware tare, "soft" for software zero.
            current_counts: Current counts (required for soft mode, optional for device
                mode with fallback_on_failure=True).
            fallback_on_failure: If True and mode is "device", fall back to soft zero
                if device bias fails. Requires current_counts.

        Raises:
            BiasError: If device bias fails and fallback_on_failure is False.
            ValueError: If mode is "soft" and current_counts is None.
        """
        if mode == "device":
            try:
                self.apply_device_bias()
            except BiasError:
                if fallback_on_failure and current_counts is not None:
                    self.apply_soft_zero(current_counts)
                else:
                    raise
        elif mode == "soft":
            if current_counts is None:
                raise ValueError("current_counts required for soft bias mode")
            self.apply_soft_zero(current_counts)
        else:
            raise ValueError(f"Unknown bias mode: {mode}")

    def adjust_sample(
        self, counts: tuple[int, int, int, int, int, int]
    ) -> tuple[int, int, int, int, int, int]:
        """Adjust sample counts by applying any active soft zero offset.

        If no soft zero is active, returns the original counts unchanged.

        Args:
            counts: Raw sample counts [Fx, Fy, Fz, Tx, Ty, Tz].

        Returns:
            Adjusted counts (or original if no soft zero active).
        """
        if self._soft_zero is not None:
            return self._soft_zero.apply(counts)
        return counts

    def adjust_sample_array(
        self, counts: NDArray[np.int32]
    ) -> NDArray[np.int32]:
        """Adjust sample counts array by applying any active soft zero offset.

        If no soft zero is active, returns the original counts unchanged.

        Args:
            counts: Raw sample counts array of shape (6,).

        Returns:
            Adjusted counts array (or original if no soft zero active).
        """
        if self._soft_zero is not None:
            return self._soft_zero.apply_array(counts)
        return counts
