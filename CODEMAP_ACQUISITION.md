# Codemap: Acquisition Engine

> High-frequency (1000Hz) non-blocking data ingestion with ring buffer.

## Key Files

| File | Responsibility |
|------|----------------|
| `src/gsdv/acquisition/acquisition_engine.py` | Receive thread, state machine, statistics |
| `src/gsdv/acquisition/ring_buffer.py` | Pre-allocated circular buffer |

## Data Flow

```
RdtClient.receive_samples()
           ↓
    [receive thread]
           ↓
    RingBuffer.append(sample)
           ↓
    ├→ get_latest(n) → numpy arrays
    └→ callback(sample) [optional, separate thread]
```

## State Machine

```
STOPPED → start() → STARTING → [thread spawned] → RUNNING
                                                      ↓
STOPPED ← [thread joined] ← STOPPING ← stop() ←──────┘
                                                      ↓
                                               ERROR (on exception)
```

## Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `AcquisitionEngine` | `acquisition_engine.py:45` | Thread lifecycle, stats, callbacks |
| `RingBuffer` | `ring_buffer.py:20` | NumPy circular arrays, overwrite semantics |
| `AcquisitionStats` | `acquisition_engine.py:25` | Immutable stats snapshot |

## Buffer Structure

```python
RingBuffer(capacity=60000)  # 60s at 1000Hz
├── timestamps: int64[60000]      # t_monotonic_ns
├── rdt_sequences: uint32[60000]
├── ft_sequences: uint32[60000]
├── status: uint32[60000]
├── counts: int32[60000, 6]       # Fx,Fy,Fz,Tx,Ty,Tz
└── write_ptr: int                # wraps at capacity
```

## Thread Model

```
Main thread              Receive thread           Callback thread
     │                        │                        │
     │──start()──────────────→│                        │
     │                        │──UDP recv loop────────→│
     │                        │  └→ buffer.append()    │──callback(sample)
     │──stats()──────────────→│                        │
     │                        │                        │
     │──stop()───────────────→│                        │
     │                        │──join(2s)              │──join(1s)
```

## Configuration

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `buffer_capacity` | `60000` | Samples (60s at 1000Hz) |
| `receive_timeout` | `0.1` | Socket timeout (seconds) |
| `callback` | `None` | Optional per-sample notification |

## Statistics

| Field | Meaning |
|-------|---------|
| `packets_received` | Total UDP packets |
| `packets_lost` | Sequence gaps detected |
| `receive_errors` | Socket exceptions |
| `samples_per_second` | Rolling average rate |
| `buffer_fill_percent` | Current usage |

## Common Tasks

| Task | Solution |
|------|----------|
| Increase buffer | Change `buffer_capacity` param (trades memory for history) |
| Add stat field | Add to `AcquisitionStats` dataclass, update in receive loop |
| Change timeout | Pass `receive_timeout` to constructor |

## Gotchas

**Overwrite semantics**: When buffer full, oldest samples silently overwritten. Check `overwrites` counter if data loss matters.

**Callback thread**: Callbacks run in separate thread to avoid blocking receive. Don't do heavy work in callback.

**Thread safety**: `stats()` and `get_latest()` acquire lock. Don't call at >100Hz from UI.

**Stop timeout**: `stop()` waits up to 2s for receive thread. If socket blocked, may need to close socket first.

## Dependencies

| This Uses | Used By |
|-----------|---------|
| `RdtClient` (protocols) | `ProcessingEngine` |
| `threading`, `queue` | `MainWindow` |
| `numpy` | `VisualizationBuffer` |
