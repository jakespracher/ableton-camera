from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_INVALID_CHARS = re.compile(r'[/\\:*?"<>|\s]+')


def sanitize_component(value: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", value.strip())
    return cleaned or "Unknown"


def build_filename(track_label: str, at: datetime, ext: str = "mkv") -> str:
    safe_track = sanitize_component(track_label)
    stamp = at.strftime("%Y-%m-%d_%H%M%S")
    extension = ext.lstrip(".")
    return f"{safe_track}_{stamp}.{extension}"


def extension_from_path(path: Path) -> str:
    suffix = path.suffix
    return suffix.lstrip(".") if suffix else "mkv"
