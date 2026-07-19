from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from bridge.metadata import OscQuery, resolve_track_label
from bridge.naming import build_filename, extension_from_path
from bridge.obs_client import ObsClient
from bridge.recording_state import RecordingEdge, RecordingSignals, format_signals
from bridge.take_sidecar import LAST_TAKE_FILENAME, TakeSidecar, write_take_sidecars

logger = logging.getLogger(__name__)

STOP_FINALIZE_ATTEMPTS = 3
STOP_FINALIZE_RETRY_DELAY_S = 0.5
TRACK_LABEL_STOP_WAIT_S = 0.75
UNKNOWN_TRACK_LABEL = "UnknownTrack"


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
        self._track_label_generation = 0
        self._track_label_thread: threading.Thread | None = None
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
            if not signals.start_active:
                logger.info("Count-in finished after record was canceled; clearing pending OBS start")
                self._pending_obs_start = False
                self._clear_take_context()
                return
            self._start_obs(reason="count_in_finished")

    def _on_live_start(self, signals: RecordingSignals) -> None:
        if self._is_recording:
            logger.info("Start ignored: OBS already recording %s", format_signals(signals))
            return
        self._begin_track_label_resolution(prefer_selected=signals.arrangement == 1)

        if signals.arrangement == 1:
            logger.info(
                "Path=arrangement_immediate track=%s %s",
                self._track_label or "pending",
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
            self._track_label or "pending",
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
                self._track_label or "pending",
            )
            return
        logger.info("Path=session_immediate_no_count_in track=%s", self._track_label or "pending")
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
                self._track_label or "pending",
                obs_ms,
                f"{lag:.0f}" if lag is not None else "?",
            )
        except Exception:
            logger.exception("Failed to start OBS recording")
            self._clear_take_context()
            self._pending_obs_start = False

    def _on_stop(self, signals: RecordingSignals) -> None:
        logger.info("Stop requested %s", format_signals(signals))
        self._pending_obs_start = False
        if not self._is_recording:
            logger.info("Stop ignored: OBS not recording")
            self._clear_take_context()
            return
        started = self._started_at or self._clock()
        try:
            staged = self._stop_obs_with_retries()
            if self._is_recording:
                return
            if staged is None or not staged.is_file():
                logger.error("No recording file found in staging after stop")
                (self._output_dir / LAST_TAKE_FILENAME).unlink(missing_ok=True)
                return
            if staged.stat().st_size <= 0:
                logger.error("Recording file is empty; not publishing latest take: %s", staged)
                (self._output_dir / LAST_TAKE_FILENAME).unlink(missing_ok=True)
                return
            track = self._track_label_for_finalize()
            ext = extension_from_path(staged)
            filename = build_filename(track, started, ext=ext)
            dest = self._output_dir / filename
            self._output_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(dest))
            if not dest.is_file():
                logger.error("Recording move did not create destination file: %s", dest)
                (self._output_dir / LAST_TAKE_FILENAME).unlink(missing_ok=True)
                return
            (self._output_dir / LAST_TAKE_FILENAME).unlink(missing_ok=True)
            sidecar, history = write_take_sidecars(
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
            logger.info("Updated take history %s", history)
        except Exception:
            logger.exception("Failed to finalize recording")
        finally:
            if not self._is_recording:
                self._clear_take_context()

    def _stop_obs_with_retries(self) -> Path | None:
        staged: Path | None = None
        for attempt in range(1, STOP_FINALIZE_ATTEMPTS + 1):
            staged = self._obs.stop_record()
            if staged is not None:
                self._is_recording = False
                return staged
            if not self._obs_still_recording():
                self._is_recording = False
                return staged
            logger.warning(
                "OBS still recording after stop attempt %s/%s",
                attempt,
                STOP_FINALIZE_ATTEMPTS,
            )
            if attempt < STOP_FINALIZE_ATTEMPTS:
                time.sleep(STOP_FINALIZE_RETRY_DELAY_S)
        logger.error("OBS still recording after stop attempts; keeping recorder active for retry")
        return None

    def _obs_still_recording(self) -> bool:
        try:
            return self._obs.is_recording()
        except Exception:
            logger.exception("Failed to query OBS recording state after stop")
            return True

    def _begin_track_label_resolution(self, *, prefer_selected: bool = False) -> None:
        self._track_label_generation += 1
        generation = self._track_label_generation
        self._track_label = None
        thread = threading.Thread(
            target=self._resolve_track_label_async,
            args=(generation, prefer_selected),
            daemon=True,
            name="track-label-resolver",
        )
        self._track_label_thread = thread
        thread.start()

    def _resolve_track_label_async(self, generation: int, prefer_selected: bool) -> None:
        try:
            if prefer_selected:
                selected_label = self._resolve_selected_track_label()
                if selected_label:
                    self._set_track_label_if_current(
                        generation,
                        selected_label,
                        source="selected",
                    )
            label = resolve_track_label(self._metadata, self._track_merge)
        except Exception:
            logger.exception("Failed to resolve track label")
            label = UNKNOWN_TRACK_LABEL
        if label and label != UNKNOWN_TRACK_LABEL:
            self._set_track_label_if_current(generation, label, source="metadata")
        elif self._track_label is None:
            self._set_track_label_if_current(generation, UNKNOWN_TRACK_LABEL, source="fallback")

    def _resolve_selected_track_label(self) -> str:
        selected = self._metadata.get_selected_track_index()
        if selected >= 0:
            return self._metadata.get_track_name(selected)
        return ""

    def _set_track_label_if_current(self, generation: int, label: str, *, source: str) -> bool:
        if generation != self._track_label_generation:
            return False
        self._track_label = label or UNKNOWN_TRACK_LABEL
        logger.info("Resolved %s track label: %s", source, self._track_label)
        return True

    def _track_label_for_finalize(self) -> str:
        if self._track_label and self._track_label != UNKNOWN_TRACK_LABEL:
            return self._track_label
        thread = self._track_label_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=TRACK_LABEL_STOP_WAIT_S)
            if thread.is_alive():
                logger.warning("Track label resolution timed out; using UnknownTrack")
        return self._track_label or UNKNOWN_TRACK_LABEL

    def _clear_take_context(self) -> None:
        self._track_label_generation += 1
        self._track_label = None
        self._track_label_thread = None
        self._started_at = None
