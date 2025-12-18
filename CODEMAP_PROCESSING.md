# Codemap: Processing Pipeline

> Counts→SI conversion, filtering, multi-resolution decimation.

## Key Files

| File | Responsibility |
|------|----------------|
| `src/gsdv/processing/processing_engine.py` | Orchestrates conversion + filtering |
| `src/gsdv/processing/filters.py` | Butterworth IIR low-pass |
| `src/gsdv/processing/decimation.py` | Multi-resolution visualization buffer |
| `src/gsdv/processing/units.py` | Force/torque unit conversions |

## Data Flow

```
SampleRecord(counts only)
         ↓
    [soft zero subtract]
         ↓
    CalibrationInfo.convert_counts_to_si()
         ↓
    [IIR filter, optional]
         ↓
    SampleRecord(counts + force_N + torque_Nm)
         ↓
    ├→ VisualizationBuffer (tiered decimation)
    └→ logger_queue (for AsyncFileWriter)
```

## Decimation Tiers

| Tier | Resolution | Duration | Samples | Memory |
|------|------------|----------|---------|--------|
| Raw | 1000Hz | 60s | 60,000 | ~2.4MB |
| Tier1 | 10Hz | 1 hour | 36,000 | ~1.4MB |
| Tier2 | 0.1Hz | 24 hours | 8,600 | ~0.3MB |
| Tier3 | 0.01Hz | 7 days | 6,000 | ~0.2MB |

Each tier bucket stores `(min, max, count)` to preserve signal peaks.

## Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `ProcessingEngine` | `processing_engine.py:50` | Sync/async processing orchestration |
| `FilterPipeline` | `filters.py:30` | Butterworth IIR (Direct Form II) |
| `VisualizationBuffer` | `decimation.py:80` | Tiered min/max buckets |
| `SoftZeroOffsets` | `processing_engine.py:25` | Application-level bias |

## Filter Implementation

```
Butterworth 2nd-order IIR, Direct Form II Transposed
├── Coefficients via bilinear transform + frequency prewarping
├── Per-channel state vectors (6 channels)
├── Cutoff range: 0.7Hz - 120Hz
└── State reset on stream start (bumpless transients)
```

## Unit Conversions

| Force Units | Torque Units |
|-------------|--------------|
| N (SI) | N·m (SI) |
| lbf (×4.44822) | N·mm (×1000) |
| kgf (×9.80665) | lbf·in (×0.1129848) |
| | lbf·ft (×0.7375621) |

## Configuration

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `filter_enabled` | `False` | Enable IIR low-pass |
| `filter_cutoff_hz` | `10.0` | Cutoff frequency |
| `soft_zero_counts` | `(0,0,0,0,0,0)` | Application bias offset |

## Patterns

| Pattern | When | Example |
|---------|------|---------|
| Sync processing | Low latency | `engine.process_sample(sample)` |
| Async processing | Decouple from UI | `engine.submit_sample(sample)` + callback |
| Tier selection | Plot time window | `buffer.get_tier_for_window(seconds)` |

## Common Tasks

| Task | Solution |
|------|----------|
| Add filter type | Implement in `filters.py`, add to `FilterPipeline` |
| Add unit | Add to `ForceUnit`/`TorqueUnit` enum in `units.py`, add conversion factor |
| Change tier resolution | Edit `TIER_CONFIG` in `decimation.py` |

## Gotchas

**Filter state**: Filter has memory. Call `reset_filter_state()` when stream restarts to avoid transient spikes.

**Tier memory**: Total <10MB by design. Changing tier config may increase memory significantly.

**Queue overflow**: Async path drops samples if queue full. Check `dropped_input` stat.

**Counts overflow**: Raw counts are int32. Verify calibration factors won't overflow float64 after conversion.

## Dependencies

| This Uses | Used By |
|-----------|---------|
| `CalibrationInfo` (models) | `AsyncFileWriter` (logger_queue) |
| `numpy`, `scipy` concepts | `MultiChannelPlot` (via callback) |
| `queue`, `threading` | `MainWindow` |
