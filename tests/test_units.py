"""Tests for unit conversion logic."""

import pytest

from gsdv.config.preferences import ForceUnit, TorqueUnit
from gsdv.processing.units import (
    FORCE_TO_NEWTONS,
    TORQUE_TO_NEWTON_METERS,
    convert_force,
    convert_torque,
    force_from_newtons,
    force_to_newtons,
    force_unit_from_sensor_code,
    torque_from_newton_meters,
    torque_to_newton_meters,
    torque_unit_from_sensor_code,
)


class TestForceConversion:
    """Tests for force unit conversions."""

    def test_newtons_to_lbf(self) -> None:
        """1 N should convert to approximately 0.2248 lbf."""
        result = convert_force(1.0, ForceUnit.N, ForceUnit.lbf)
        assert result == pytest.approx(0.2248089, rel=1e-5)

    def test_lbf_to_newtons(self) -> None:
        """1 lbf should convert to approximately 4.448 N."""
        result = convert_force(1.0, ForceUnit.lbf, ForceUnit.N)
        assert result == pytest.approx(4.4482216152605, rel=1e-10)

    def test_newtons_to_kgf(self) -> None:
        """1 N should convert to approximately 0.102 kgf."""
        result = convert_force(1.0, ForceUnit.N, ForceUnit.kgf)
        assert result == pytest.approx(0.1019716, rel=1e-5)

    def test_kgf_to_newtons(self) -> None:
        """1 kgf should convert to exactly 9.80665 N."""
        result = convert_force(1.0, ForceUnit.kgf, ForceUnit.N)
        assert result == pytest.approx(9.80665, rel=1e-10)

    def test_lbf_to_kgf(self) -> None:
        """1 lbf should convert to approximately 0.4536 kgf."""
        result = convert_force(1.0, ForceUnit.lbf, ForceUnit.kgf)
        expected = 4.4482216152605 / 9.80665
        assert result == pytest.approx(expected, rel=1e-10)

    def test_same_unit_is_identity(self) -> None:
        """Converting between same units returns the same value."""
        for unit in ForceUnit:
            assert convert_force(42.5, unit, unit) == 42.5

    def test_force_to_newtons(self) -> None:
        """force_to_newtons converts to canonical N."""
        assert force_to_newtons(1.0, ForceUnit.N) == 1.0
        assert force_to_newtons(1.0, ForceUnit.lbf) == pytest.approx(4.4482216152605)
        assert force_to_newtons(1.0, ForceUnit.kgf) == pytest.approx(9.80665)

    def test_force_from_newtons(self) -> None:
        """force_from_newtons converts from canonical N."""
        assert force_from_newtons(1.0, ForceUnit.N) == 1.0
        assert force_from_newtons(4.4482216152605, ForceUnit.lbf) == pytest.approx(1.0)
        assert force_from_newtons(9.80665, ForceUnit.kgf) == pytest.approx(1.0)

    def test_roundtrip_conversion(self) -> None:
        """Converting N -> other -> N should return original value."""
        original = 100.0
        for unit in ForceUnit:
            converted = convert_force(original, ForceUnit.N, unit)
            back = convert_force(converted, unit, ForceUnit.N)
            assert back == pytest.approx(original, rel=1e-10)

    def test_negative_values(self) -> None:
        """Negative force values should convert correctly."""
        result = convert_force(-10.0, ForceUnit.N, ForceUnit.lbf)
        expected = convert_force(10.0, ForceUnit.N, ForceUnit.lbf)
        assert result == pytest.approx(-expected)

    def test_zero_value(self) -> None:
        """Zero should remain zero after conversion."""
        for from_unit in ForceUnit:
            for to_unit in ForceUnit:
                assert convert_force(0.0, from_unit, to_unit) == 0.0


class TestTorqueConversion:
    """Tests for torque unit conversions."""

    def test_nm_to_nmm(self) -> None:
        """1 N·m should convert to 1000 N·mm."""
        result = convert_torque(1.0, TorqueUnit.Nm, TorqueUnit.Nmm)
        assert result == pytest.approx(1000.0, rel=1e-10)

    def test_nmm_to_nm(self) -> None:
        """1000 N·mm should convert to 1 N·m."""
        result = convert_torque(1000.0, TorqueUnit.Nmm, TorqueUnit.Nm)
        assert result == pytest.approx(1.0, rel=1e-10)

    def test_nm_to_lbf_ft(self) -> None:
        """1 N·m should convert to approximately 0.7376 lbf·ft."""
        result = convert_torque(1.0, TorqueUnit.Nm, TorqueUnit.lbf_ft)
        assert result == pytest.approx(0.7375621, rel=1e-5)

    def test_lbf_ft_to_nm(self) -> None:
        """1 lbf·ft should convert to approximately 1.3558 N·m."""
        result = convert_torque(1.0, TorqueUnit.lbf_ft, TorqueUnit.Nm)
        assert result == pytest.approx(1.3558179483314004, rel=1e-10)

    def test_nm_to_lbf_in(self) -> None:
        """1 N·m should convert to approximately 8.8507 lbf·in."""
        result = convert_torque(1.0, TorqueUnit.Nm, TorqueUnit.lbf_in)
        assert result == pytest.approx(8.8507457, rel=1e-5)

    def test_lbf_in_to_nm(self) -> None:
        """1 lbf·in should convert to approximately 0.1130 N·m."""
        result = convert_torque(1.0, TorqueUnit.lbf_in, TorqueUnit.Nm)
        assert result == pytest.approx(0.1129848290276167, rel=1e-10)

    def test_lbf_ft_to_lbf_in(self) -> None:
        """1 lbf·ft should convert to 12 lbf·in."""
        result = convert_torque(1.0, TorqueUnit.lbf_ft, TorqueUnit.lbf_in)
        assert result == pytest.approx(12.0, rel=1e-5)

    def test_same_unit_is_identity(self) -> None:
        """Converting between same units returns the same value."""
        for unit in TorqueUnit:
            assert convert_torque(42.5, unit, unit) == 42.5

    def test_torque_to_newton_meters(self) -> None:
        """torque_to_newton_meters converts to canonical N·m."""
        assert torque_to_newton_meters(1.0, TorqueUnit.Nm) == 1.0
        assert torque_to_newton_meters(1000.0, TorqueUnit.Nmm) == pytest.approx(1.0)
        assert torque_to_newton_meters(1.0, TorqueUnit.lbf_ft) == pytest.approx(1.3558179483314004)
        assert torque_to_newton_meters(1.0, TorqueUnit.lbf_in) == pytest.approx(0.1129848290276167)

    def test_torque_from_newton_meters(self) -> None:
        """torque_from_newton_meters converts from canonical N·m."""
        assert torque_from_newton_meters(1.0, TorqueUnit.Nm) == 1.0
        assert torque_from_newton_meters(1.0, TorqueUnit.Nmm) == pytest.approx(1000.0)
        assert torque_from_newton_meters(
            1.3558179483314004, TorqueUnit.lbf_ft
        ) == pytest.approx(1.0)
        assert torque_from_newton_meters(
            0.1129848290276167, TorqueUnit.lbf_in
        ) == pytest.approx(1.0)

    def test_roundtrip_conversion(self) -> None:
        """Converting N·m -> other -> N·m should return original value."""
        original = 100.0
        for unit in TorqueUnit:
            converted = convert_torque(original, TorqueUnit.Nm, unit)
            back = convert_torque(converted, unit, TorqueUnit.Nm)
            assert back == pytest.approx(original, rel=1e-10)

    def test_negative_values(self) -> None:
        """Negative torque values should convert correctly."""
        result = convert_torque(-10.0, TorqueUnit.Nm, TorqueUnit.lbf_ft)
        expected = convert_torque(10.0, TorqueUnit.Nm, TorqueUnit.lbf_ft)
        assert result == pytest.approx(-expected)

    def test_zero_value(self) -> None:
        """Zero should remain zero after conversion."""
        for from_unit in TorqueUnit:
            for to_unit in TorqueUnit:
                assert convert_torque(0.0, from_unit, to_unit) == 0.0


class TestSensorUnitCodes:
    """Tests for sensor unit code conversion."""

    def test_force_unit_from_sensor_code_lbf(self) -> None:
        """Code 1 should map to lbf."""
        assert force_unit_from_sensor_code(1) == ForceUnit.lbf

    def test_force_unit_from_sensor_code_n(self) -> None:
        """Code 2 should map to N."""
        assert force_unit_from_sensor_code(2) == ForceUnit.N

    def test_force_unit_from_sensor_code_kgf(self) -> None:
        """Code 5 should map to kgf."""
        assert force_unit_from_sensor_code(5) == ForceUnit.kgf

    def test_force_unit_from_sensor_code_invalid(self) -> None:
        """Invalid code should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown force unit code"):
            force_unit_from_sensor_code(99)

    def test_torque_unit_from_sensor_code_lbf_in(self) -> None:
        """Code 1 should map to lbf_in."""
        assert torque_unit_from_sensor_code(1) == TorqueUnit.lbf_in

    def test_torque_unit_from_sensor_code_lbf_ft(self) -> None:
        """Code 2 should map to lbf_ft."""
        assert torque_unit_from_sensor_code(2) == TorqueUnit.lbf_ft

    def test_torque_unit_from_sensor_code_nm(self) -> None:
        """Code 3 should map to Nm."""
        assert torque_unit_from_sensor_code(3) == TorqueUnit.Nm

    def test_torque_unit_from_sensor_code_nmm(self) -> None:
        """Code 4 should map to Nmm."""
        assert torque_unit_from_sensor_code(4) == TorqueUnit.Nmm

    def test_torque_unit_from_sensor_code_invalid(self) -> None:
        """Invalid code should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown torque unit code"):
            torque_unit_from_sensor_code(99)


class TestConversionFactorCompleteness:
    """Tests that all enum values have conversion factors defined."""

    def test_all_force_units_have_factors(self) -> None:
        """Every ForceUnit should have a conversion factor."""
        for unit in ForceUnit:
            assert unit in FORCE_TO_NEWTONS, f"Missing factor for {unit}"
            assert FORCE_TO_NEWTONS[unit] > 0, f"Invalid factor for {unit}"

    def test_all_torque_units_have_factors(self) -> None:
        """Every TorqueUnit should have a conversion factor."""
        for unit in TorqueUnit:
            assert unit in TORQUE_TO_NEWTON_METERS, f"Missing factor for {unit}"
            assert TORQUE_TO_NEWTON_METERS[unit] > 0, f"Invalid factor for {unit}"
