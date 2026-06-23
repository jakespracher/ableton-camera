from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from bridge.metadata import OscQuery, resolve_track_label
from bridge.naming import build_filename, extension_from_path
from bridge.obs_client import ObsClient
from bridge.recording_state import RecordingEdge, RecordingSignals, format_signals
from bridge.take_sidecar import TakeSidecar, write_last_take

logger = logging.getLogger(__name__)


class Recorder:
    def __init__(
        self,
        obs: ObsClient,
        metadata: OscQuery,
        output_dir: Path,
        staging_dir: Path,
        track_merge: str = "_",
        clock: Callable[[], datetime] | None = None,
        sync_offset_ms: int = 0,
    ) -> None:
        self._obs = obs
        self._metadata = metadata
        self._output_dir = output_dir
        self._staging_dir = staging_dir
        self._track_merge = track_merge
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._sync_offset_ms = sync_offset_ms
        self._is_recording = False
        self._pending_obs_start = False
        self._started_at: datetime | None = None
        self._track_label: str | None = None
        self._is_counting_in: Callable[[], bool] | None = None
        self._count_in_osc_available: Callable[[], bool] | None = None
        self._record_mode_latency_ms: Callable[[], float | None] | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def set_counting_in_probe(
        self,
        probe: Callable[[], bool] | None = None,
        *,
        osc_available: Callable[[], bool] | None = None,
        record_mode_latency_ms: Callable[[], float | None] | None = None,
    ) -> None:
        self._is_counting_in = probe or (lambda: False)
        self._count_in_osc_available = osc_available
        self._record_mode_latency_ms = record_mode_latency_ms

    def on_edge(self, edge: RecordingEdge, signals: RecordingSignals) -> None:
        logger.info(
            "Recorder edge=%s pending=%s obs_recording=%s %s",
            edge.name,
            self._pending_obs_start,
            self._is_recording,
            format_signals(signals),
        )
        if edge is RecordingEdge.STARTED:
            self._on_live_start(signals)
        elif edge is RecordingEdge.STOPPED:
            self._on_stop(signals)

    def on_count_in_finished(self, signals: RecordingSignals) -> None:
        """Called when Live leaves count-in while a take is armed."""
        logger.info(
            "Count-in finished callback pending=%s %s",
            self._pending_obs_start,
            format_signals(signals),
        )
        if self._pending_obs_start:
            self._start_obs(reason="count_in_finished")

    def _on_live_start(self, signals: RecordingSignals) -> None:
        if self._is_recording:
            logger.info("Start ignored: OBS already recording %s", format_signals(signals))
            return
        self._track_label = resolve_track_label(self._metadata, self._track_merge)

        if signals.arrangement == 1:
            logger.info(
                "Path=arrangement_immediate track=%s %s",
                self._track_label,
                format_signals(signals),
            )
            self._start_obs(reason="arrangement_record")
            return

        osc_ok = (
            self._count_in_osc_available()
            if self._count_in_osc_available is not None
            else False
        )
        counting_in = osc_ok and self._is_counting_in() if self._is_counting_in else False
        logger.info(
            "Path=session_start_probe track=%s count_in_osc=%s fetch_counting_in=%s pending=%s %s",
            self._track_label,
            osc_ok,
            counting_in,
            self._pending_obs_start,
            format_signals(signals),
        )
        if self._pending_obs_start:
            if counting_in:
                logger.info("Path=session_defer_still_counting_in (waiting)")
                return
            logger.info("Path=session_pending_cleared_after_count_in")
            self._start_obs(reason="session_pending_cleared")
            return
        if counting_in:
            self._pending_obs_start = True
            logger.info(
                "Path=session_defer_count_in track=%s (OBS after is_counting_in→0)",
                self._track_label,
            )
            return
        logger.info("Path=session_immediate_no_count_in track=%s", self._track_label)
        self._start_obs(reason="session_immediate")

    def _start_obs(self, *, reason: str = "unknown") -> None:
        if self._is_recording:
            logger.info("OBS start skipped (%s): already recording", reason)
            return
        self._pending_obs_start = False
        if self._started_at is None:
            self._started_at = self._clock()
        lag = self._record_mode_latency_ms() if self._record_mode_latency_ms else None
        t0 = time.monotonic()
        try:
            self._obs.start_record()
            self._is_recording = True
            obs_ms = (time.monotonic() - t0) * 1000.0
            logger.info(
                "OBS recording started reason=%s track=%s obs_ws_ms=%.0f record_mode_lag_ms=%s",
                reason,
                self._track_label,
                obs_ms,
                f"{lag:.0f}" if lag is not None else "?",
            )
        except Exception:
            logger.exception("Failed to start OBS recording")
            self._track_label = None
            self._started_at = None
            self._pending_obs_start = False

    def _on_stop(self, signals: RecordingSignals) -> None:
        logger.info("Stop requested %s", format_signals(signals))
        self._pending_obs_start = False
        if not self._is_recording:
            logger.info("Stop ignored: OBS not recording")
            self._track_label = None
            self._started_at = None
            return
        self._is_recording = False
        track = self._track_label or "UnknownTrack"
        started = self._started_at or self._clock()
        try:
            staged = self._obs.stop_record()
            if staged is None or not staged.is_file():
                logger.error("No recording file found in staging after stop")
                return
            ext = extension_from_path(staged)
            filename = build_filename(track, started, ext=ext)
            dest = self._output_dir / filename
            self._output_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(dest))
            if not dest.is_file():
                logger.error("Recording move did not create destination file: %s", dest)
                return
            sidecar = write_last_take(
                self._output_dir,
                TakeSidecar(
                    video_path=dest,
                    track_label=track,
                    recorded_start=started,
                    finalized_at=self._clock(),
                    sync_offset_ms=self._sync_offset_ms,
                ),
            )
            logger.info("Saved recording to %s", dest)
            logger.info("Updated take sidecar %s", sidecar)
        except Exception:
            logger.exception("Failed to finalize recording")
        finally:
            self._track_label = None
            self._started_at = None
