# Codemap: Network Protocols

> UDP/TCP/HTTP communication with ATI Gamma F/T sensors.

## Key Files

| File | Responsibility |
|------|----------------|
| `src/gsdv/protocols/rdt_udp.py` | UDP RDT streaming (1000Hz real-time data) |
| `src/gsdv/protocols/http_calibration.py` | HTTP GET calibration from /netftapi2.xml |
| `src/gsdv/protocols/tcp_cmd.py` | TCP port 49151 commands (bias, transform) |
| `src/gsdv/protocols/discovery.py` | Subnet scanning for sensor discovery |

## Data Flow

```
Sensor (ATI NETrs)
       ↓
┌──────┴──────┐
│ UDP 49152   │ ← RdtClient.receive_samples() → SampleRecord iterator
│ (RDT 1000Hz)│   36-byte packets: seq, status, 6×int32 counts
└─────────────┘

┌──────┴──────┐
│ HTTP 80     │ ← HttpCalibrationClient.get_calibration()
│ /netftapi2  │   XML → CalibrationInfo
└─────────────┘
       ↓ [fallback if HTTP fails]
┌──────┴──────┐
│ TCP 49151   │ ← TcpCommandClient
│ Commands    │   READCALINFO, WRITETRANSFORM, READFT
└─────────────┘
```

## Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `RdtClient` | `rdt_udp.py:30` | UDP streaming, packet parsing, loss detection |
| `HttpCalibrationClient` | `http_calibration.py:25` | Raw socket HTTP, XML parsing |
| `TcpCommandClient` | `tcp_cmd.py:40` | Command/response protocol |
| `DiscoverySensor` | `discovery.py:35` | Concurrent subnet scan |

## Packet Formats

**RDT Response (36 bytes)**:
```
bytes 0-3:   rdt_sequence (uint32 BE)
bytes 4-7:   ft_sequence (uint32 BE)
bytes 8-11:  status (uint32 BE)
bytes 12-35: counts[6] (int32 BE) → Fx, Fy, Fz, Tx, Ty, Tz
```

**TCP Commands**:
```
READCALINFO\r\n → CPF=xxx;CPT=yyy;Serial=...
WRITETRANSFORM dx dy dz rx ry rz\r\n → OK\r\n
READFT\r\n → Fx Fy Fz Tx Ty Tz\r\n
```

## Patterns

| Pattern | When | Example |
|---------|------|---------|
| Fallback calibration | HTTP fails | `get_calibration_with_fallback(ip)` tries HTTP then TCP |
| Non-blocking recv | Avoid stalls | `socket.settimeout(0.1)` + catch timeout |
| Sequence gap detection | Packet loss | Compare `rdt_sequence` to expected |

## Dependencies

| This Uses | Used By |
|-----------|---------|
| `socket`, `struct` | `AcquisitionEngine` |
| `xml.etree.ElementTree` | `ProcessingEngine` (calibration) |
| `threading` (discovery) | `MainWindow` (connect) |

## Common Tasks

| Task | Solution |
|------|----------|
| Add new command | Add method to `TcpCommandClient`, format as `CMD args\r\n`, parse response |
| Handle new packet field | Update `_parse_response()` in `rdt_udp.py`, extend `SampleRecord` |
| Support new sensor | Add variant parsing in `http_calibration.py` XML handler |

## Gotchas

**HTTP uses raw sockets**: No `requests` library. Uses manual `socket.send(b"GET /netftapi2.xml...")` for minimal dependencies.

**Byte order is big-endian**: All multi-byte fields use `struct.unpack(">I", ...)` (network byte order).

**Discovery timeout**: Subnet scan uses 10s max with concurrent threads. Large subnets (/16) may not complete.

**TCP command newlines**: Commands end with `\r\n`, responses also end with `\r\n`. Strip before parsing.
