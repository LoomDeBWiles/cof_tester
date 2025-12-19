# GSDV - Gamma Sensor Data Viewer

Real-time data acquisition, visualization, and logging for ATI Gamma series 6-axis force/torque sensors.

## Features

- Real-time visualization of all six F/T channels (Fx, Fy, Fz, Tx, Ty, Tz)
- High-frequency data logging (1000 Hz) with CSV/TSV/Excel export
- Multi-channel plotting with configurable time windows (1s to 7 days)
- Unit conversion (N, lbf, kgf for force; N·m, N·mm, lbf·in, lbf·ft for torque)
- Device bias/tare support
- Tool transform configuration
- Dark/light theme support
- Sensor simulator for testing without hardware

## Prerequisites

- **Python 3.11 or later** (3.12+ recommended)
- **Network access** to your ATI Gamma sensor (same LAN or routable IP)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/LoomDeBWiles/cof_tester.git
cd cof_tester
```

### 2. Install dependencies

**Option A: Using uv (recommended)**

[uv](https://github.com/astral-sh/uv) is a fast Python package manager.

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install dependencies
uv sync --all-extras
```

**Option B: Using pip**

```bash
# Create virtual environment
python -m venv .venv

# Activate it
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

# Install package with dev dependencies
pip install -e ".[dev]"
```

### 3. Platform-specific notes

#### macOS
Works out of the box. No additional dependencies needed.

#### Windows
Works out of the box. If you see Qt platform plugin errors, ensure you're using Python from python.org (not Windows Store).

#### Linux (Ubuntu/Debian)
You may need Qt platform dependencies:

```bash
sudo apt-get update
sudo apt-get install -y libxcb-xinerama0 libxcb-cursor0 libegl1 libgl1
```

For headless servers (CLI only, no GUI):
```bash
export QT_QPA_PLATFORM=offscreen
```

## Network Configuration

The sensor must be reachable from the machine running GSDV:

| Port | Protocol | Purpose |
|------|----------|---------|
| 49152 | UDP | Real-time data streaming (RDT) |
| 49151 | TCP | Command interface |
| 80 | HTTP | Calibration info (netftapi2.xml) |

**Typical setup:**
1. Connect sensor to your lab network via Ethernet
2. Configure sensor IP via ATI's web interface (default: 192.168.1.1)
3. Ensure your computer is on the same subnet or has a route to the sensor

**Firewall:** Allow inbound UDP on port 49152 if your OS firewall is enabled.

## Usage

### GUI (default)

```bash
# Activate venv first if using pip installation
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

# Launch GUI
gsdv
```

### CLI Commands

```bash
# Discover sensors on local network
gsdv discover --subnet 192.168.1.0/24

# Stream live data to console
gsdv stream --ip 192.168.1.100 --seconds 10

# Log data to files with rotation
gsdv log --ip 192.168.1.100 --out ./data --rotate-size 100MB

# Run sensor simulator for testing without hardware
gsdv simulate-sensor --rate 1000
```

### Testing without hardware

Run the simulator in one terminal:
```bash
gsdv simulate-sensor
```

Then connect to localhost in another terminal or the GUI:
```bash
gsdv stream --ip 127.0.0.1
```

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=src/gsdv

# Run linter
ruff check src tests

# Type checking
mypy src
```

## Troubleshooting

### "Connection refused" when connecting to sensor
- Verify sensor IP is correct: `ping <sensor-ip>`
- Check sensor is powered on and network cable connected
- Ensure no firewall blocking ports 49151, 49152, 80

### "No sensors found" during discovery
- Discovery only works on the local subnet
- Try specifying the subnet explicitly: `gsdv discover --subnet 10.0.0.0/24`
- Some networks block broadcast/multicast traffic

### GUI doesn't start on Linux
Install Qt dependencies:
```bash
sudo apt-get install libxcb-xinerama0 libxcb-cursor0 libegl1 libgl1
```

### High packet loss shown in status bar
- Check network quality between computer and sensor
- Reduce other network traffic on the same interface
- Use a dedicated Ethernet connection (not WiFi)

### "Module not found" errors
Ensure you've activated the virtual environment:
```bash
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows
```

## Target Hardware

ATI Gamma Series Force/Torque Sensor with Net F/T interface (NETrs)

- Sensor communication via UDP (RDT protocol) at 1000 Hz
- Calibration retrieval via HTTP or TCP
- Supports device-level and software bias/tare

## Project Structure

```
src/gsdv/
├── main.py              # Entry point (CLI/GUI dispatch)
├── models.py            # SampleRecord, CalibrationInfo
├── errors.py            # Error hierarchy with recovery actions
├── acquisition/         # Network layer, RDT client
├── protocols/           # RDT, TCP, HTTP protocol handlers
├── processing/          # Filtering, decimation, unit conversion
├── logging/             # Async file writer with rotation
├── ui/                  # PySide6 GUI components
├── plot/                # pyqtgraph real-time plotting
├── config/              # User preferences
└── diagnostics/         # CLI commands, sensor simulator
```

See `CODEMAP_*.md` files for detailed architectural documentation.

## License

MIT
