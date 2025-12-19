# Codemap: UI & Visualization

> PySide6 GUI with real-time pyqtgraph plotting.

## Key Files

| File | Responsibility |
|------|----------------|
| `src/gsdv/ui/main_window.py` | Main application window, panels, controls |
| `src/gsdv/ui/settings_dialog.py` | Preferences editor modal |
| `src/gsdv/plot/plot_widget.py` | Real-time multi-channel pyqtgraph |
| `src/gsdv/config/preferences.py` | Persistent user settings |

## Component Layout

```
┌─────────────────────────────────────────────────────────┐
│ MainWindow                                              │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────┐ ┌─────────────────────────────────┐ │
│ │ ConnectionPanel │ │ MultiChannelPlot                │ │
│ │ - IP input      │ │ - 6 channel lines (Fx..Tz)     │ │
│ │ - Connect btn   │ │ - Dual Y-axis (force/torque)   │ │
│ │ - Status LED    │ │ - Time window zoom             │ │
│ └─────────────────┘ │ - Tier-based data source       │ │
│ ┌─────────────────┐ │                                 │ │
│ │ ChannelSelector │ └─────────────────────────────────┘ │
│ │ - Fx/Fy/Fz/Tx.. │                                     │
│ │ - Toggle each   │                                     │
│ └─────────────────┘                                     │
│ ┌─────────────────┐                                     │
│ │ TimeWindow      │                                     │
│ │ - 1s to 7 days  │                                     │
│ └─────────────────┘                                     │
│ ┌─────────────────┐                                     │
│ │ RecordingCtrls  │                                     │
│ │ - Start/Stop    │                                     │
│ │ - Bias button   │                                     │
│ └─────────────────┘                                     │
├─────────────────────────────────────────────────────────┤
│ StatusBar: packets | loss % | buffer fill | recording  │
└─────────────────────────────────────────────────────────┘
```

## Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `MainWindow` | `main_window.py:50` | Top-level QMainWindow |
| `MultiChannelPlot` | `plot_widget.py:40` | pyqtgraph PlotWidget wrapper |
| `SettingsDialog` | `settings_dialog.py:30` | QDialog for preferences |
| `UserPreferences` | `preferences.py:25` | Dataclass + JSON persistence |

## Signal/Slot Flow

```
ConnectionPanel.connect_clicked
         ↓
    MainWindow._on_connect()
         ↓
    AcquisitionEngine.start()
         ↓
    [callback thread]
         ↓
    ProcessingEngine.process_sample()
         ↓
    visualization_callback(sample)
         ↓
    QMetaObject.invokeMethod() [thread-safe]
         ↓
    MultiChannelPlot.add_sample()
```

## Time Windows

| Label | Seconds | Tier Used |
|-------|---------|-----------|
| 1s | 1 | Raw |
| 5s | 5 | Raw |
| 30s | 30 | Raw |
| 1 min | 60 | Raw |
| 5 min | 300 | Tier1 |
| 30 min | 1800 | Tier1 |
| 1 hour | 3600 | Tier1 |
| 6 hours | 21600 | Tier2 |
| 24 hours | 86400 | Tier2 |
| 7 days | 604800 | Tier3 |

## Preferences Structure

```python
UserPreferences:
├── connection: ip, ports, timeout, auto_reconnect
├── visualization: channels_enabled, force_unit, torque_unit, theme
├── logging: format, directory, rotation_size, rotation_time, prefix
├── bias: mode (device|soft), soft_zero_counts
├── filter: enabled, cutoff_hz
├── decimation_factor: int (1=1000Hz, 10=100Hz)  # Controls acquisition rate
├── transform: dx, dy, dz, rx, ry, rz
└── buffer: ring_capacity_samples
```

## Themes

| Theme | Background | Line Colors |
|-------|------------|-------------|
| Dark | `#1e1e1e` | Bright primaries |
| Light | `#ffffff` | Dark primaries |

## Common Tasks

| Task | Solution |
|------|----------|
| Add UI panel | Create QWidget subclass, add to `MainWindow.__init__()` layout |
| Add preference | Add field to `UserPreferences`, add control to `SettingsDialog` |
| Add time window | Add to `TIME_WINDOWS` list in `main_window.py` |
| Change plot colors | Edit `CHANNEL_COLORS` dict in `plot_widget.py` |

## Plot Performance Optimizations

Per [pyqtgraph documentation](https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/plotdataitem.html):

| Setting | Value | Purpose |
|---------|-------|---------|
| `antialias` | `False` | Disable antialiasing for speed |
| `pen width` | `1` | Wider pens cause significant slowdown |
| `setClipToView` | `True` | Only render visible data |
| `setDownsampling` | `auto=True, method="peak"` | Auto-downsample preserving peaks/valleys |

## Gotchas

**Thread-safe updates**: Never call Qt methods from callback thread. Use `QMetaObject.invokeMethod()` or signals.

**Plot performance**: Use pyqtgraph's built-in `setDownsampling(auto=True, method="peak")` and `setClipToView(True)`. Avoid pen width > 1 and antialiasing.

**Preference persistence**: Uses `platformdirs` for OS-appropriate config location. Don't hardcode paths.

**Modal dialogs**: `SettingsDialog.exec()` blocks. Apply changes after dialog closes, not during.

**Dual Y-axis**: Force on left (N), torque on right (N·m). Scaling is independent.

**Decimation setting**: Changes to `decimation_factor` in Settings require disconnect/reconnect to take effect.

## Dependencies

| This Uses | Used By |
|-----------|---------|
| `PySide6`, `pyqtgraph` | `main.py` entry point |
| `ProcessingEngine` (callback) | — |
| `AcquisitionEngine` (stats) | — |
| `VisualizationBuffer` (tiers) | — |
| `UserPreferences` | — |

## Entry Points

```bash
gsdv-gui          # Launches MainWindow (placeholder)
```

```python
from gsdv.ui import MainWindow
app = QApplication([])
window = MainWindow()
window.show()
app.exec()
```
