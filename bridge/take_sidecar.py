from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LAST_TAKE_FILENAME = "last_take.json"
TAKE_HISTORY_FILENAME = "take_history.json"
SIDECAR_POINTER_FILENAME = "sidecar_path.json"
SIDECAR_POINTER_ENV = "ABLETON_CAMERA_SIDECAR_POINTER"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TakeSidecar:
    video_path: Path
    track_label: str
    recorded_start: datetime
    finalized_at: datetime
    sync_offset_ms: int = 0

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "video_path": str(self.video_path.resolve()),
            "track_label": self.track_label,
            "recorded_start": self.recorded_start.isoformat(),
            "finalized_at": self.finalized_at.isoformat(),
            "sync_offset_ms": self.sync_offset_ms,
        }


def write_last_take(output_dir: Path, take: TakeSidecar) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / LAST_TAKE_FILENAME
    _write_json_atomic(sidecar_path, take.to_json_dict())
    return sidecar_path


def write_take_sidecars(output_dir: Path, take: TakeSidecar) -> tuple[Path, Path]:
    history_path = append_take_history(output_dir, take)
    last_path = write_last_take(output_dir, take)
    publish_sidecar_pointer(last_path, history_path)
    return last_path, history_path


def publish_sidecar_pointer(last_path: Path, history_path: Path) -> Path:
    pointer_path = sidecar_pointer_path()
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(
        pointer_path,
        {
            "schema_version": SCHEMA_VERSION,
            "last_take_path": str(last_path.resolve()),
            "take_history_path": str(history_path.resolve()),
        },
    )
    return pointer_path


def sidecar_pointer_path() -> Path:
    override = os.environ.get(SIDECAR_POINTER_ENV)
    if override:
        return Path(override).expanduser()

    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "ableton-camera"
            / SIDECAR_POINTER_FILENAME
        )
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return root / "ableton-camera" / SIDECAR_POINTER_FILENAME

    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else Path.home() / ".config"
    return root / "ableton-camera" / SIDECAR_POINTER_FILENAME


def append_take_history(output_dir: Path, take: TakeSidecar) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_path = output_dir / TAKE_HISTORY_FILENAME
    history = _read_history(history_path)
    history["takes"].append(take.to_json_dict())
    _write_json_atomic(history_path, history)
    return history_path


def _read_history(history_path: Path) -> dict[str, object]:
    if not history_path.exists():
        return {"schema_version": SCHEMA_VERSION, "takes": []}

    raw = json.loads(history_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported take history schema_version: {raw.get('schema_version')}")
    takes = raw.get("takes")
    if not isinstance(takes, list):
        raise ValueError("Take history must contain a takes list.")
    return {"schema_version": SCHEMA_VERSION, "takes": takes}


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
