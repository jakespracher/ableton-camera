from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bridge.naming import extension_from_path, sanitize_component
from bridge.take_sidecar import TakeSidecar, write_take_sidecars


@dataclass(frozen=True)
class CaptureResult:
    video_path: Path
    sidecar_path: Path
    history_path: Path


def capture_seconds(*, bars: int, tempo_bpm: float, beats_per_bar: int) -> float:
    if bars <= 0:
        raise ValueError("bars must be greater than zero")
    if tempo_bpm <= 0:
        raise ValueError("tempo_bpm must be greater than zero")
    if beats_per_bar <= 0:
        raise ValueError("beats_per_bar must be greater than zero")
    return bars * beats_per_bar * 60 / tempo_bpm


def build_capture_filename(track_label: str, at: datetime, ext: str) -> str:
    safe_track = sanitize_component(track_label)
    stamp = at.strftime("%Y-%m-%d_%H%M%S")
    extension = ext.lstrip(".")
    return f"{safe_track}_capture_{stamp}.{extension}"


def finalize_capture_take(
    *,
    source_path: Path,
    output_dir: Path,
    track_label: str,
    clock: Callable[[], datetime],
    sync_offset_ms: int,
    bars: int,
    tempo_bpm: float,
    beats_per_bar: int,
    live_current_song_time: float,
    trim_seconds: float | None,
) -> CaptureResult:
    captured_at = clock()
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / build_capture_filename(
        track_label,
        captured_at,
        extension_from_path(source_path),
    )
    shutil.move(str(source_path), str(dest))
    sidecar_path, history_path = write_take_sidecars(
        output_dir,
        TakeSidecar(
            video_path=dest,
            track_label=track_label,
            recorded_start=captured_at,
            finalized_at=clock(),
            sync_offset_ms=sync_offset_ms,
            extra={
                "take_type": "capture_midi",
                "bars": bars,
                "tempo_bpm": tempo_bpm,
                "beats_per_bar": beats_per_bar,
                "live_current_song_time": live_current_song_time,
                "source_video_path": str(source_path.resolve()),
                "trim_seconds": trim_seconds,
            },
        ),
    )
    return CaptureResult(dest, sidecar_path, history_path)
