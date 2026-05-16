from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path


class OutputDirCancelled(Exception):
    """User cancelled the output folder picker."""


def validate_output_dir(path: Path, *, create: bool = False) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_file():
        raise ValueError(f"Not a directory: {resolved}")
    if resolved.exists():
        if not resolved.is_dir():
            raise ValueError(f"Not a directory: {resolved}")
        if not _is_writable(resolved):
            raise ValueError(f"Directory is not writable: {resolved}")
        return resolved
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved
    raise ValueError(f"Directory does not exist: {resolved}")


def _is_writable(directory: Path) -> bool:
    probe = directory / ".ableton_camera_write_test"
    try:
        probe.touch()
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def choose_output_dir(
    prompt_fn: Callable[[], str | None] | None = None,
    *,
    create: bool = True,
) -> Path:
    if prompt_fn is None:
        prompt_fn = _default_folder_prompt

    raw = prompt_fn()
    if raw is None or not str(raw).strip():
        raise OutputDirCancelled("Output folder selection cancelled")

    return validate_output_dir(Path(str(raw).strip()), create=create)


def _default_folder_prompt() -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return _terminal_folder_prompt()

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="Choose folder for video recordings")
    finally:
        root.destroy()
    return selected if selected else None


def _terminal_folder_prompt() -> str | None:
    print("Enter output folder for recordings:", file=sys.stderr)
    line = sys.stdin.readline()
    if not line.strip():
        return None
    return line.strip()
