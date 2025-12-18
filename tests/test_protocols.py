"""Tests for RDT, TCP, and HTTP protocol implementations."""

import pytest
from pathlib import Path

from gsdv.protocols import CalibrationInfo, SampleRecord
from gsdv.protocols.rdt_udp import parse_rdt_response
from gsdv.protocols.tcp_cmd import (
    TRANSFORM_VALUE_MAX,
    TRANSFORM_VALUE_MIN,
    ToolTransform,
    build_transform_request,
    parse_calinfo_response,
)
from gsdv.protocols.http_calibration import parse_calibration_xml


class TestSampleRecord:
    """Tests for SampleRecord dataclass."""

    def test_create_with_required_fields_only(self) -> None:
        """SampleRecord can be created with only required fields."""
        record = SampleRecord(
            t_monotonic_ns=1000000000,
            rdt_sequence=42,
            ft_sequence=100,
            status=0,
            counts=(1000, 2000, 3000, 400, 500, 600),
        )
        assert record.t_monotonic_ns == 1000000000
        assert record.rdt_sequence == 42
        assert record.ft_sequence == 100
        assert record.status == 0
        assert record.counts == (1000, 2000, 3000, 400, 500, 600)
        assert record.force_N is None
        assert record.torque_Nm is None

    def test_create_with_all_fields(self) -> None:
        """SampleRecord can be created with all fields including optional."""
        record = SampleRecord(
            t_monotonic_ns=1000000000,
            rdt_sequence=42,
            ft_sequence=100,
            status=0,
            counts=(1000, 2000, 3000, 400, 500, 600),
            force_N=(10.0, 20.0, 30.0),
            torque_Nm=(0.4, 0.5, 0.6),
        )
        assert record.force_N == (10.0, 20.0, 30.0)
        assert record.torque_Nm == (0.4, 0.5, 0.6)

    def test_counts_wrong_length_raises_value_error(self) -> None:
        """SampleRecord raises ValueError if counts has wrong length."""
        with pytest.raises(ValueError, match="counts must have exactly 6 elements"):
            SampleRecord(
                t_monotonic_ns=1000000000,
                rdt_sequence=42,
                ft_sequence=100,
                status=0,
                counts=(1000, 2000, 3000),
            )

    def test_force_N_wrong_length_raises_value_error(self) -> None:
        """SampleRecord raises ValueError if force_N has wrong length."""
        with pytest.raises(ValueError, match="force_N must have exactly 3 elements"):
            SampleRecord(
                t_monotonic_ns=1000000000,
                rdt_sequence=42,
                ft_sequence=100,
                status=0,
                counts=(1000, 2000, 3000, 400, 500, 600),
                force_N=(10.0, 20.0),
            )

    def test_torque_Nm_wrong_length_raises_value_error(self) -> None:
        """SampleRecord raises ValueError if torque_Nm has wrong length."""
        with pytest.raises(ValueError, match="torque_Nm must have exactly 3 elements"):
            SampleRecord(
                t_monotonic_ns=1000000000,
                rdt_sequence=42,
                ft_sequence=100,
                status=0,
                counts=(1000, 2000, 3000, 400, 500, 600),
                torque_Nm=(0.1,),
            )

    def test_frozen_immutable(self) -> None:
        """SampleRecord is immutable (frozen dataclass)."""
        record = SampleRecord(
            t_monotonic_ns=1000000000,
            rdt_sequence=42,
            ft_sequence=100,
            status=0,
            counts=(1000, 2000, 3000, 400, 500, 600),
        )
        with pytest.raises(AttributeError):
            record.rdt_sequence = 99  # type: ignore[misc]

    def test_equality(self) -> None:
        """SampleRecord instances with same values are equal."""
        record1 = SampleRecord(
            t_monotonic_ns=1000000000,
            rdt_sequence=42,
            ft_sequence=100,
            status=0,
            counts=(1000, 2000, 3000, 400, 500, 600),
        )
        record2 = SampleRecord(
            t_monotonic_ns=1000000000,
            rdt_sequence=42,
            ft_sequence=100,
            status=0,
            counts=(1000, 2000, 3000, 400, 500, 600),
        )
        assert record1 == record2

    def test_negative_counts_allowed(self) -> None:
        """SampleRecord allows negative count values (valid sensor data)."""
        record = SampleRecord(
            t_monotonic_ns=1000000000,
            rdt_sequence=42,
            ft_sequence=100,
            status=0,
            counts=(-1000, -2000, -3000, -400, -500, -600),
        )
        assert record.counts == (-1000, -2000, -3000, -400, -500, -600)


class TestCalibrationInfo:
    """Tests for CalibrationInfo dataclass."""

    def test_create_with_required_fields_only(self) -> None:
        """CalibrationInfo can be created with only required fields."""
        cal = CalibrationInfo(
            counts_per_force=1000000.0,
            counts_per_torque=1000000.0,
        )
        assert cal.counts_per_force == 1000000.0
        assert cal.counts_per_torque == 1000000.0
        assert cal.serial_number is None
        assert cal.firmware_version is None
        assert cal.force_units_code is None
        assert cal.torque_units_code is None

    def test_create_with_all_fields(self) -> None:
        """CalibrationInfo can be created with all fields."""
        cal = CalibrationInfo(
            counts_per_force=1000000.0,
            counts_per_torque=500000.0,
            serial_number="FT12345",
            firmware_version="1.2.3",
            force_units_code=2,
            torque_units_code=3,
        )
        assert cal.counts_per_force == 1000000.0
        assert cal.counts_per_torque == 500000.0
        assert cal.serial_number == "FT12345"
        assert cal.firmware_version == "1.2.3"
        assert cal.force_units_code == 2
        assert cal.torque_units_code == 3

    def test_zero_counts_per_force_raises_value_error(self) -> None:
        """CalibrationInfo raises ValueError if counts_per_force is zero."""
        with pytest.raises(ValueError, match="counts_per_force must be positive"):
            CalibrationInfo(
                counts_per_force=0,
                counts_per_torque=1000000.0,
            )

    def test_negative_counts_per_force_raises_value_error(self) -> None:
        """CalibrationInfo raises ValueError if counts_per_force is negative."""
        with pytest.raises(ValueError, match="counts_per_force must be positive"):
            CalibrationInfo(
                counts_per_force=-1000000.0,
                counts_per_torque=1000000.0,
            )

    def test_zero_counts_per_torque_raises_value_error(self) -> None:
        """CalibrationInfo raises ValueError if counts_per_torque is zero."""
        with pytest.raises(ValueError, match="counts_per_torque must be positive"):
            CalibrationInfo(
                counts_per_force=1000000.0,
                counts_per_torque=0,
            )

    def test_negative_counts_per_torque_raises_value_error(self) -> None:
        """CalibrationInfo raises ValueError if counts_per_torque is negative."""
        with pytest.raises(ValueError, match="counts_per_torque must be positive"):
            CalibrationInfo(
                counts_per_force=1000000.0,
                counts_per_torque=-500000.0,
            )

    def test_frozen_immutable(self) -> None:
        """CalibrationInfo is immutable (frozen dataclass)."""
        cal = CalibrationInfo(
            counts_per_force=1000000.0,
            counts_per_torque=1000000.0,
        )
        with pytest.raises(AttributeError):
            cal.counts_per_force = 2000000.0  # type: ignore[misc]

    def test_equality(self) -> None:
        """CalibrationInfo instances with same values are equal."""
        cal1 = CalibrationInfo(
            counts_per_force=1000000.0,
            counts_per_torque=500000.0,
            serial_number="FT12345",
        )
        cal2 = CalibrationInfo(
            counts_per_force=1000000.0,
            counts_per_torque=500000.0,
            serial_number="FT12345",
        )
        assert cal1 == cal2


class TestRdtUdp:
    """Tests for UDP RDT streaming protocol."""

    def test_parse_rdt_packet_from_fixture(self) -> None:
        """Parse RDT packet from binary fixture."""
        fixture_path = Path("tests/fixtures/rdt_packet.bin")
        data = fixture_path.read_bytes()
        rdt_seq, ft_seq, status, counts = parse_rdt_response(data)

        assert rdt_seq == 1
        assert ft_seq == 100
        assert status == 0
        assert counts == (1000, 2000, 3000, 400, 500, 600)


class TestTcpCmd:
    """Tests for TCP command interface."""

    def test_parse_calinfo_response_from_fixture(self) -> None:
        """Parse calibration info from binary fixture."""
        fixture_path = Path("tests/fixtures/tcp_calinfo.bin")
        data = fixture_path.read_bytes()
        cal = parse_calinfo_response(data)

        assert cal.counts_per_force == 1000000.0
        assert cal.counts_per_torque == 1000000.0
        assert cal.force_units_code == 2
        assert cal.torque_units_code == 3

    def test_build_transform_request_valid_values(self) -> None:
        """build_transform_request succeeds with values within range."""
        transform = ToolTransform(dx=100.0, dy=-50.0, dz=0.0, rx=45.0, ry=-30.0, rz=15.5)
        result = build_transform_request(transform)
        assert len(result) == 20

    def test_build_transform_request_at_max_boundary(self) -> None:
        """build_transform_request succeeds at maximum boundary value."""
        transform = ToolTransform(
            dx=TRANSFORM_VALUE_MAX,
            dy=TRANSFORM_VALUE_MAX,
            dz=TRANSFORM_VALUE_MAX,
            rx=TRANSFORM_VALUE_MAX,
            ry=TRANSFORM_VALUE_MAX,
            rz=TRANSFORM_VALUE_MAX,
        )
        result = build_transform_request(transform)
        assert len(result) == 20

    def test_build_transform_request_at_min_boundary(self) -> None:
        """build_transform_request succeeds at minimum boundary value."""
        transform = ToolTransform(
            dx=TRANSFORM_VALUE_MIN,
            dy=TRANSFORM_VALUE_MIN,
            dz=TRANSFORM_VALUE_MIN,
            rx=TRANSFORM_VALUE_MIN,
            ry=TRANSFORM_VALUE_MIN,
            rz=TRANSFORM_VALUE_MIN,
        )
        result = build_transform_request(transform)
        assert len(result) == 20

    def test_build_transform_request_value_exceeds_max_raises_value_error(self) -> None:
        """build_transform_request raises ValueError when value exceeds maximum."""
        transform = ToolTransform(dx=400.0)
        with pytest.raises(ValueError, match=r"dx=400\.0 is outside valid range"):
            build_transform_request(transform)

    def test_build_transform_request_value_below_min_raises_value_error(self) -> None:
        """build_transform_request raises ValueError when value below minimum."""
        transform = ToolTransform(dy=-400.0)
        with pytest.raises(ValueError, match=r"dy=-400\.0 is outside valid range"):
            build_transform_request(transform)

    def test_build_transform_request_error_message_includes_field_name(self) -> None:
        """build_transform_request error message identifies the invalid field."""
        transform = ToolTransform(rz=500.0)
        with pytest.raises(ValueError, match=r"rz=500\.0"):
            build_transform_request(transform)

    def test_build_transform_request_error_message_includes_valid_range(self) -> None:
        """build_transform_request error message shows valid range."""
        transform = ToolTransform(dx=400.0)
        with pytest.raises(
            ValueError, match=rf"\[{TRANSFORM_VALUE_MIN}, {TRANSFORM_VALUE_MAX}\]"
        ):
            build_transform_request(transform)

    def test_build_transform_request_values_encoded_as_int16_times_100(self) -> None:
        """build_transform_request encodes values as int16 * 100 big-endian."""
        import struct

        transform = ToolTransform(dx=10.5, dy=-20.25, dz=0.01, rx=1.5, ry=-2.5, rz=100.0)
        request = build_transform_request(transform)

        # Extract packed int16 values from bytes 3-14
        values = struct.unpack(">6h", request[3:15])
        assert values[0] == 1050   # 10.5 * 100
        assert values[1] == -2025  # -20.25 * 100
        assert values[2] == 1      # 0.01 * 100 = 1 (truncated to int)
        assert values[3] == 150    # 1.5 * 100
        assert values[4] == -250   # -2.5 * 100
        assert values[5] == 10000  # 100.0 * 100

    def test_build_transform_request_zero_values_produce_zero_bytes(self) -> None:
        """build_transform_request encodes zero transform to zero bytes."""
        import struct

        transform = ToolTransform()
        request = build_transform_request(transform)

        values = struct.unpack(">6h", request[3:15])
        assert values == (0, 0, 0, 0, 0, 0)

    def test_build_transform_request_packet_header(self) -> None:
        """build_transform_request sets correct command and unit bytes."""
        from gsdv.protocols.tcp_cmd import TcpCommand, TransformDistUnits, TransformAngleUnits

        transform = ToolTransform(dx=10.0)
        request = build_transform_request(transform)

        assert request[0] == TcpCommand.WRITETRANSFORM
        assert request[1] == TransformDistUnits.MM
        assert request[2] == TransformAngleUnits.DEGREES

    def test_build_transform_request_padding_bytes_are_zero(self) -> None:
        """build_transform_request fills remaining bytes with zeros."""
        transform = ToolTransform(dx=10.0, dy=20.0, dz=30.0, rx=1.0, ry=2.0, rz=3.0)
        request = build_transform_request(transform)

        # Bytes 15-19 (5 bytes) should be zero padding
        assert request[15:20] == b"\x00\x00\x00\x00\x00"


class TestHttpCalibration:
    """Tests for HTTP calibration retrieval."""

    def test_parse_calibration_xml_from_fixture(self) -> None:
        """Parse calibration XML from fixture."""
        fixture_path = Path("tests/fixtures/netftapi2.xml")
        xml_content = fixture_path.read_text()
        cal = parse_calibration_xml(xml_content)

        assert cal.counts_per_force == 1000000.0
        assert cal.counts_per_torque == 1000000.0
        assert cal.serial_number == "FT12345"
        assert cal.firmware_version == "1.0.0"
        assert cal.force_units_code == 2
        assert cal.torque_units_code == 3
