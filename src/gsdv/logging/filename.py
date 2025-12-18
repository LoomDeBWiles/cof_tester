"""Filename generation for data logging.

Implements FR-20 (File Naming): timestamped filenames with optional prefix
and filesystem-safe sanitization.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


# Characters allowed in filename prefix (filesystem-safe across platforms)
# Allows alphanumeric, underscore, hyphen, and period
_SAFE_PREFIX_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]*$")

# Characters to strip from prefix (reserved on Windows and generally problematic)
# Includes space to ensure sanitized output is valid per _SAFE_PREFIX_PATTERN
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f ]')

# Pattern matching unsafe characters in extension (anything that isn't alphanumeric)
# Prevents path traversal attacks via extension parameter
_UNSAFE_EXTENSION_CHARS = re.compile(r"[^a-zA-Z0-9]")


def sanitize_prefix(prefix: str) -> str:
    """Sanitize a filename prefix for filesystem safety.

    Removes characters that are invalid on Windows, macOS, or Linux filesystems.
    Returns empty string if the result would be empty or only whitespace.

    Args:
        prefix: User-provided filename prefix.

    Returns:
        Sanitized prefix safe for use in filenames.
    """
    if not prefix:
        return ""

    # Remove unsafe characters
    sanitized = _UNSAFE_CHARS.sub("", prefix)

    # Collapse multiple underscores/hyphens
    sanitized = re.sub(r"[_\-]{2,}", "_", sanitized)

    # Strip leading/trailing whitespace and dots (problematic on some systems)
    sanitized = sanitized.strip(" .")

    return sanitized


def is_valid_prefix(prefix: str) -> bool:
    """Check if a prefix contains only safe filesystem characters.

    Args:
        prefix: Filename prefix to validate.

    Returns:
        True if the prefix is safe to use without modification.
    """
    if not prefix:
        return True
    return bool(_SAFE_PREFIX_PATTERN.match(prefix))


def sanitize_extension(extension: str) -> str:
    """Sanitize a file extension for filesystem safety.

    Removes any characters that could enable path traversal or other
    filesystem attacks. Only alphanumeric characters are allowed.

    Args:
        extension: File extension (with or without leading dot).

    Returns:
        Sanitized extension containing only alphanumeric characters.
    """
    # Strip leading dots first
    ext = extension.lstrip(".")
    # Remove all non-alphanumeric characters (including path separators)
    return _UNSAFE_EXTENSION_CHARS.sub("", ext)


def generate_filename(
    extension: str,
    prefix: str = "",
    timestamp: datetime | None = None,
    part_number: int | None = None,
) -> str:
    """Generate a timestamped filename for data logging.

    Format: {prefix_}YYYYMMDD_HHMMSS{_partNNN}.{ext}

    Args:
        extension: File extension without the dot (e.g., "csv", "tsv").
        prefix: Optional user prefix. Will be sanitized for filesystem safety.
        timestamp: Timestamp to use. Defaults to current UTC time.
        part_number: Optional part number for rotated files (1-999).

    Returns:
        Generated filename string.

    Raises:
        ValueError: If extension is empty (or becomes empty after sanitization)
            or part_number is out of range.
    """
    if part_number is not None and (part_number < 1 or part_number > 999):
        raise ValueError("Part number must be between 1 and 999")

    # Use current UTC time if not provided
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Format timestamp as YYYYMMDD_HHMMSS
    time_str = timestamp.strftime("%Y%m%d_%H%M%S")

    # Sanitize and apply prefix
    safe_prefix = sanitize_prefix(prefix)

    # Build filename parts
    parts = []
    if safe_prefix:
        parts.append(safe_prefix)
    parts.append(time_str)

    # Add part number for rotated files
    if part_number is not None:
        parts.append(f"part{part_number:03d}")

    # Sanitize extension (remove path traversal characters, keep only alphanumeric)
    ext = sanitize_extension(extension)
    if not ext:
        raise ValueError("Extension cannot be empty")

    return "_".join(parts) + "." + ext


def generate_filepath(
    output_directory: Path | str,
    extension: str,
    prefix: str = "",
    timestamp: datetime | None = None,
    part_number: int | None = None,
) -> Path:
    """Generate a full filepath for data logging.

    Args:
        output_directory: Directory where the file will be created.
        extension: File extension without the dot.
        prefix: Optional user prefix.
        timestamp: Timestamp to use. Defaults to current UTC time.
        part_number: Optional part number for rotated files.

    Returns:
        Full Path object for the output file.

    Raises:
        ValueError: If extension is empty or part_number is out of range.
    """
    filename = generate_filename(
        extension=extension,
        prefix=prefix,
        timestamp=timestamp,
        part_number=part_number,
    )
    return Path(output_directory) / filename


def preview_filename(
    extension: str,
    prefix: str = "",
) -> str:
    """Generate a preview filename showing what will be created.

    Uses a placeholder timestamp to show the format without committing
    to a specific time.

    Args:
        extension: File extension without the dot.
        prefix: Optional user prefix.

    Returns:
        Preview filename string with placeholder timestamp.
    """
    safe_prefix = sanitize_prefix(prefix)

    parts = []
    if safe_prefix:
        parts.append(safe_prefix)
    parts.append("YYYYMMDD_HHMMSS")

    ext = sanitize_extension(extension)

    return "_".join(parts) + "." + ext
