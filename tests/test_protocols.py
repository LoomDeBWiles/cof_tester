"""Tests for RDT, TCP, and HTTP protocol implementations."""

import pytest

from gsdv.protocols import CalibrationInfo, SampleRecord


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

    def test_placeholder(self) -> None:
        """Placeholder test."""
        pass


class TestTcpCmd:
    """Tests for TCP command interface."""

    def test_placeholder(self) -> None:
        """Placeholder test."""
        pass


class TestHttpCalibration:
    """Tests for HTTP calibration retrieval."""

    def test_placeholder(self) -> None:
        """Placeholder test."""
        pass
