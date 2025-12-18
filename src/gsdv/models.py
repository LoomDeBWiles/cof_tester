"""Core data models for sensor data and calibration."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class SampleRecord:
    """A single force/torque sample from the sensor.

    Raw data from UDP RDT streaming protocol. Contains raw counts and optional
    converted engineering units.

    Attributes:
        t_monotonic_ns: Monotonic timestamp in nanoseconds when sample was received.
        rdt_sequence: RDT packet sequence number for detecting packet loss.
        ft_sequence: Internal sensor sample sequence number.
        status: Sensor status code.
        counts: Raw counts in fixed order [Fx, Fy, Fz, Tx, Ty, Tz].
        force_N: Optional converted force values in Newtons [Fx, Fy, Fz].
        torque_Nm: Optional converted torque values in Newton-meters [Tx, Ty, Tz].
    """

    t_monotonic_ns: int
    rdt_sequence: int
    ft_sequence: int
    status: int
    counts: tuple[int, int, int, int, int, int]
    force_N: Optional[tuple[float, float, float]] = None
    torque_Nm: Optional[tuple[float, float, float]] = None

    def __post_init__(self) -> None:
        if len(self.counts) != 6:
            raise ValueError(f"counts must have exactly 6 elements, got {len(self.counts)}")
        if self.force_N is not None and len(self.force_N) != 3:
            raise ValueError(f"force_N must have exactly 3 elements, got {len(self.force_N)}")
        if self.torque_Nm is not None and len(self.torque_Nm) != 3:
            raise ValueError(f"torque_Nm must have exactly 3 elements, got {len(self.torque_Nm)}")

    def counts_as_array(self) -> NDArray[np.int32]:
        """Return counts as a numpy array for calculations."""
        return np.array(self.counts, dtype=np.int32)


@dataclass(frozen=True, slots=True)
class CalibrationInfo:
    """Calibration data from the sensor.

    Retrieved via HTTP (/netftapi2.xml) or TCP command interface.

    Attributes:
        counts_per_force: Calibration factor for converting force counts to Newtons.
        counts_per_torque: Calibration factor for converting torque counts to Newton-meters.
        serial_number: Optional sensor serial number.
        firmware_version: Optional sensor firmware version.
        force_units_code: Optional force unit code from sensor (1=lbf, 2=N, 5=kgf).
        torque_units_code: Optional torque unit code from sensor (1=lbf-in, 2=lbf-ft, 3=N-m, 4=N-mm).
    """

    counts_per_force: float
    counts_per_torque: float
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    force_units_code: Optional[int] = None
    torque_units_code: Optional[int] = None

    def __post_init__(self) -> None:
        if self.counts_per_force <= 0:
            raise ValueError(f"counts_per_force must be positive, got {self.counts_per_force}")
        if self.counts_per_torque <= 0:
            raise ValueError(f"counts_per_torque must be positive, got {self.counts_per_torque}")

    def convert_counts_to_si(
        self, counts: tuple[int, int, int, int, int, int] | NDArray[np.int32]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Convert raw counts to SI units (N and N-m).

        Args:
            counts: 6 raw count values [Fx, Fy, Fz, Tx, Ty, Tz] as tuple or array.

        Returns:
            Tuple of (force_N, torque_Nm) arrays each with 3 elements.
        """
        arr = np.array(counts, dtype=np.float64) if not isinstance(counts, np.ndarray) else counts.astype(np.float64)
        force_N = arr[:3] / self.counts_per_force
        torque_Nm = arr[3:] / self.counts_per_torque
        return force_N, torque_Nm
