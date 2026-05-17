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


def default_project_name(at: datetime | None = None) -> str:
    """Date-based project folder name when none is configured (YYYY-MM-DD, local time)."""
    when = at if at is not None else datetime.now().astimezone()
    return when.strftime("%Y-%m-%d")


def resolve_output_dir(base_dir: Path, project: str | None) -> Path:
    """Place recordings in base_dir, or base_dir/{project} when a project name is set."""
    if not project or not project.strip():
        return base_dir
    safe_project = sanitize_component(project)
    if safe_project == "Unknown":
        return base_dir
    return base_dir / safe_project


def extension_from_path(path: Path) -> str:
    suffix = path.suffix
    return suffix.lstrip(".") if suffix else "mkv"
