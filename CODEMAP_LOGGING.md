# Codemap: File Logging

> Non-blocking buffered file writing with rotation and multi-format export.

## Key Files

| File | Responsibility |
|------|----------------|
| `src/gsdv/logging/writer.py` | Async writer thread, queue, rotation |
| `src/gsdv/logging/formats.py` | CSV/TSV/Excel formatters |
| `src/gsdv/logging/filename.py` | Timestamped filename generation |

## Data Flow

```
ProcessingEngine.logger_queue
           ↓
    [writer thread]
           ↓
    formatter(sample) → line
           ↓
    buffer (64KB)
           ↓
    flush (every 250ms or buffer full)
           ↓
    file.write()
           ↓
    [rotation check: size/time]
           ↓
    new file if exceeded
```

## State Machine

```
STOPPED → start() → RUNNING → stop() → STOPPING → STOPPED
                       ↓
                    ERROR (disk full, permission denied)
```

## Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `AsyncFileWriter` | `writer.py:40` | Thread, queue, buffering, rotation |
| `WriterStats` | `writer.py:20` | samples_written, dropped, bytes, latency |
| `csv_formatter` | `formats.py:30` | CSV line generator |
| `generate_filename` | `filename.py:25` | Sanitized timestamped names |

## File Formats

**CSV/TSV Header**:
```
# Serial: FT12345
# Firmware: 1.2.3
# CPF: 1000000
# CPT: 1000000
t_monotonic_ns,rdt_sequence,ft_sequence,status,Fx_counts,Fy_counts,...,Fx_N,Fy_N,...
```

**Excel-compatible**: Same as CSV but with:
- UTF-8 BOM (`0xEFBBBF`) for encoding detection
- `\r\n` line endings

**Filename Format**:
```
{prefix_}YYYYMMDD_HHMMSS{_partNNN}.{ext}
Example: sensor1_20251218_153045.csv
Rotated: sensor1_20251218_153045_002.csv
```

## Configuration

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `queue_size` | `1000` | Max pending samples |
| `batch_size` | `100` | Samples per write batch |
| `flush_interval_ms` | `250` | Force flush interval |
| `rotation_size_mb` | `100` | Rotate at size |
| `rotation_time_min` | `60` | Rotate at time |

## Statistics

| Field | Meaning |
|-------|---------|
| `samples_written` | Total to disk |
| `samples_dropped` | Queue overflow |
| `bytes_written` | Total bytes |
| `flushes` | Flush count |
| `flush_latency_avg_ms` | I/O performance |

## Error Handling

| Exception | Cause | Recovery |
|-----------|-------|----------|
| `DirectoryNotWritableError` | Permission denied | Choose different directory |
| `DiskFullError` | No space left | Free space or change drive |
| `LogRotationError` | Can't create new file | Check permissions, disk |
| `FileWriteError` | I/O error during write | Retry or abort |

## Common Tasks

| Task | Solution |
|------|----------|
| Add format | Add formatter function in `formats.py`, register in format map |
| Change rotation | Pass `rotation_size_mb` / `rotation_time_min` to constructor |
| Add header field | Edit formatter functions, update header line |

## Gotchas

**Non-blocking write**: `write(sample)` returns immediately. If queue full, sample dropped (returns `False`).

**Excel BOM**: Required for Excel to detect UTF-8. Don't strip it.

**Filename sanitization**: Removes `<>:"/\|?*` and path traversal (`..`). Don't rely on user input being safe.

**Rotation part numbers**: 001-999. After 999, behavior undefined (won't happen in practice).

**Flush on stop**: `stop()` flushes remaining buffer before closing. Don't kill process without stop().

## Dependencies

| This Uses | Used By |
|-----------|---------|
| `ProcessingEngine.logger_queue` | `MainWindow` (recording controls) |
| `pathlib`, `threading`, `queue` | CLI `log` command |
