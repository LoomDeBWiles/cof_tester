"""Unit conversion for force and torque values.

Implements Section 7.1 (BL-1, BL-2), FR-9, FR-10, FR-11.
Internal canonical units are Newtons (N) for force and Newton-meters (N·m) for torque.
"""

from enum import Enum

from gsdv.config.preferences import ForceUnit, TorqueUnit


# Conversion factors TO canonical units (N for force, N·m for torque)
# These factors are applied: canonical = value * factor
FORCE_TO_NEWTONS: dict[ForceUnit, float] = {
    ForceUnit.N: 1.0,
    ForceUnit.lbf: 4.4482216152605,  # 1 lbf = 4.44822... N (exact definition)
    ForceUnit.kgf: 9.80665,  # 1 kgf = 9.80665 N (exact definition, standard gravity)
}

TORQUE_TO_NEWTON_METERS: dict[TorqueUnit, float] = {
    TorqueUnit.Nm: 1.0,
    TorqueUnit.Nmm: 0.001,  # 1 N·mm = 0.001 N·m
    TorqueUnit.lbf_in: 0.1129848290276167,  # 1 lbf·in = lbf * in_to_m
    TorqueUnit.lbf_ft: 1.3558179483314004,  # 1 lbf·ft = lbf * ft_to_m
}


def convert_force(value: float, from_unit: ForceUnit, to_unit: ForceUnit) -> float:
    """Convert force between supported units.

    Args:
        value: Force value to convert.
        from_unit: Source force unit.
        to_unit: Target force unit.

    Returns:
        Converted force value.
    """
    if from_unit == to_unit:
        return value
    # Convert to canonical (N), then to target
    newtons = value * FORCE_TO_NEWTONS[from_unit]
    return newtons / FORCE_TO_NEWTONS[to_unit]


def convert_torque(value: float, from_unit: TorqueUnit, to_unit: TorqueUnit) -> float:
    """Convert torque between supported units.

    Args:
        value: Torque value to convert.
        from_unit: Source torque unit.
        to_unit: Target torque unit.

    Returns:
        Converted torque value.
    """
    if from_unit == to_unit:
        return value
    # Convert to canonical (N·m), then to target
    newton_meters = value * TORQUE_TO_NEWTON_METERS[from_unit]
    return newton_meters / TORQUE_TO_NEWTON_METERS[to_unit]


def force_from_newtons(newtons: float, to_unit: ForceUnit) -> float:
    """Convert force from Newtons to the specified unit.

    Args:
        newtons: Force value in Newtons.
        to_unit: Target force unit.

    Returns:
        Converted force value.
    """
    return newtons / FORCE_TO_NEWTONS[to_unit]


def force_to_newtons(value: float, from_unit: ForceUnit) -> float:
    """Convert force to Newtons from the specified unit.

    Args:
        value: Force value in source unit.
        from_unit: Source force unit.

    Returns:
        Force value in Newtons.
    """
    return value * FORCE_TO_NEWTONS[from_unit]


def torque_from_newton_meters(newton_meters: float, to_unit: TorqueUnit) -> float:
    """Convert torque from Newton-meters to the specified unit.

    Args:
        newton_meters: Torque value in Newton-meters.
        to_unit: Target torque unit.

    Returns:
        Converted torque value.
    """
    return newton_meters / TORQUE_TO_NEWTON_METERS[to_unit]


def torque_to_newton_meters(value: float, from_unit: TorqueUnit) -> float:
    """Convert torque to Newton-meters from the specified unit.

    Args:
        value: Torque value in source unit.
        from_unit: Source torque unit.

    Returns:
        Torque value in Newton-meters.
    """
    return value * TORQUE_TO_NEWTON_METERS[from_unit]


class SensorUnitCode(Enum):
    """Sensor unit codes from calibration data (Section 15.2)."""

    # Force unit codes
    FORCE_LBF = 1
    FORCE_N = 2
    FORCE_KGF = 5

    # Torque unit codes
    TORQUE_LBF_IN = 1
    TORQUE_LBF_FT = 2
    TORQUE_NM = 3
    TORQUE_NMM = 4


def force_unit_from_sensor_code(code: int) -> ForceUnit:
    """Convert sensor force unit code to ForceUnit enum.

    Args:
        code: Sensor force unit code (1=lbf, 2=N, 5=kgf).

    Returns:
        Corresponding ForceUnit.

    Raises:
        ValueError: If code is not recognized.
    """
    mapping = {
        1: ForceUnit.lbf,
        2: ForceUnit.N,
        5: ForceUnit.kgf,
    }
    if code not in mapping:
        raise ValueError(f"Unknown force unit code: {code}")
    return mapping[code]


def torque_unit_from_sensor_code(code: int) -> TorqueUnit:
    """Convert sensor torque unit code to TorqueUnit enum.

    Args:
        code: Sensor torque unit code (1=lbf-in, 2=lbf-ft, 3=N-m, 4=N-mm).

    Returns:
        Corresponding TorqueUnit.

    Raises:
        ValueError: If code is not recognized.
    """
    mapping = {
        1: TorqueUnit.lbf_in,
        2: TorqueUnit.lbf_ft,
        3: TorqueUnit.Nm,
        4: TorqueUnit.Nmm,
    }
    if code not in mapping:
        raise ValueError(f"Unknown torque unit code: {code}")
    return mapping[code]
