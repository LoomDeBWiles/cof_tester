"""Export format implementations (CSV, TSV, Excel-compatible)."""

from typing import Any, Optional

from gsdv.models import CalibrationInfo, SampleRecord

FORMAT_CSV = "csv"
FORMAT_TSV = "tsv"
FORMAT_EXCEL = "excel_compatible"

BOM_UTF8 = "\ufeff"


def _format_value(val: Any) -> str:
    """Format a single value for output."""
    if val is None:
        return ""
    if isinstance(val, float):
        # Use enough precision for scientific data
        return f"{val:.6f}"
    return str(val)


def _flatten_sample(sample: SampleRecord) -> list[Any]:
    """Flatten a SampleRecord into a list of values."""
    # Base fields
    values = [
        sample.t_monotonic_ns,
        sample.rdt_sequence,
        sample.ft_sequence,
        sample.status,
    ]
    # Counts
    values.extend(sample.counts)
    
    # Force (if available, else empty placeholders)
    if sample.force_N:
        values.extend(sample.force_N)
    else:
        values.extend([""] * 3)
        
    # Torque (if available, else empty placeholders)
    if sample.torque_Nm:
        values.extend(sample.torque_Nm)
    else:
        values.extend([""] * 3)
        
    return values


def csv_formatter(sample: Any) -> str:
    """Format a sample as CSV."""
    if isinstance(sample, SampleRecord):
        values = _flatten_sample(sample)
        return ",".join(_format_value(v) for v in values)
    elif isinstance(sample, tuple):
        return ",".join(str(v) for v in sample)
    return str(sample)


def tsv_formatter(sample: Any) -> str:
    """Format a sample as TSV."""
    if isinstance(sample, SampleRecord):
        values = _flatten_sample(sample)
        return "\t".join(_format_value(v) for v in values)
    elif isinstance(sample, tuple):
        return "\t".join(str(v) for v in sample)
    return str(sample)


def excel_formatter(sample: Any) -> str:
    """Format a sample for Excel (CSV compatible).
    
    Note: The Writer handles the line endings (CRLF).
    This function behaves like standard CSV for the row data.
    """
    return csv_formatter(sample)


def get_column_headers(format_type: str = FORMAT_CSV) -> str:
    """Get the column header line."""
    cols = [
        "t_monotonic_ns",
        "rdt_sequence",
        "ft_sequence",
        "status",
        "Fx_counts",
        "Fy_counts",
        "Fz_counts",
        "Tx_counts",
        "Ty_counts",
        "Tz_counts",
        "Fx_N",
        "Fy_N",
        "Fz_N",
        "Tx_Nm",
        "Ty_Nm",
        "Tz_Nm",
    ]
    
    sep = "\t" if format_type == FORMAT_TSV else ","
    return sep.join(cols)


def get_metadata_header(
    format_type: str,
    calibration: Optional[CalibrationInfo] = None,
    identity: Optional[dict[str, str]] = None,
    extra_metadata: Optional[dict[str, str]] = None,
) -> str:
    """Generate the full metadata header string including BOM if needed.
    
    Args:
        format_type: One of FORMAT_CSV, FORMAT_TSV, FORMAT_EXCEL.
        calibration: Optional CalibrationInfo object.
        identity: Optional dictionary with identity info (serial, firmware).
        extra_metadata: Optional additional metadata key-values.
        
    Returns:
        String containing BOM (if Excel), comments, and column headers.
        Does NOT include the final newline, as Writer adds it.
    """
    lines = []
    
    # Add BOM for Excel-compatible format
    if format_type == FORMAT_EXCEL:
        lines.append(BOM_UTF8)
        
    # Add metadata comments
    # Note: Excel opening CSV ignores '#' comments usually, but putting them 
    # at the top is standard for scientific data. User can import text to handle them.
    # However, if requirement "Excel opens files correctly" means "click and see table",
    # comments might push data down or be in first cell.
    # Standard practice for "Excel CSV" is usually just headers. 
    # But "Metadata header" is a requirement.
    # We will use '#' prefix.
    
    def add_comment(key: str, val: Any) -> None:
        if val is not None:
             lines.append(f"# {key}: {val}")

    if identity:
        add_comment("Serial Number", identity.get("serial_number"))
        add_comment("Firmware Version", identity.get("firmware_version"))
        
    if calibration:
        add_comment("Counts Per Force", calibration.counts_per_force)
        add_comment("Counts Per Torque", calibration.counts_per_torque)
        add_comment("Force Units Code", calibration.force_units_code)
        add_comment("Torque Units Code", calibration.torque_units_code)
        
    if extra_metadata:
        for k, v in extra_metadata.items():
            add_comment(k, v)
            
    # Add column headers
    # Ensure previous lines have newlines if we added them (except BOM which is just a marker)
    # Actually, `lines` is a list of strings. We should join them with the target line ending.
    # But Writer takes a single string header.
    # If we return a multi-line string, Writer might add ONE line terminator at the end.
    # We should pre-join these with the target terminator?
    # Writer's `line_terminator` is used for data rows.
    # The header is written as-is, with `line_terminator` appended if not present.
    # So we should join metadata lines with `\n` (or `\r\n` for Excel).
    
    terminator = "\r\n" if format_type == FORMAT_EXCEL else "\n"
    
    # Filter out empty BOM entry if present (it's handled by join if we're careful)
    # Actually, BOM should be the start of the string, no newline after it.
    
    header_str = ""
    if format_type == FORMAT_EXCEL:
        header_str += BOM_UTF8
        # Remove BOM from lines list to avoid double adding or newline issues
        if lines and lines[0] == BOM_UTF8:
            lines.pop(0)
            
    # Join comment lines
    if lines:
        header_str += terminator.join(lines) + terminator
        
    # Append column headers
    header_str += get_column_headers(format_type)
    
    return header_str