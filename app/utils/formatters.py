"""Reusable human-readable formatters."""

from __future__ import annotations

import os

_UNITS = ("B", "KB", "MB", "GB", "TB")
_DECIMALS = {"B": 0, "KB": 0, "MB": 1, "GB": 2, "TB": 2}

BAR_WIDTH = 16
BAR_FULL = "▰"
BAR_EMPTY = "▱"


def format_size(num_bytes: float | int | None) -> str:
    """``512 KB`` / ``12.4 MB`` / ``1.42 GB``."""
    value = max(0.0, float(num_bytes or 0))
    index = 0
    while value >= 1024 and index < len(_UNITS) - 1:
        value /= 1024.0
        index += 1
    unit = _UNITS[index]
    return f"{value:.{_DECIMALS[unit]}f} {unit}"


def format_speed(bytes_per_second: float | None) -> str:
    """``23.4 MB/s``."""
    if not bytes_per_second or bytes_per_second <= 0:
        return "0 KB/s"
    return f"{format_size(bytes_per_second)}/s"


def format_duration(seconds: float | int | None) -> str:
    """``MM:SS`` or ``HH:MM:SS``."""
    total = int(max(0, seconds or 0))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "--:--"
    return format_duration(seconds)


def format_percentage(done: float | int, total: float | int) -> str:
    if not total or total <= 0:
        return "0%"
    return f"{max(0.0, min(100.0, done / total * 100.0)):.0f}%"


def progress_bar(done: float | int, total: float | int, width: int = BAR_WIDTH) -> str:
    """Fixed-width bar: ``▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱  50%``."""
    ratio = 0.0 if not total or total <= 0 else max(0.0, min(1.0, done / total))
    filled = int(ratio * width + 0.5)
    return f"{BAR_FULL * filled}{BAR_EMPTY * (width - filled)}  {ratio * 100:.0f}%"


def pretty_name(name: str, limit: int = 46) -> str:
    """Readable single-line title for a file name (display only)."""
    stem, ext = os.path.splitext(name or "file")
    stem = " ".join(stem.replace("_", " ").replace(".", " ").split()) or "file"
    room = max(8, limit - len(ext))
    if len(stem) > room:
        head = (room * 2) // 3
        tail = room - head - 1
        stem = f"{stem[:head].rstrip()}…{stem[-tail:].lstrip()}"
    return f"{stem}{ext}"
