# Codemap: Diagnostics & CLI

> Command-line tools for sensor discovery, streaming, logging, and simulation.

## Key Files

| File | Responsibility |
|------|----------------|
| `src/gsdv/diagnostics/cli.py` | CLI entry point with subcommands |
| `src/gsdv/diagnostics/sensor_simulator.py` | Fake sensor for testing |

## CLI Commands

```
gsdv discover [--subnet 192.168.1.0/24] [--timeout 0.5]
    Scan subnet for ATI sensors via HTTP /netftapi2.xml probing.

gsdv stream --ip <sensor-ip> [--seconds N]
    Stream live data to console with sequence numbers and sample rate.

gsdv log --ip <sensor-ip> --out <dir> [--format csv|tsv|excel_compatible]
         [--prefix PREFIX] [--rotate-size 2GB] [--rotate-time 1h]
    Log data to file with optional rotation.

gsdv simulate-sensor [--rate 1000] [--loss 0.0] [--reorder 0.0]
    Run fake sensor for testing without hardware.
```

## Sensor Simulator Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ SensorSimulator                                             │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│ │ UDP Thread  │  │ TCP Thread  │  │ HTTP Thread         │   │
│ │ port 49152  │  │ port 49151  │  │ port 8080           │   │
│ │             │  │             │  │                     │   │
│ │ RDT packets │  │ READCALINFO │  │ GET /netftapi2.xml  │   │
│ │ @ 1000 Hz   │  │ WRITETRANSFORM│ │                     │   │
│ └──────┬──────┘  │ READFT bias │  └─────────────────────┘   │
│        │         └─────────────┘                            │
│        ↓                                                    │
│ ┌──────────────┐                                            │
│ │ Streaming    │ ← _generate_sample() → sinusoidal + noise  │
│ │ Thread       │ ← FaultConfig → loss, reorder, burst,      │
│ │              │                  disconnect injection      │
│ └──────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

## Fault Injection (FaultConfig)

| Fault | Description |
|-------|-------------|
| `loss_probability` | Drop packets randomly |
| `reorder_probability` | Delay packets to arrive out-of-order |
| `burst_loss_probability` | Drop N consecutive packets |
| `disconnect_probability` | Pause streaming temporarily |

## Data Flow: CLI Log Command

```
cmd_log(args)
       ↓
get_calibration_with_fallback(ip)  → CalibrationInfo
       ↓
RdtClient(ip).receive_samples()    → SampleRecord iterator
       ↓
AsyncFileWriter.write((timestamp, sample))
       ↓
[writer thread formats and flushes to disk]
```

## Usage Examples

```bash
# Discover sensors on lab network
gsdv discover --subnet 10.0.0.0/24

# Stream for 10 seconds
gsdv stream --ip 192.168.1.100 --seconds 10

# Log with rotation
gsdv log --ip 192.168.1.100 --out ./data --rotate-size 100MB

# Test without hardware
gsdv simulate-sensor --rate 1000 --loss 0.01
```
