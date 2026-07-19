from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from bridge.metadata import resolve_track_label
from bridge.naming import extension_from_path, sanitize_component
from bridge.obs_client import ObsClient
from bridge.take_sidecar import TakeSidecar, write_take_sidecars

logger = logging.getLogger(__name__)


class CaptureMidiQuery(Protocol):
    def get_num_tracks(self) -> int: ...

    def is_armed(self, track_id: int) -> bool: ...

    def get_track_name(self, track_id: int) -> str: ...

    def get_selected_track_index(self) -> int: ...

    def get_recording_track_index(self) -> int | None: ...

    def get_tempo(self) -> float: ...

    def get_signature_numerator(self) -> int: ...

    def get_current_song_time(self) -> float: ...

    def capture_midi(self, destination: int) -> None: ...


@dataclass(frozen=True)
class CaptureResult:
    video_path: Path
    sidecar_path: Path
    history_path: Path


@dataclass(frozen=True)
class CaptureRequest:
    bars: int = 4
    destination: str = "arrangement"

    def to_json_dict(self) -> dict[str, object]:
        return {
            "bars": self.bars,
            "destination": self.destination,
        }

    @classmethod
    def from_json_dict(cls, payload: dict[str, object]) -> "CaptureRequest":
        bars = payload.get("bars", 4)
        destination = payload.get("destination", "arrangement")
        return cls(bars=int(bars), destination=str(destination))


@dataclass(frozen=True)
class CaptureResponse:
    ok: bool
    message: str
    video_path: Path | None = None
    sidecar_path: Path | None = None
    history_path: Path | None = None
    error: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "message": self.message,
            "error": self.error,
        }
        if self.video_path is not None:
            payload["video_path"] = str(self.video_path)
        if self.sidecar_path is not None:
            payload["sidecar_path"] = str(self.sidecar_path)
        if self.history_path is not None:
            payload["history_path"] = str(self.history_path)
        return payload

    @classmethod
    def from_json_dict(cls, payload: dict[str, object]) -> "CaptureResponse":
        video_path = payload.get("video_path")
        sidecar_path = payload.get("sidecar_path")
        history_path = payload.get("history_path")
        error = payload.get("error")
        return cls(
            ok=bool(payload.get("ok")),
            message=str(payload.get("message", "")),
            video_path=Path(str(video_path)) if video_path is not None else None,
            sidecar_path=Path(str(sidecar_path)) if sidecar_path is not None else None,
            history_path=Path(str(history_path)) if history_path is not None else None,
            error=str(error) if error is not None else None,
        )


CaptureTrimmer = Callable[[Path, float], tuple[Path, float | None]]

DESTINATION_CODES = {
    "auto": 0,
    "session": 1,
    "arrangement": 2,
}


def destination_code(destination: str) -> int:
    key = destination.lower()
    if key not in DESTINATION_CODES:
        choices = ", ".join(sorted(DESTINATION_CODES))
        raise ValueError(f"destination must be one of: {choices}")
    return DESTINATION_CODES[key]


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
    source_video_path: Path | None = None,
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
                "source_video_path": str((source_video_path or source_path).resolve()),
                "trim_seconds": trim_seconds,
            },
        ),
    )
    return CaptureResult(dest, sidecar_path, history_path)


def trim_replay_tail(source_path: Path, seconds: float) -> tuple[Path, float | None]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        logger.warning("ffmpeg not found; using the full replay buffer file")
        return source_path, None

    trimmed = source_path.with_name(f"{source_path.stem}.capture-tail{source_path.suffix}")
    command = [
        ffmpeg,
        "-y",
        "-sseof",
        f"-{seconds:.6f}",
        "-i",
        str(source_path),
        "-c",
        "copy",
        str(trimmed),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception:
        logger.exception("Could not trim replay buffer tail; using the full replay buffer file")
        trimmed.unlink(missing_ok=True)
        return source_path, None

    return trimmed, seconds


class CaptureService:
    def __init__(
        self,
        *,
        obs: ObsClient,
        query: CaptureMidiQuery,
        output_dir: Path,
        clock: Callable[[], datetime],
        sync_offset_ms: int = 0,
        track_merge: str = "_",
        trim_replay: CaptureTrimmer = trim_replay_tail,
    ) -> None:
        self._obs = obs
        self._query = query
        self._output_dir = output_dir
        self._clock = clock
        self._sync_offset_ms = sync_offset_ms
        self._track_merge = track_merge
        self._trim_replay = trim_replay

    def capture_midi(self, request: CaptureRequest) -> CaptureResponse:
        try:
            destination = destination_code(request.destination)
        except ValueError as exc:
            return CaptureResponse(ok=False, message=str(exc), error="invalid_request")

        if not self._obs.ensure_replay_buffer():
            return CaptureResponse(
                ok=False,
                message="OBS Replay Buffer was started; run capture again after it has history.",
                error="replay_buffer_started",
            )

        try:
            tempo_bpm = self._query.get_tempo()
            beats_per_bar = self._query.get_signature_numerator()
            live_current_song_time = self._query.get_current_song_time()
            seconds = capture_seconds(
                bars=request.bars,
                tempo_bpm=tempo_bpm,
                beats_per_bar=beats_per_bar,
            )
            track_label = resolve_track_label(self._query, self._track_merge)
            self._query.capture_midi(destination)
            source_path = self._obs.save_replay_buffer()
            if source_path is None:
                return CaptureResponse(
                    ok=False,
                    message="OBS did not publish a replay buffer video.",
                    error="missing_replay_video",
                )
            capture_source, trim_seconds = self._trim_replay(source_path, seconds)
            result = finalize_capture_take(
                source_path=capture_source,
                output_dir=self._output_dir,
                track_label=track_label,
                clock=self._clock,
                sync_offset_ms=self._sync_offset_ms,
                bars=request.bars,
                tempo_bpm=tempo_bpm,
                beats_per_bar=beats_per_bar,
                live_current_song_time=live_current_song_time,
                trim_seconds=trim_seconds,
                source_video_path=source_path,
            )
            if capture_source != source_path:
                source_path.unlink(missing_ok=True)
            return CaptureResponse(
                ok=True,
                message=f"Captured {request.bars} bars of MIDI and video.",
                video_path=result.video_path,
                sidecar_path=result.sidecar_path,
                history_path=result.history_path,
            )
        except ValueError as exc:
            return CaptureResponse(ok=False, message=str(exc), error="invalid_request")
        except Exception as exc:
            logger.exception("Capture MIDI failed")
            return CaptureResponse(
                ok=False,
                message=f"Capture MIDI failed: {exc}",
                error="capture_failed",
            )
