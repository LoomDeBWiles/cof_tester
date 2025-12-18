"""Error types and recovery strategies for GSDV.

Error taxonomy:
- NET: Network errors (timeouts, connection refused, socket errors)
- PROTO: Protocol parsing errors (malformed packets, missing fields)
- CAL: Calibration retrieval failures (HTTP/TCP unavailable)
- IO: File I/O errors (disk full, permission denied, rotation failures)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorCategory(Enum):
    """Error category for classification and routing."""

    NET = "NET"
    PROTO = "PROTO"
    CAL = "CAL"
    IO = "IO"


class RecoveryAction(Enum):
    """Suggested recovery action for the user."""

    RETRY = "retry"
    RECONNECT = "reconnect"
    FALLBACK = "fallback"
    CHOOSE_DIRECTORY = "choose_directory"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ErrorContext:
    """Additional context for an error.

    Attributes:
        host: Remote host involved (IP or hostname).
        port: Port number involved.
        path: File path involved.
        protocol: Protocol name (UDP, TCP, HTTP).
        original_error: The underlying exception message.
    """

    host: Optional[str] = None
    port: Optional[int] = None
    path: Optional[str] = None
    protocol: Optional[str] = None
    original_error: Optional[str] = None


class GsdvError(Exception):
    """Base exception for all GSDV errors.

    Attributes:
        category: Error category for classification.
        code: Short error code (e.g., "NET-001").
        message: User-friendly error message.
        recovery: Suggested recovery action.
        context: Additional error context.
    """

    def __init__(
        self,
        category: ErrorCategory,
        code: str,
        message: str,
        recovery: RecoveryAction,
        context: Optional[ErrorContext] = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.message = message
        self.recovery = recovery
        self.context = context or ErrorContext()

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def user_message(self) -> str:
        """Return a user-friendly message suitable for display in the UI."""
        return self.message


class NetworkError(GsdvError):
    """Network-related errors (connection, timeout, socket issues)."""

    def __init__(
        self,
        code: str,
        message: str,
        recovery: RecoveryAction = RecoveryAction.RECONNECT,
        context: Optional[ErrorContext] = None,
    ) -> None:
        super().__init__(ErrorCategory.NET, code, message, recovery, context)


class ConnectionRefusedError(NetworkError):
    """Connection was refused by the remote host."""

    def __init__(self, host: str, port: int, original_error: Optional[str] = None) -> None:
        context = ErrorContext(host=host, port=port, original_error=original_error)
        super().__init__(
            code="NET-001",
            message=f"Connection refused by {host}:{port}. Check that the sensor is powered on and the IP address is correct.",
            recovery=RecoveryAction.RECONNECT,
            context=context,
        )


class ConnectionTimeoutError(NetworkError):
    """Connection attempt timed out."""

    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        context = ErrorContext(host=host, port=port)
        super().__init__(
            code="NET-002",
            message=f"Connection to {host}:{port} timed out after {timeout_seconds:.1f}s. Check network connectivity and sensor status.",
            recovery=RecoveryAction.RETRY,
            context=context,
        )


class NetworkDisconnectError(NetworkError):
    """Connection was lost unexpectedly."""

    def __init__(self, host: str, port: int, original_error: Optional[str] = None) -> None:
        context = ErrorContext(host=host, port=port, original_error=original_error)
        super().__init__(
            code="NET-003",
            message=f"Lost connection to {host}:{port}. The sensor may have been disconnected or powered off.",
            recovery=RecoveryAction.RECONNECT,
            context=context,
        )


class SocketError(NetworkError):
    """Low-level socket error."""

    def __init__(self, host: str, port: int, operation: str, original_error: str) -> None:
        context = ErrorContext(host=host, port=port, original_error=original_error)
        super().__init__(
            code="NET-004",
            message=f"Socket error during {operation} with {host}:{port}: {original_error}",
            recovery=RecoveryAction.RECONNECT,
            context=context,
        )


class ProtocolError(GsdvError):
    """Protocol parsing or communication errors."""

    def __init__(
        self,
        code: str,
        message: str,
        recovery: RecoveryAction = RecoveryAction.RECONNECT,
        context: Optional[ErrorContext] = None,
    ) -> None:
        super().__init__(ErrorCategory.PROTO, code, message, recovery, context)


class MalformedPacketError(ProtocolError):
    """Received packet has invalid format or length."""

    def __init__(
        self, protocol: str, expected_size: int, actual_size: int, host: Optional[str] = None
    ) -> None:
        context = ErrorContext(host=host, protocol=protocol)
        super().__init__(
            code="PROTO-001",
            message=f"Malformed {protocol} packet: expected {expected_size} bytes, got {actual_size}.",
            recovery=RecoveryAction.RECONNECT,
            context=context,
        )


class InvalidHeaderError(ProtocolError):
    """Packet header is invalid or missing."""

    def __init__(self, protocol: str, expected: str, actual: str) -> None:
        context = ErrorContext(protocol=protocol)
        super().__init__(
            code="PROTO-002",
            message=f"Invalid {protocol} header: expected {expected}, got {actual}.",
            recovery=RecoveryAction.RECONNECT,
            context=context,
        )


class PacketParseError(ProtocolError):
    """Failed to parse packet contents."""

    def __init__(self, protocol: str, field: str, reason: str) -> None:
        context = ErrorContext(protocol=protocol)
        super().__init__(
            code="PROTO-003",
            message=f"Failed to parse {protocol} packet field '{field}': {reason}",
            recovery=RecoveryAction.RECONNECT,
            context=context,
        )


class SequenceGapError(ProtocolError):
    """Detected gap in sequence numbers indicating packet loss."""

    def __init__(self, expected_seq: int, actual_seq: int, gap_size: int) -> None:
        context = ErrorContext(protocol="RDT")
        super().__init__(
            code="PROTO-004",
            message=f"Packet loss detected: expected sequence {expected_seq}, got {actual_seq} ({gap_size} packets lost).",
            recovery=RecoveryAction.MANUAL,
            context=context,
        )


class CalibrationError(GsdvError):
    """Calibration retrieval or parsing errors."""

    def __init__(
        self,
        code: str,
        message: str,
        recovery: RecoveryAction = RecoveryAction.FALLBACK,
        context: Optional[ErrorContext] = None,
    ) -> None:
        super().__init__(ErrorCategory.CAL, code, message, recovery, context)


class HttpCalibrationError(CalibrationError):
    """Failed to retrieve calibration via HTTP."""

    def __init__(self, host: str, status_code: Optional[int] = None, reason: str = "") -> None:
        context = ErrorContext(host=host, port=80, protocol="HTTP")
        if status_code:
            msg = f"HTTP calibration request to {host} failed with status {status_code}."
        else:
            msg = f"HTTP calibration request to {host} failed: {reason}"
        super().__init__(
            code="CAL-001",
            message=msg,
            recovery=RecoveryAction.FALLBACK,
            context=context,
        )


class TcpCalibrationError(CalibrationError):
    """Failed to retrieve calibration via TCP."""

    def __init__(self, host: str, reason: str) -> None:
        context = ErrorContext(host=host, port=49151, protocol="TCP")
        super().__init__(
            code="CAL-002",
            message=f"TCP calibration request to {host}:49151 failed: {reason}",
            recovery=RecoveryAction.RETRY,
            context=context,
        )


class CalibrationParseError(CalibrationError):
    """Failed to parse calibration data."""

    def __init__(self, protocol: str, field: str, reason: str) -> None:
        context = ErrorContext(protocol=protocol)
        super().__init__(
            code="CAL-003",
            message=f"Failed to parse calibration data ({protocol}): missing or invalid '{field}'. {reason}",
            recovery=RecoveryAction.RETRY,
            context=context,
        )


class CalibrationUnavailableError(CalibrationError):
    """Calibration could not be retrieved from any source."""

    def __init__(self, host: str, http_error: Optional[str], tcp_error: Optional[str]) -> None:
        context = ErrorContext(host=host)
        details = []
        if http_error:
            details.append(f"HTTP: {http_error}")
        if tcp_error:
            details.append(f"TCP: {tcp_error}")
        detail_str = "; ".join(details) if details else "Unknown reason"
        super().__init__(
            code="CAL-004",
            message=f"Could not retrieve calibration from {host}. {detail_str}",
            recovery=RecoveryAction.MANUAL,
            context=context,
        )


class BiasError(CalibrationError):
    """Failed to apply bias (tare) command."""

    def __init__(self, host: str, mode: str, reason: str) -> None:
        context = ErrorContext(host=host)
        super().__init__(
            code="CAL-005",
            message=f"Failed to apply {mode} bias to sensor at {host}: {reason}",
            recovery=RecoveryAction.FALLBACK,
            context=context,
        )


class IoError(GsdvError):
    """File I/O errors."""

    def __init__(
        self,
        code: str,
        message: str,
        recovery: RecoveryAction = RecoveryAction.CHOOSE_DIRECTORY,
        context: Optional[ErrorContext] = None,
    ) -> None:
        super().__init__(ErrorCategory.IO, code, message, recovery, context)


class DirectoryNotWritableError(IoError):
    """Output directory is not writable."""

    def __init__(self, path: str) -> None:
        context = ErrorContext(path=path)
        super().__init__(
            code="IO-001",
            message=f"Cannot write to directory '{path}'. Check permissions or choose a different directory.",
            recovery=RecoveryAction.CHOOSE_DIRECTORY,
            context=context,
        )


class DiskFullError(IoError):
    """Disk is full, cannot write data."""

    def __init__(self, path: str) -> None:
        context = ErrorContext(path=path)
        super().__init__(
            code="IO-002",
            message=f"Disk full while writing to '{path}'. Recording stopped to preserve existing data.",
            recovery=RecoveryAction.CHOOSE_DIRECTORY,
            context=context,
        )


class LogRotationError(IoError):
    """Failed to rotate log file."""

    def __init__(self, current_path: str, reason: str) -> None:
        context = ErrorContext(path=current_path, original_error=reason)
        super().__init__(
            code="IO-003",
            message=f"Failed to rotate log file: {reason}. Recording stopped, existing data preserved.",
            recovery=RecoveryAction.CHOOSE_DIRECTORY,
            context=context,
        )


class FileWriteError(IoError):
    """General file write error."""

    def __init__(self, path: str, reason: str) -> None:
        context = ErrorContext(path=path, original_error=reason)
        super().__init__(
            code="IO-004",
            message=f"Error writing to '{path}': {reason}",
            recovery=RecoveryAction.CHOOSE_DIRECTORY,
            context=context,
        )


class FileCloseError(IoError):
    """Error closing file (data may be incomplete)."""

    def __init__(self, path: str, reason: str) -> None:
        context = ErrorContext(path=path, original_error=reason)
        super().__init__(
            code="IO-005",
            message=f"Error closing file '{path}': {reason}. Data may be incomplete.",
            recovery=RecoveryAction.MANUAL,
            context=context,
        )
