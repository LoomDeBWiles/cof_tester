Version 1.1 below updates the original v1.0 draft plan  and incorporates the provided open-question answers and protocol byte layouts. 

---

# Gamma Sensor Data Viewer Application

**Version:** 1.1 (December 2025)
**Status:** Ready to Execute
**Document Owner:** Sparta Biomedical
**Target Hardware:** ATI Gamma Series Force/Torque Sensor (NETrs)

---

## 0 Change Log (v1.1 vs v1.0)

1. **Open questions resolved**

   * Discovery method chosen for v1.
   * Calibration XML schema fields confirmed and parsing strategy documented.
   * Default streaming rate defined explicitly as 1000 Hz (NETrs default).
   * Tool transform decision made: on-device via WRITETRANSFORM.
   * Excel-compatible export definition locked.

2. **Added Binary Protocol Appendix**

   * Exact UDP RDT request and response layouts with offsets, sizes, endianness, and hex examples.
   * Exact TCP calibration request and response layouts.
   * Bias command options (UDP primary, TCP fallback).
   * Tool transform command layout.

3. **Plot library specified**

   * **pyqtgraph** selected for real-time plotting performance in Qt.

4. **Concrete ring buffer sizing**

   * Raw ring and multi-resolution tiers defined with memory estimates.

5. **Preferences file defined**

   * JSON file format.
   * Platform-specific config directories via `platformdirs`.
   * Atomic writes required.

6. **Minor execution polish added**

   * Keyboard shortcuts defined.
   * Log rotation policy defined.
   * Sensor simulator scope specified as both standalone and test fixture.

---

## 1 Executive Summary

### 1.1 Product Overview

This plan defines requirements for a desktop application that provides real-time data acquisition, visualization, and logging for the ATI Gamma series 6-axis force/torque sensor. It is intended to be a functionally equivalent alternative to ATI’s proprietary Data Viewer, with enhanced multi-channel plotting and a modern, intuitive user interface aligned with 2025 design principles.

The primary differentiator is support for simultaneous logging and visualization of all six force/torque channels (Fx, Fy, Fz, Tx, Ty, Tz) rather than limiting the user to single-axis viewing, with a streamlined workflow for selecting output directories and configuring export formats.

### 1.2 Primary Users

* Researchers running experiments and collecting force/torque time-series data
* Engineers and technicians performing high-frequency testing (for example, friction testing workflows)

### 1.3 Primary Workflows

1. **Connect to a sensor**

   * Enter sensor IP (static or DHCP-assigned) or use discovery
   * Click Connect
   * Confirm Connected status and view sensor info (serial, calibration, firmware)
2. **Configure viewing and units**

   * Enable any combination of Fx, Fy, Fz, Tx, Ty, Tz
   * Choose force units (N, lbf, kgf) and torque units (N·m, N·mm, lbf·in, lbf·ft)
   * Adjust time window and Y-axis scaling
3. **Run real-time visualization**

   * View multi-trace time-series plot with legend and optional grid and crosshair
   * Monitor real-time numeric readout for active channels
4. **Record data**

   * Pick output directory
   * Confirm filename preview (timestamped, optional prefix)
   * Start and stop recording and monitor duration and file size

---

## 2 Problem Statement and Background

### 2.1 Problem Statement

The existing ATI F/T Data Viewer provides basic functionality but lacks multi-channel visualization, modern UI design patterns, and flexible export options. Researchers and engineers require an application that can simultaneously plot multiple force/torque axes while logging high-frequency data to user-specified directories.

### 2.2 Background

The ATI NETrs F/T system supports multiple protocols; this v1 application targets UDP RDT and TCP and HTTP interfaces for maximum throughput and simplicity.

Key reference characteristics:

* 6-axis measurement: Fx, Fy, Fz (force) and Tx, Ty, Tz (torque)
* RDT streaming via UDP port 49152
* TCP command interface on port 49151
* HTTP calibration interface (preferred): port 80, GET `/netftapi2.xml` returns calibration fields
* Configurable software filtering (0.7 Hz to 120 Hz cutoff)

### 2.3 Terminology

* F/T: Force/Torque
* Channels: Fx, Fy, Fz (force) and Tx, Ty, Tz (torque)
* RDT: Raw Data Transfer streaming protocol over UDP
* cpf / cpt: calibration factors counts_per_force and counts_per_torque used to convert counts to engineering units
* Bias / Tare: command to zero the sensor output offset (device bias) or an application-level soft zero
* rdt_sequence / ft_sequence: sequence numbers used to detect packet loss and sample continuity

---

## 3 Goals and Scope

### 3.1 Goals

1. Provide real-time visualization of any combination of the six F/T channels
2. Enable high-frequency data logging with user-selectable output directory
3. Deliver a clean, intuitive interface requiring minimal training
4. Maintain full compatibility with ATI NETrs communication protocols used in v1 (UDP RDT, TCP, HTTP)

### 3.2 Non-Goals

Explicitly out of scope for v1.1:

* Industrial protocol support (EtherNet/IP, PROFINET, DeviceNet, CAN)
* Serial/RS422/RS485 communication
* IMU data visualization (accelerometer, gyroscope)
* Monitor conditions and threshold alerting
* Multi-sensor simultaneous acquisition
* Post-acquisition data analysis tools

### 3.3 Success Metrics

* User can connect and begin viewing data within 30 seconds of launch
* Zero data loss at sustained 1000 Hz streaming rates
* Plot update latency under 50 ms
* File I/O throughput supports full-rate logging without dropped samples
* Plot refresh rate at least 30 fps
* Memory footprint under 200 MB during normal operation
* Startup time under 3 seconds

### 3.4 Scope

This plan covers the v1 desktop application including:

* Connection management (static IP, DHCP address entry, sensor discovery) and status display
* Streaming acquisition of all six channels, bias (tare), calibration-based conversion, and unit selection
* Multi-channel real-time visualization and numeric readouts
* Data logging to user-selected directories with timestamped filenames and CSV, TSV, Excel-compatible export
* Preference persistence, filtering controls, tool transform input, and theme toggle
* Cross-platform targets: macOS 12+ (primary), Windows 10/11 and Ubuntu 22.04+ (secondary)

### 3.5 Development Milestones

| Phase | Deliverables                                   | Exit Criteria (v1 minimum)                                                                                                               |
| ----- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| M1    | Protocol layer: UDP/TCP/HTTP + CLI + simulator | CLI prints continuous Fx..Tz with sequence numbers and measured sample rate; confirms packet parsing, endian correctness, and start/stop |
| M2    | UI shell with connection panel + plot          | User can connect and see live data plotted                                                                                               |
| M3    | Multi-channel plot with toggles                | All 6 channels can be displayed simultaneously; toggles stable                                                                           |
| M4    | Logging with folder selection + CSV            | Record start/stop works; CSV written with metadata; no dropped samples at 1000 Hz                                                        |
| M5    | Settings persistence, units, bias, transform   | Preferences persist; unit conversions validated; bias modes validated; tool transform sent via TCP                                       |
| M6    | Polish + perf + tests                          | Meets success metrics; release candidate builds                                                                                          |

### 3.6 Top Risks and Mitigations

* High-frequency logging causing dropped samples: dedicated file-writer thread, buffered writes, backpressure indicators; never block the UDP receive loop
* Discovery variability: best-effort discovery plus direct IP entry always supported; visible rescan and subnet targeting
* Long time-window plotting vs memory budget: bounded ring buffer plus multi-resolution downsampling tiers; pyqtgraph for real-time rendering

---

## 4 Users and Use Cases

### 4.1 Users

* Researcher: needs high-frequency logging, fast setup, and multi-channel plots for experiments
* Test engineer/technician: needs reliable connect/reconnect behavior, directory selection, and quick sanity checks via numeric readouts

### 4.2 Use Cases and Acceptance Criteria

1. **UC-1: Connect via IP**

   * Flow: Enter IP → Connect → status becomes Connected with populated sensor info
   * Acceptance:

     * Clear connected/disconnected/error status
     * Sensor identity displayed after connect
     * Viewing live data within 30 seconds

2. **UC-2: Discover sensor on local network**

   * Flow: Discover/Scan → list found sensors → select → connect
   * Acceptance:

     * Discovery bounded time (target under 10 seconds on a /24)
     * Discovery never blocks UI
     * Includes IP and identity fields when available

3. **UC-3: Stream and visualize multi-channel data**

   * Flow: Start/confirm streaming → toggle channels → view plot and numeric readouts
   * Acceptance:

     * Plot any combination of channels on one chart
     * Plot refresh at least 30 fps; update latency under 50 ms

4. **UC-4: Apply bias (tare)**

   * Flow: Click Bias/Tare → values re-zero
   * Acceptance:

     * Applies to all six channels consistently
     * Visible confirmation in UI
     * Supports two modes:

       * Device tare (default)
       * Soft zero (fallback or optional)

5. **UC-5: Configure units**

   * Flow: Select force units and torque units
   * Acceptance:

     * Force: N, lbf, kgf
     * Torque: N·m, N·mm, lbf·in, lbf·ft
     * UI and logs label units clearly

6. **UC-6: Record high-frequency data**

   * Flow: Select folder → Start recording → Stop → inspect output file
   * Acceptance:

     * One-click record start/stop with indicator
     * Timestamped filename with optional prefix
     * Formats: CSV (primary), TSV, Excel-compatible CSV
     * No dropped samples at sustained 1000 Hz while logging
     * Log rotation supported for very long sessions

7. **UC-7: Persistent settings and theme**

   * Flow: Change settings → quit → relaunch
   * Acceptance:

     * Preferences persist (last IP, output directory, channel selections, theme)
     * Stored in OS user config directory

8. **UC-8: Handle disconnection**

   * Flow: Disconnect occurs → app indicates issue → optional reconnect
   * Acceptance:

     * Graceful handling; optional auto-reconnect
     * Sequence-number monitoring detects packet loss and logs warnings

---

## 5 System Overview

Processing pipeline:

1. Receive raw counts from sensor
2. Apply bias handling:

   * Device tare sets sensor internal bias
   * Optional soft zero subtracts app-level offsets
3. Convert to engineering units using cpf/cpt
4. Apply optional digital filter
5. Route to visualization buffers and file writer
6. Decimate for display if sample rate exceeds plot refresh rate

Major system components:

* UI (main window, plot area, numeric readouts, settings)
* Plotting layer (pyqtgraph)
* Network/protocol layer (UDP RDT streaming, TCP commands, HTTP calibration)
* Acquisition engine (packet receive, sequencing, buffering)
* Processing engine (conversion, optional filter, optional soft zero)
* Visualization model (multi-resolution buffer for time-window display)
* Logger (async buffered writer, metadata header, rotation)
* Preferences storage (JSON via platformdirs)

---

## 6 Functional Requirements

### 6.1 Connection Management

* **FR-1 (IP Connection):** MUST support connection via static IP or DHCP-assigned address
* **FR-2 (Discovery):** SHOULD auto-detect sensor on local network (user-initiated)
* **FR-3 (Connection Status):** MUST display connection status clearly
* **FR-4 (Sensor Identity):** MUST retrieve and display serial, calibration info, firmware version when available
* **FR-5 (Protocol Support):** MUST support UDP (RDT) and TCP; SHOULD use HTTP for calibration when available

### 6.2 Data Acquisition

* **FR-6 (Multi-Channel Stream):** MUST stream all six channels simultaneously
* **FR-7 (Streaming Rate):** MUST sustain **1000 Hz** streaming (NETrs default) and display measured sample rate; SHOULD tolerate other rates
* **FR-8 (Bias/Tare):** MUST support bias with:

  * Default: device tare command
  * Fallback/optional: soft zero mode
* **FR-9 (Calibration Conversion):** MUST convert counts to engineering units using cpf/cpt
* **FR-10 (Force Units):** MUST support N, lbf, kgf
* **FR-11 (Torque Units):** MUST support N·m, N·mm, lbf·in, lbf·ft

### 6.3 Real-Time Visualization

* **FR-12 (Combined Plot):** MUST plot any combination of channels on a single chart
* **FR-13 (Channel Toggles):** MUST provide per-channel enable/disable controls
* **FR-14 (Axis Scaling):** MUST autoscale Y; SHOULD allow manual range
* **FR-15 (Time Window):** MUST provide time window control from 1 second to 7 days
* **FR-16 (Numeric Readouts):** MUST display real-time numeric readout for active channels
* **FR-17 (Inspection Tools):** SHOULD include legend, grid option, crosshair option

### 6.4 Data Logging

* **FR-18 (Record Control):** MUST provide one-click record start/stop with indicator
* **FR-19 (Output Directory):** MUST provide folder picker
* **FR-20 (File Naming):** MUST generate timestamped filenames; SHOULD support optional prefix
* **FR-21 (Export Formats):** MUST support CSV, TSV, and Excel-compatible CSV (see Section 16.3)
* **FR-22 (Metadata Header):** MUST include channel names, units, cpf/cpt, identity fields when available
* **FR-23 (Telemetry):** SHOULD display duration and file size during capture
* **FR-24 (Optional Log Decimation):** MAY support decimation for reduced file sizes
* **FR-29 (Log Rotation):** MUST support automatic file splitting by time and/or size for long recordings

### 6.5 Configuration and Settings

* **FR-25 (Preferences Persistence):** MUST persist key user preferences
* **FR-26 (Filter Cutoff):** MUST provide configurable filter cutoff
* **FR-27 (Tool Transform):** MUST support tool transform input and apply via on-device WRITETRANSFORM
* **FR-28 (Theme Toggle):** MUST support dark/light theme
* **FR-30 (Keyboard Shortcuts):** MUST implement core shortcuts (see Section 8.4)
* **FR-31 (Preferences Format and Location):** MUST store preferences as JSON in OS user config directory using platformdirs, with atomic writes

---

## 7 Functional Rules and Logic

### 7.1 Core Logic

* **BL-1 Counts to engineering units**

  * Force_N = Force_counts / counts_per_force (cpf)
  * Torque_Nm = Torque_counts / counts_per_torque (cpt)
  * Canonical internal units: Force in N, Torque in N·m; convert for display and logging per settings

* **BL-2 Unit conversions**

  * Force:

    * N base
    * lbf = N / 4.4482216152605
    * kgf = N / 9.80665
  * Torque:

    * N·m base
    * N·mm = N·m * 1000
    * lbf·in = N·m / (4.4482216152605 * 0.0254)
    * lbf·ft = N·m / (4.4482216152605 * 0.3048)

* **BL-3 Bias behavior**

  * Default: Device tare (bias) is issued to the sensor.
  * Optional: Soft zero stores current raw counts as offsets per channel and subtracts from subsequent samples.
  * If device tare fails (network or protocol), the UI MUST surface failure and the app SHOULD offer soft zero as fallback.

* **BL-4 Filtering**

  * Optional and controlled by cutoff frequency
  * Supported cutoff range includes 0.7 Hz to 120 Hz
  * Filter must be stable for streaming; recommended: 2nd-order IIR low-pass (Butterworth)

* **BL-5 Plot decimation and time window**

  * Display decimates when sample rate exceeds plot refresh rate, while logger remains full-rate
  * Visualization uses bounded ring buffer plus multi-resolution tiers to support up to 7 days without exceeding memory budget

* **BL-6 Packet loss monitoring**

  * Monitor rdt_sequence gaps, increment packet-loss counter
  * UI shows warning; logs record packet loss events

* **BL-7 Recording telemetry**

  * Duration derived from first and last sample timestamps plus wall clock for UI
  * File size estimated during capture and corrected upon close

### 7.2 State Transitions

* Connection lifecycle: DISCONNECTED → DISCOVERING (optional) → CONNECTING → CONNECTED → STREAMING
* Recording is orthogonal: RECORDING may be active while STREAMING
* Rules:

  * Streaming must not start unless connected
  * Recording must not start unless streaming is active (or streaming can be auto-started as part of record)
  * On network error, transition to ERROR with actionable message; allow retry and optional auto-reconnect

### 7.3 Validation Rules

* IP input validates IPv4 (optionally IPv6); invalid disables Connect
* Output directory must be writable; otherwise Record disabled with inline error
* Filename prefix must be filesystem-safe; invalid chars rejected or sanitized
* Tool transform inputs numeric; empty defaults to 0

---

## 8 UI and UX Specification

### 8.1 Global Navigation

Single main window:

* Header bar (title, connection status, settings icon)
* Connection panel
* Channel selector
* Plot area
* Numeric display
* Recording controls
* Status bar

### 8.2 Key Views

**Main Window**

* Connection: IP input, Connect button, sensor info
* Channels: six toggles for Fx..Tz
* Plot: multi-trace plot, legend, axis labels, time window control
* Numeric: real-time readouts for enabled channels
* Recording: record/stop, folder picker, filename preview, duration, file size
* Status: sample rate, buffer status, packet loss counters, warnings

**Settings Dialog**

* Connection options: timeouts, auto-reconnect, discovery subnets
* Filtering: enable/disable, cutoff frequency
* Units: force and torque
* Bias: mode selection (device tare default, soft zero optional)
* Tool transform: Dx, Dy, Dz, Rx, Ry, Rz (sent via TCP WRITETRANSFORM)
* Theme: dark/light toggle
* Diagnostics: packet loss, dropped-by-app counter, log paths

### 8.3 Micro Interactions

* Connect: “Connecting…” then “Connected” with sensor info populated
* Channel toggles: click toggles visibility; enabled state visually distinct
* Recording: Record changes to Stop with clear active indicator
* Folder selection: OS-native picker; selected path displayed with truncation
* Prevent invalid actions via disabled controls and inline validation

### 8.4 Keyboard Shortcuts

Use Ctrl on Windows and Linux, Cmd on macOS:

* Connect: Ctrl+Enter
* Start recording: Ctrl+R
* Stop recording: Ctrl+S
* Bias/Tare: Ctrl+B
* Open Settings: Ctrl+Comma

---

## 9 Non-Functional Requirements

### 9.1 Performance

* Must sustain acquisition without sample loss at 1000 Hz
* Plot refresh at least 30 fps; plot update latency under 50 ms
* Startup under 3 seconds
* Memory under 200 MB during normal operation

### 9.2 Reliability

* Handle disconnect gracefully; offer auto-reconnect
* Preserve file integrity on unexpected closure (flush policy, atomic closes)
* Detect and report packet loss with UI warnings and log entries

### 9.3 Extensibility

* Protocol layer modular to allow future additions without redesign

### 9.4 Security

* Local operation only; no cloud dependency
* Never execute received payload as code shows
* Discovery scanning limited to local interfaces and user-initiated

---

## 10 Integration Interfaces

### 10.1 ATI NETrs Sensor Interface

#### UDP RDT Streaming

* Port: 49152
* Request packets: see Appendix 25.3.1 (8 bytes, big-endian)
* Start streaming: command 0x0002, sample_count 0 (infinite)
* Stop streaming: command 0x0000
* Device bias/tare: command 0x0042 (no response, effect visible in subsequent samples)
* Response packets: see Appendix 25.3.2 (36 bytes, big-endian)
* Response ordering: Fx, Fy, Fz, Tx, Ty, Tz as int32 counts

#### TCP Command Interface

* Port: 49151
* Calibration retrieval:

  * Request: READCALINFO 20 bytes (command 0x01 + zeros)
  * Response: 24 bytes, big-endian (includes cpf/cpt and unit codes)
  * Important: calibration request does not include 0x1234 header in the request
* Tool transform:

  * WRITETRANSFORM command 0x02, 20 bytes total (see Appendix 25.3.5)
* Bias fallback:

  * READFT with sysCommands bit0 = 1 (see Appendix 25.3.4)

#### HTTP Calibration Interface (Preferred)

* Port: 80
* GET `/netftapi2.xml`
* XML contains at minimum:

  * counts_per_force
  * counts_per_torque
* App uses HTTP first; falls back to TCP calibration if HTTP fails

### 10.2 Filesystem Interface

* Folder picker uses OS-native dialog; path displayed in UI
* Logger writes CSV/TSV/Excel-compatible CSV to chosen directory
* Log rotation may create multiple sequential files for one session

---

# Technical Requirements

Everything below this line is implementation-oriented TRD content.

---

## 11 Core Components

### 11.1 Component Inventory

| Component                 | Reads                                                   | Writes                                             |
| ------------------------- | ------------------------------------------------------- | -------------------------------------------------- |
| UI (MainWindow, Settings) | Preferences, connection state, plot model, record state | User actions, settings changes                     |
| Plot layer (pyqtgraph)    | PlotModel series                                        | Rendered plot                                      |
| PreferencesStore          | preferences.json                                        | preferences.json (atomic write)                    |
| DiscoveryService          | local NIC subnets                                       | discovered sensor list                             |
| SensorConnectionManager   | UI inputs, discovered list                              | connection state, active endpoints                 |
| UDP RDT Client            | UDP packets                                             | SampleRecord stream                                |
| TCP Command Client        | UI commands                                             | calibration request, tool transform, bias fallback |
| HTTP Calibration Client   | /netftapi2.xml                                          | CalibrationInfo                                    |
| AcquisitionEngine         | SampleRecord stream                                     | raw ring buffer, loss counters                     |
| ProcessingEngine          | raw ring, calibration, settings                         | display tiers, logger queue                        |
| Logger                    | samples                                                 | log files, rotation                                |
| Diagnostics/CLI           | config flags                                            | stdout, capture files                              |
| Sensor simulator          | config flags                                            | UDP/TCP/HTTP endpoints                             |

### 11.2 Technology Stack

* Language: Python 3.11+
* UI: PySide6 (preferred) or PyQt6
* Plotting: **pyqtgraph**
* Numeric: numpy
* Config paths: platformdirs
* Testing: pytest
* Packaging: pyproject.toml + uv/pip tooling

### 11.3 Directory Structure

Recommended layout:

gamma_sensor_data_viewer/

* pyproject.toml
* README.md
* src/gsdv/

  * main.py
  * ui/

    * main_window.py
    * settings_dialog.py
  * plot/

    * plot_widget.py
  * protocols/

    * rdt_udp.py
    * tcp_cmd.py
    * http_calibration.py
  * acquisition/

    * acquisition_engine.py
    * ring_buffer.py
  * processing/

    * processing_engine.py
    * units.py
    * filters.py
    * decimation.py
    * transform.py
  * logging/

    * writer.py
    * formats.py
  * config/

    * preferences.py
  * diagnostics/

    * cli.py
    * sensor_simulator.py
* tests/

  * test_protocols.py
  * test_units.py
  * test_filters.py
  * test_logging.py
  * test_decimation.py
  * test_integration_simulator.py

---

## 12 Pipeline Overview

### 12.1 Stage Inventory

* Discover: UI Discover or gsdv discover
* Connect: UI Connect or gsdv connect
* Calibrate: auto after connect; HTTP preferred, TCP fallback
* Stream: auto after connect; UDP start command
* Process: continuous conversion, optional filter, update tiers
* Visualize: UI refresh loop (timer at 30 fps)
* Log: UI Record or gsdv log; async writes and rotation

### 12.2 Stage Dependencies

* Calibrate depends on Connect
* Stream depends on Connect
* Process depends on Stream and benefits from Calibrate
* Log depends on Stream and must not block Stream

---

## 13 Execution Model

### 13.1 Initial Run

1. App starts, loads preferences
2. UI renders in disconnected state
3. User connects via IP or discovery
4. On connect:

   * Fetch calibration (HTTP preferred) and identity
   * Start UDP RDT streaming
5. Begin processing loop (filter per settings; bias mode per settings)
6. UI updates:

   * Plot at least 30 fps
   * Numeric updates
7. Recording optional; logger runs asynchronously

### 13.2 Incremental Runs

* Start/stop recording does not stop streaming
* Toggle channels affects plot and numeric only
* Adjust time window switches tiers shown, not acquisition
* Reconnect: auto or manual without restart

---

## 14 Configuration Reference

### 14.1 Connection

* last_ip: string
* protocol_mode: enum auto|udp_tcp
* udp_port: int default 49152
* tcp_port: int default 49151
* http_port: int default 80
* connect_timeout_ms: int default 2000
* discovery_subnets: list[string] default detected local /24 subnets

### 14.2 Visualization

* channels_enabled: set[Fx,Fy,Fz,Tx,Ty,Tz] default Fx,Fy,Fz
* time_window_seconds: float default 10.0
* y_autoscale: bool default true
* y_manual_min/max: float optional
* show_grid: bool default true
* show_crosshair: bool default false
* plot_max_points_per_channel: int default 10000

### 14.3 Units

* force_unit: enum N|lbf|kgf default N
* torque_unit: enum Nm|Nmm|lbf_in|lbf_ft default Nm

### 14.4 Filtering

* filter_enabled: bool default false
* filter_cutoff_hz: float default 120.0 (min 0.7, max 120.0)

### 14.5 Bias

* bias_mode: enum device|soft default device

### 14.6 Logging

* output_directory: string
* filename_prefix: string
* format: enum csv|tsv|excel_compatible default csv
* flush_interval_ms: int default 250
* log_decimation_factor: int default 1
* rotation_enabled: bool default true
* rotate_interval_minutes: int default 60
* rotate_max_bytes: int default 2000000000

### 14.7 Tool Transform

* transform_dx/dy/dz: float default 0.0 (mm)
* transform_rx/ry/rz: float default 0.0 (degrees)

### 14.8 Preferences Storage

* **Format:** JSON
* **Location:** OS user config directory via `platformdirs.user_config_dir("gsdv")`
* **Filename:** preferences.json
* **Write rule:** atomic (write temp then rename)

Example locations:

* Linux: `~/.config/gsdv/preferences.json`
* macOS: `~/Library/Application Support/gsdv/preferences.json`
* Windows: `%APPDATA%\gsdv\preferences.json`

---

## 15 Data Models

### 15.1 SampleRecord

Required:

* t_monotonic_ns: int
* rdt_sequence: int
* ft_sequence: int
* status: int
* counts: int[6] in fixed order Fx,Fy,Fz,Tx,Ty,Tz

Optional:

* force_N: float[3]
* torque_Nm: float[3]

### 15.2 CalibrationInfo

Required:

* counts_per_force: float
* counts_per_torque: float

Optional:

* serial_number: string
* firmware_version: string
* force_units_code: int
* torque_units_code: int

### 15.3 UserPreferences

Includes fields from Section 14 plus:

* preferences_version: int for migration
* last_updated_utc: string ISO-8601

---

## 16 Algorithms and Core Logic

### 16.1 UDP RDT Streaming Loop

Core requirements:

* Never block on UI or file I/O
* Detect packet loss via rdt_sequence gaps
* Clean start/stop

Pseudocode:

1. Create UDP socket; set receive buffer large enough for bursts
2. Send RDT_REQUEST start (8 bytes, header 0x1234, command 0x0002, sample_count 0)
3. Loop:

   * recvfrom
   * parse fixed-size RDT_RESPONSE (36 bytes, big-endian)
   * validate length and header assumptions
   * push SampleRecord into bounded queue for processing

### 16.2 Multi-Resolution Plot Buffering and Decimation

Goal: maintain 30 fps plotting while supporting a 1 second to 7 day time window.

Implementation approach:

* Maintain a bounded raw ring plus downsampled tiers.
* Store min/max per bucket for tiers so inspection shows extremes.

Concrete sizing (default):

| Tier     | Duration Covered |          Effective Rate | Buckets or Samples per Channel | Stored Values                | Approx Memory |
| -------- | ---------------: | ----------------------: | -----------------------------: | ---------------------------- | ------------: |
| Raw ring |             60 s |                 1000 Hz |                         60,000 | raw counts + seq + timestamp |       ~2.6 MB |
| Tier 1   |           1 hour |  10 Hz (100 ms buckets) |                         36,000 | min/max float32 + timestamp  |       ~2.0 MB |
| Tier 2   |         24 hours |   0.1 Hz (10 s buckets) |                          8,640 | min/max float32 + timestamp  |       ~0.5 MB |
| Tier 3   |           7 days | 0.01 Hz (100 s buckets) |                          6,048 | min/max float32 + timestamp  |      ~0.34 MB |

Notes:

* Total for these buffers is well under 10 MB, leaving large headroom under the 200 MB cap.
* UI selects the smallest tier that can cover the requested window within plot point budget.
* pyqtgraph downsampling and clipping should be enabled to protect UI responsiveness.

### 16.3 Async Buffered File Writer and Rotation

Requirements:

* Full-rate capture at 1000 Hz with zero dropped samples
* Duration and file size visible during capture
* Must support long sessions via rotation

Approach:

* Logger runs in its own thread
* Processing thread enqueues structured samples or preformatted rows
* Logger writes in batches; flushes every flush_interval_ms and on stop
* Rotation:

  * If rotation_enabled:

    * Rotate if elapsed time exceeds rotate_interval_minutes, or file exceeds rotate_max_bytes
    * Each rotated file includes metadata header and column header row
    * Filenames include part index: `_part001`, `_part002`, etc
* Stop behavior:

  * Flush queue
  * Close file handle
  * Optional fsync for integrity

Excel-compatible definition:

* CSV with UTF-8 BOM
* CRLF newlines
* Conservative quoting to satisfy Excel import expectations
* No .xlsx conversion in v1

### 16.4 Sensor Discovery

Best-effort v1 discovery:

* Determine active local network subnets per NIC
* Scan a limited range (default /24 per subnet) by probing `http://<ip>/netftapi2.xml` with short timeout
* If XML contains expected calibration fields, treat host as sensor
* Populate list with IP plus any identity extracted

---

## 17 Adapter and Plugin Architecture

Keep protocol support modular:

* ISensorTransport:

  * connect(ip) → session
  * start_streaming, stop_streaming
  * send_command
  * read_samples
  * get_calibration
    Built-in adapters:
* NetRsUdpRdtTransport
* NetRsTcpCommandTransport
* NetRsHttpCalibrationTransport

---

## 18 CLI

Minimal CLI supports M1 and automation:

* gsdv discover [--subnet 192.168.1.0/24]
* gsdv stream --ip <ip> [--seconds 10]
* gsdv log --ip <ip> --out <dir> [--format csv|tsv|excel_compatible] [--seconds N]
* gsdv simulate-sensor [--rate 1000] [--loss 0.0] [--reorder 0.0] [--tcp] [--http] [--udp]

---

## 19 Concurrency and Locking

Threads:

* UI thread: rendering and user actions
* UDP receive thread: reads packets, parses, pushes SampleRecord to bounded queue
* Processing thread: conversion, filtering, tier updates, enqueue to logger
* Logger thread: buffered writes and rotation

Locking strategy:

* Bounded queues between threads
* UDP receive thread must never block; if queue full:

  * increment dropped-by-app counter
  * surface warning in status bar

---

## 20 Error Handling and Recovery

Taxonomy: NET, PROTO, CAL, IO, UI

Additions for v1.1:

* IO-003: Log rotation failed (cannot open next file)
  Recovery: stop recording, keep streaming, surface error, prompt for new directory

Atomic writes:

* Preferences writes must be atomic
* Log files:

  * On start: write metadata header
  * During run: flush at interval
  * On stop or rotation: flush and close; optional fsync

---

## 21 Caching and Invalidation

* Cache CalibrationInfo per sensor IP (and serial if available) for session
* Invalidate on:

  * reconnect to different IP or serial
  * user selects refresh calibration
  * firmware version change detected

---

## 22 Testing Strategy

### 22.1 Unit Tests

* RDT parsing from binary fixtures (endian correctness)
* Calibration parsing (HTTP XML, TCP response)
* Unit conversions
* Filter stability
* Decimation bucket logic and tier switching
* Filename generation and prefix sanitization
* CSV formatting and metadata header generation

### 22.2 Integration Tests

**Sensor simulator requirements (must be both standalone and test-friendly):**

* Standalone: `gsdv simulate-sensor` or `python -m gsdv.diagnostics.sensor_simulator`
* Provides:

  * HTTP server on port 80 serving `/netftapi2.xml`
  * UDP server on port 49152 sending RDT responses at configurable rate (default 1000 Hz)
  * TCP server on port 49151 supporting READCALINFO and optional READFT bias
* Fault injection:

  * Packet loss probability
  * Out-of-order injection
  * Burst behavior
  * Forced disconnects

Pytest fixture:

* Starts simulator in subprocess on ephemeral ports
* Returns connection info to tests
* Supports deterministic behavior via fixed random seed

End-to-end:

* connect → calibrate → stream → record N seconds → verify row count and metadata

### 22.3 Edge Cases

* Long-duration run with 7 day view window within memory budget
* Disk full mid-recording
* Disconnect mid-recording closes file cleanly
* High-DPI scaling and keyboard navigation

---

## 23 Resolved Decisions and Remaining Questions

### 23.1 Resolved

1. **Discovery:** subnet probing of `/netftapi2.xml` on local networks is acceptable for v1, user-initiated
2. **Calibration XML schema:** parse `counts_per_force` and `counts_per_torque`; include captured XML in Appendix 25.4 when available
3. **Default streaming rate:** 1000 Hz is default for NETrs; v1 targets sustaining 1000 Hz and displays measured rate
4. **Tool transform:** on-device via WRITETRANSFORM (TCP command 0x02); app sends dx/dy/dz in mm and rx/ry/rz in degrees (scaled by 100)
5. **Excel-compatible export:** CSV with UTF-8 BOM + CRLF; no .xlsx conversion in v1

### 23.2 Remaining (non-blocking)

* Confirm transform coordinate frame expectations using a physical validation test (known applied loads) and document in a short operational note

---

## 24 Glossary

* ATI NETrs: networked force/torque system supporting UDP/TCP/HTTP
* RDT: Raw Data Transfer protocol for high-rate UDP streaming
* cpf/cpt: counts-per-force/torque calibration constants
* Bias/Tare: operation to zero offsets
* Packet loss: missing rdt_sequence increments

---

## 25 Appendix

### 25.1 Workflow Sequences

Connect and Stream:

1. Launch app
2. Enter IP or discover
3. Connect
4. Retrieve calibration
5. Start UDP stream
6. Show plot and numeric readouts

Record Session:

1. Choose folder
2. Verify filename preview
3. Press Record
4. Observe duration and file size
5. Press Stop
6. Verify output file opens in spreadsheet tool

### 25.2 Example Log File Format (CSV)

Structure:

* Metadata header (comment lines)
* One header row with channel names and units
* Data rows with timestamps + sequences + channels

Example header row:
timestamp_utc, t_monotonic_ns, rdt_sequence, ft_sequence, status, Fx [N], Fy [N], Fz [N], Tx [N·m], Ty [N·m], Tz [N·m]

### 25.3 Binary Protocol Appendix

#### 25.3.1 UDP RDT Request Packet (8 bytes)

Big-endian.

```
Offset  Size  Type    Field           Description
0x00    2     uint16  command_header  0x1234
0x02    2     uint16  command         0x0000 stop
                                      0x0002 start real-time streaming
                                      0x0003 start buffered streaming
                                      0x0042 set bias/tare
0x04    4     uint32  sample_count    0 = infinite, else N samples

Hex example (start infinite):
12 34 00 02 00 00 00 00

Hex example (stop):
12 34 00 00 00 00 00 00

Hex example (bias/tare):
12 34 00 42 00 00 00 00
```

#### 25.3.2 UDP RDT Response Packet (36 bytes)

Big-endian.

```
Offset  Size  Type    Field         Description
0x00    4     uint32  rdt_sequence  Packet sequence number
0x04    4     uint32  ft_sequence   Internal sample number
0x08    4     uint32  status        Status code
0x0C    4     int32   Fx            Counts
0x10    4     int32   Fy            Counts
0x14    4     int32   Fz            Counts
0x18    4     int32   Tx            Counts
0x1C    4     int32   Ty            Counts
0x20    4     int32   Tz            Counts

Total: 36 bytes
Python struct: >IIIiiiiii
```

#### 25.3.3 TCP Calibration Request (20 bytes)

Sent to TCP 49151. No 0x1234 header in request.

```
Offset  Size  Type    Field     Value
0x00    1     uint8   command   0x01 (READCALINFO)
0x01    19    uint8[] reserved  zeros

Hex:
01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

#### 25.3.4 TCP Calibration Response (24 bytes)

Big-endian.

```
Offset  Size  Type       Field           Description
0x00    2     uint16     header          0x1234
0x02    1     uint8      forceUnits      Unit code
0x03    1     uint8      torqueUnits     Unit code
0x04    4     uint32     countsPerForce  cpf
0x08    4     uint32     countsPerTorque cpt
0x0C    12    uint16[6]  scaleFactors    16-bit scaling factors

Total: 24 bytes
Python struct: >HBBII6H
```

#### 25.3.5 TCP Bias Command via READFT (fallback, 20 bytes)

```
Offset  Size  Type    Field        Value
0x00    1     uint8   command      0x00 (READFT)
0x01    15    uint8[] reserved     zeros
0x10    2     uint16  MCEnable     0x0000
0x12    2     uint16  sysCommands  0x0001 (bit 0 = bias)

Hex:
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01
```

#### 25.3.6 TCP Tool Transform Command WRITETRANSFORM (20 bytes)

```
Offset  Size  Type      Field                 Notes
0x00    1     uint8     command               0x02
0x01    1     uint8     transformDistUnits    3 = mm
0x02    1     uint8     transformAngleUnits   1 = degrees
0x03    12    int16[6]  transform             dx,dy,dz,rx,ry,rz values x 100
0x0F    5     uint8[5]  reserved              zeros

Total: 20 bytes
```

### 25.4 Calibration XML Capture

To finalize documentation, paste a real sensor response here after running:

```
curl http://<sensor-ip>/netftapi2.xml
```

Minimum expected fields:

* counts_per_force
* counts_per_torque

### 25.5 Unit Codes Reference

Force unit codes:

* 1 lbf
* 2 N
* 5 kgf

Torque unit codes:

* 1 lbf·in
* 2 lbf·ft
* 3 N·m
* 4 N·mm

### 25.6 References

* ATI NETrs F/T Manual (Document #9620-05-NETRS FT)
* Gamma Series Transducer Manual
