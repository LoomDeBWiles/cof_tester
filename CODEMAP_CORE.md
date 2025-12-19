# Codemap: Core Models & Entry Point

> Fundamental data structures, error handling, and application entry.

## Key Files

| File | Responsibility |
|------|----------------|
| `src/gsdv/models.py` | SampleRecord, CalibrationInfo dataclasses |
| `src/gsdv/errors.py` | Error hierarchy with recovery actions |
| `src/gsdv/main.py` | Application entry point (CLI/GUI dispatch) |

## Data Models

### SampleRecord
```python
@dataclass(frozen=True, slots=True)
class SampleRecord:
    t_monotonic_ns: int           # When received (nanoseconds)
    rdt_sequence: int             # Packet sequence (detect loss)
    ft_sequence: int              # Sensor internal sequence
    status: int                   # Sensor status code
    counts: tuple[int, ...]       # [Fx, Fy, Fz, Tx, Ty, Tz] raw
    force_N: Optional[tuple]      # [Fx, Fy, Fz] in Newtons
    torque_Nm: Optional[tuple]    # [Tx, Ty, Tz] in Newton-meters
```

### CalibrationInfo
```python
@dataclass(frozen=True, slots=True)
class CalibrationInfo:
    counts_per_force: float       # CPF for N conversion
    counts_per_torque: float      # CPT for N-m conversion
    serial_number: Optional[str]
    firmware_version: Optional[str]
    force_units_code: Optional[int]   # 1=lbf, 2=N, 5=kgf
    torque_units_code: Optional[int]  # 1=lbf-in, 2=lbf-ft, 3=N-m, 4=N-mm

    def convert_counts_to_si(counts) -> (force_N, torque_Nm)
```

## Error Hierarchy

```
GsdvError (base)
├── NetworkError (NET)
│   ├── SensorConnectionRefused    NET-001
│   ├── SensorConnectionTimeout    NET-002
│   ├── NetworkDisconnectError     NET-003
│   └── SocketError                NET-004
├── ProtocolError (PROTO)
│   ├── MalformedPacketError       PROTO-001
│   ├── InvalidHeaderError         PROTO-002
│   ├── PacketParseError           PROTO-003
│   └── SequenceGapError           PROTO-004
├── CalibrationError (CAL)
│   ├── HttpCalibrationError       CAL-001
│   ├── TcpCalibrationError        CAL-002
│   ├── CalibrationParseError      CAL-003
│   ├── CalibrationUnavailableError CAL-004
│   └── BiasError                  CAL-005
└── IoError (IO)
    ├── DirectoryNotWritableError  IO-001
    ├── DiskFullError              IO-002
    ├── LogRotationError           IO-003
    ├── FileWriteError             IO-004
    └── FileCloseError             IO-005
```

## Recovery Actions

| Action | When Used |
|--------|-----------|
| `RETRY` | Transient failures (timeout) |
| `RECONNECT` | Connection lost |
| `FALLBACK` | HTTP failed, try TCP |
| `CHOOSE_DIRECTORY` | I/O errors |
| `MANUAL` | Unrecoverable |

## Entry Point (main.py)

```
gsdv [command]
      │
      ├── (no args) → GUI with full functionality:
      │               ├── Connection management
      │               ├── Real-time plotting (with decimation)
      │               ├── Recording to CSV via AsyncFileWriter
      │               └── Bias/tare operations
      │
      └── (with args) → CLI dispatch to diagnostics/cli.py
```

## GUI Data Flow (main.py)

```
on_connect_requested(ip)
         ↓
    get_calibration_with_fallback(ip)
         ↓
    AcquisitionEngine(ip, decimation_factor=preferences.decimation_factor)
         ↓
    set_sample_callback(on_sample)  ──→  AsyncFileWriter.write() [if recording]
         ↓
    plot_area.set_buffer(engine.buffer)
         ↓
    engine.start()
```

## Conversion Flow

```
SampleRecord.counts (raw int32)
           ↓
CalibrationInfo.convert_counts_to_si()
           ↓
    force_N = counts[:3] / cpf
    torque_Nm = counts[3:] / cpt
           ↓
(force_N, torque_Nm) as numpy arrays
```
