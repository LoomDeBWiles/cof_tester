"""Tests for GSDV error types and recovery strategies."""

import pytest

from gsdv.errors import (
    BiasError,
    CalibrationError,
    CalibrationParseError,
    CalibrationUnavailableError,
    ConnectionRefusedError,
    ConnectionTimeoutError,
    DirectoryNotWritableError,
    DiskFullError,
    ErrorCategory,
    ErrorContext,
    FileCloseError,
    FileWriteError,
    GsdvError,
    HttpCalibrationError,
    InvalidHeaderError,
    IoError,
    LogRotationError,
    MalformedPacketError,
    NetworkDisconnectError,
    NetworkError,
    PacketParseError,
    ProtocolError,
    RecoveryAction,
    SequenceGapError,
    SocketError,
    TcpCalibrationError,
)


class TestErrorContext:
    """Tests for ErrorContext dataclass."""

    def test_default_values(self) -> None:
        """ErrorContext has all None defaults."""
        ctx = ErrorContext()
        assert ctx.host is None
        assert ctx.port is None
        assert ctx.path is None
        assert ctx.protocol is None
        assert ctx.original_error is None

    def test_with_all_fields(self) -> None:
        """ErrorContext can hold all fields."""
        ctx = ErrorContext(
            host="192.168.1.100",
            port=49152,
            path="/var/log/data.csv",
            protocol="UDP",
            original_error="Connection reset",
        )
        assert ctx.host == "192.168.1.100"
        assert ctx.port == 49152
        assert ctx.path == "/var/log/data.csv"
        assert ctx.protocol == "UDP"
        assert ctx.original_error == "Connection reset"

    def test_frozen(self) -> None:
        """ErrorContext is immutable."""
        ctx = ErrorContext(host="localhost")
        with pytest.raises(AttributeError):
            ctx.host = "other"  # type: ignore[misc]


class TestGsdvError:
    """Tests for base GsdvError class."""

    def test_str_includes_code_and_message(self) -> None:
        """String representation includes error code and message."""
        err = GsdvError(
            category=ErrorCategory.NET,
            code="TEST-001",
            message="Test error message",
            recovery=RecoveryAction.RETRY,
        )
        assert str(err) == "[TEST-001] Test error message"

    def test_user_message_returns_message(self) -> None:
        """user_message returns the message."""
        err = GsdvError(
            category=ErrorCategory.IO,
            code="TEST-002",
            message="User friendly message",
            recovery=RecoveryAction.MANUAL,
        )
        assert err.user_message() == "User friendly message"

    def test_context_defaults_to_empty(self) -> None:
        """Context defaults to empty ErrorContext."""
        err = GsdvError(
            category=ErrorCategory.CAL,
            code="TEST-003",
            message="No context",
            recovery=RecoveryAction.FALLBACK,
        )
        assert err.context is not None
        assert err.context.host is None

    def test_accepts_custom_context(self) -> None:
        """Custom context is preserved."""
        ctx = ErrorContext(host="10.0.0.1", port=80)
        err = GsdvError(
            category=ErrorCategory.NET,
            code="TEST-004",
            message="With context",
            recovery=RecoveryAction.RECONNECT,
            context=ctx,
        )
        assert err.context.host == "10.0.0.1"
        assert err.context.port == 80


class TestNetworkErrors:
    """Tests for network error types."""

    def test_connection_refused_error(self) -> None:
        """ConnectionRefusedError has correct code and message."""
        err = ConnectionRefusedError("192.168.1.50", 49152)
        assert err.code == "NET-001"
        assert err.category == ErrorCategory.NET
        assert err.recovery == RecoveryAction.RECONNECT
        assert "192.168.1.50:49152" in err.message
        assert "refused" in err.message.lower()
        assert err.context.host == "192.168.1.50"
        assert err.context.port == 49152

    def test_connection_timeout_error(self) -> None:
        """ConnectionTimeoutError includes timeout duration."""
        err = ConnectionTimeoutError("10.0.0.5", 49151, 5.0)
        assert err.code == "NET-002"
        assert err.recovery == RecoveryAction.RETRY
        assert "10.0.0.5:49151" in err.message
        assert "5.0s" in err.message
        assert "timed out" in err.message.lower()

    def test_network_disconnect_error(self) -> None:
        """NetworkDisconnectError indicates lost connection."""
        err = NetworkDisconnectError("192.168.1.100", 49152, "Connection reset by peer")
        assert err.code == "NET-003"
        assert err.recovery == RecoveryAction.RECONNECT
        assert "Lost connection" in err.message
        assert err.context.original_error == "Connection reset by peer"

    def test_socket_error(self) -> None:
        """SocketError includes operation and original error."""
        err = SocketError("192.168.1.100", 49152, "bind", "Address already in use")
        assert err.code == "NET-004"
        assert "bind" in err.message
        assert "Address already in use" in err.message


class TestProtocolErrors:
    """Tests for protocol error types."""

    def test_malformed_packet_error(self) -> None:
        """MalformedPacketError includes size information."""
        err = MalformedPacketError("RDT", 36, 24, "192.168.1.100")
        assert err.code == "PROTO-001"
        assert err.category == ErrorCategory.PROTO
        assert "36 bytes" in err.message
        assert "24" in err.message
        assert err.context.protocol == "RDT"

    def test_invalid_header_error(self) -> None:
        """InvalidHeaderError shows expected vs actual."""
        err = InvalidHeaderError("TCP", "0x1234", "0x0000")
        assert err.code == "PROTO-002"
        assert "0x1234" in err.message
        assert "0x0000" in err.message

    def test_packet_parse_error(self) -> None:
        """PacketParseError includes field name."""
        err = PacketParseError("RDT", "ft_sequence", "invalid integer")
        assert err.code == "PROTO-003"
        assert "ft_sequence" in err.message
        assert "invalid integer" in err.message

    def test_sequence_gap_error(self) -> None:
        """SequenceGapError reports packet loss."""
        err = SequenceGapError(100, 105, 5)
        assert err.code == "PROTO-004"
        assert err.recovery == RecoveryAction.MANUAL
        assert "100" in err.message
        assert "105" in err.message
        assert "5 packets lost" in err.message


class TestCalibrationErrors:
    """Tests for calibration error types."""

    def test_http_calibration_error_with_status(self) -> None:
        """HttpCalibrationError shows HTTP status code."""
        err = HttpCalibrationError("192.168.1.100", status_code=404)
        assert err.code == "CAL-001"
        assert err.category == ErrorCategory.CAL
        assert err.recovery == RecoveryAction.FALLBACK
        assert "404" in err.message
        assert err.context.port == 80

    def test_http_calibration_error_with_reason(self) -> None:
        """HttpCalibrationError shows reason when no status."""
        err = HttpCalibrationError("192.168.1.100", reason="Connection refused")
        assert "Connection refused" in err.message

    def test_tcp_calibration_error(self) -> None:
        """TcpCalibrationError indicates TCP failure."""
        err = TcpCalibrationError("192.168.1.100", "timeout")
        assert err.code == "CAL-002"
        assert err.recovery == RecoveryAction.RETRY
        assert "49151" in err.message
        assert "timeout" in err.message

    def test_calibration_parse_error(self) -> None:
        """CalibrationParseError identifies missing field."""
        err = CalibrationParseError("HTTP", "counts_per_force", "not found in XML")
        assert err.code == "CAL-003"
        assert "counts_per_force" in err.message
        assert "not found in XML" in err.message

    def test_calibration_unavailable_error(self) -> None:
        """CalibrationUnavailableError combines HTTP and TCP failures."""
        err = CalibrationUnavailableError(
            "192.168.1.100",
            http_error="404 Not Found",
            tcp_error="Connection refused",
        )
        assert err.code == "CAL-004"
        assert err.recovery == RecoveryAction.MANUAL
        assert "HTTP: 404 Not Found" in err.message
        assert "TCP: Connection refused" in err.message

    def test_bias_error(self) -> None:
        """BiasError indicates bias mode and failure reason."""
        err = BiasError("192.168.1.100", "device tare", "no response")
        assert err.code == "CAL-005"
        assert err.recovery == RecoveryAction.FALLBACK
        assert "device tare" in err.message
        assert "no response" in err.message


class TestIoErrors:
    """Tests for I/O error types."""

    def test_directory_not_writable_error(self) -> None:
        """DirectoryNotWritableError includes path."""
        err = DirectoryNotWritableError("/read/only/dir")
        assert err.code == "IO-001"
        assert err.category == ErrorCategory.IO
        assert err.recovery == RecoveryAction.CHOOSE_DIRECTORY
        assert "/read/only/dir" in err.message
        assert err.context.path == "/read/only/dir"

    def test_disk_full_error(self) -> None:
        """DiskFullError indicates data preservation."""
        err = DiskFullError("/var/data/sensor.csv")
        assert err.code == "IO-002"
        assert "preserve" in err.message.lower()
        assert err.context.path == "/var/data/sensor.csv"

    def test_log_rotation_error(self) -> None:
        """LogRotationError stops recording gracefully."""
        err = LogRotationError("/var/data/sensor.csv", "cannot create next file")
        assert err.code == "IO-003"
        assert "rotate" in err.message.lower()
        assert "preserved" in err.message.lower()

    def test_file_write_error(self) -> None:
        """FileWriteError includes path and reason."""
        err = FileWriteError("/data/sensor.csv", "permission denied")
        assert err.code == "IO-004"
        assert "/data/sensor.csv" in err.message
        assert "permission denied" in err.message

    def test_file_close_error(self) -> None:
        """FileCloseError warns about incomplete data."""
        err = FileCloseError("/data/sensor.csv", "I/O error")
        assert err.code == "IO-005"
        assert err.recovery == RecoveryAction.MANUAL
        assert "incomplete" in err.message.lower()


class TestErrorHierarchy:
    """Tests for error inheritance."""

    def test_network_error_is_gsdv_error(self) -> None:
        """NetworkError inherits from GsdvError."""
        err = ConnectionRefusedError("host", 80)
        assert isinstance(err, NetworkError)
        assert isinstance(err, GsdvError)
        assert isinstance(err, Exception)

    def test_protocol_error_is_gsdv_error(self) -> None:
        """ProtocolError inherits from GsdvError."""
        err = MalformedPacketError("UDP", 100, 50)
        assert isinstance(err, ProtocolError)
        assert isinstance(err, GsdvError)

    def test_calibration_error_is_gsdv_error(self) -> None:
        """CalibrationError inherits from GsdvError."""
        err = HttpCalibrationError("host", status_code=500)
        assert isinstance(err, CalibrationError)
        assert isinstance(err, GsdvError)

    def test_io_error_is_gsdv_error(self) -> None:
        """IoError inherits from GsdvError."""
        err = DiskFullError("/path")
        assert isinstance(err, IoError)
        assert isinstance(err, GsdvError)

    def test_can_catch_by_category(self) -> None:
        """Errors can be caught by category base class."""
        errors = [
            ConnectionRefusedError("host", 80),
            MalformedPacketError("UDP", 100, 50),
            HttpCalibrationError("host"),
            DiskFullError("/path"),
        ]

        network_errors = [e for e in errors if isinstance(e, NetworkError)]
        assert len(network_errors) == 1

        io_errors = [e for e in errors if isinstance(e, IoError)]
        assert len(io_errors) == 1
