# Plan: UI Fixes for GSDV

## Issues to Fix

1. **Numeric Readout layout** - Currently 2 rows x 3 columns, values get cut off
2. **Plot background** - White background, should be dark to match theme

## Fix 1: Numeric Readout Layout

**File:** `src/gsdv/ui/main_window.py`

**Location:** `NumericDisplay._setup_ui()` method (around line 292-309)

**Current code (2 rows x 3 columns):**
```python
def _setup_ui(self) -> None:
    layout = QGridLayout(self)
    layout.setContentsMargins(8, 4, 8, 4)
    layout.setSpacing(4)

    for i, channel in enumerate(self.CHANNELS):
        name_label = QLabel(f"{channel}:")
        name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(name_label, i // 3, (i % 3) * 2)

        value_label = QLabel("---")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setMinimumWidth(80)
        value_label.setStyleSheet("font-family: monospace;")
        layout.addWidget(value_label, i // 3, (i % 3) * 2 + 1)

        self._labels[channel] = name_label
        self._value_labels[channel] = value_label
```

**Replace with (6 rows x 2 columns, vertical layout):**
```python
def _setup_ui(self) -> None:
    layout = QGridLayout(self)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    for i, channel in enumerate(self.CHANNELS):
        name_label = QLabel(f"{channel}:")
        name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(name_label, i, 0)

        value_label = QLabel("---")
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        value_label.setMinimumWidth(120)
        value_label.setStyleSheet("font-family: monospace; font-size: 14px;")
        layout.addWidget(value_label, i, 1)

        self._labels[channel] = name_label
        self._value_labels[channel] = value_label

    # Add stretch at the bottom to push content up
    layout.setRowStretch(len(self.CHANNELS), 1)
```

## Fix 2: Plot Background Color (Dark Theme)

**File:** `src/gsdv/plot/plot_widget.py`

**Location:** `MultiChannelPlot._setup_ui()` method (around line 85-96)

**Current code:**
```python
# Configure pyqtgraph for performance
pg.setConfigOptions(antialias=False, useOpenGL=False)

# Create PlotWidget
self._plot_widget = pg.PlotWidget()
self._plot_widget.setBackground("w")  # <-- White background
```

**Replace with:**
```python
# Configure pyqtgraph for performance
pg.setConfigOptions(antialias=True, useOpenGL=False)

# Create PlotWidget
self._plot_widget = pg.PlotWidget()
self._plot_widget.setBackground("#1e1e1e")  # Dark background
```

**Also update foreground color** by adding after setBackground:
```python
self._plot_item = self._plot_widget.getPlotItem()
# ... existing axis label code ...
```

The axis labels and grid should automatically use light colors against dark background since pyqtgraph detects background luminance.

## Summary

| File | Method | Change |
|------|--------|--------|
| `src/gsdv/ui/main_window.py` | `NumericDisplay._setup_ui()` | Change grid from 2x6 to 6x2, increase spacing, add row stretch |
| `src/gsdv/plot/plot_widget.py` | `MultiChannelPlot._setup_ui()` | Change `setBackground("w")` to `setBackground("#1e1e1e")`, enable antialias |
