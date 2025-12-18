# GSDV - Gamma Sensor Data Viewer

Real-time data acquisition, visualization, and logging for ATI Gamma series 6-axis force/torque sensors.

## Features

- Real-time visualization of all six F/T channels (Fx, Fy, Fz, Tx, Ty, Tz)
- High-frequency data logging (1000 Hz) with CSV/TSV/Excel export
- Multi-channel plotting with configurable time windows
- Unit conversion (N, lbf, kgf for force; N·m, N·mm, lbf·in, lbf·ft for torque)
- Device bias/tare support
- Tool transform configuration
- Dark/light theme support

## Installation

```bash
# Using uv
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"
```

## Usage

```bash
# Launch GUI
gsdv

# CLI commands
gsdv discover                    # Discover sensors on local network
gsdv stream --ip <ip>            # Stream data from sensor
gsdv log --ip <ip> --out <dir>   # Log data to file
gsdv simulate-sensor             # Run sensor simulator for testing
```

## Development

```bash
# Run tests
pytest

# Run linter
ruff check src tests

# Type checking
mypy src
```

## Target Hardware

ATI Gamma Series Force/Torque Sensor (NETrs)

## License

MIT
