from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from bridge.metadata import OscQuery, resolve_track_label
from bridge.naming import build_filename, extension_from_path
from bridge.obs_client import ObsClient
from bridge.recording_state import RecordingEdge, RecordingSignals

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
    ) -> None:
        self._obs = obs
        self._metadata = metadata
        self._output_dir = output_dir
        self._staging_dir = staging_dir
        self._track_merge = track_merge
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._is_recording = False
        self._pending_obs_start = False
        self._started_at: datetime | None = None
        self._track_label: str | None = None
        self._is_counting_in: Callable[[], bool] | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def set_counting_in_probe(self, probe: Callable[[], bool]) -> None:
        self._is_counting_in = probe

    def on_edge(self, edge: RecordingEdge, signals: RecordingSignals) -> None:
        if edge is RecordingEdge.STARTED:
            self._on_live_start()
        elif edge is RecordingEdge.STOPPED:
            self._on_stop(signals)

    def on_count_in_finished(self, signals: RecordingSignals) -> None:
        """Called when Live leaves count-in while a take is armed."""
        if self._pending_obs_start and signals.active:
            self._start_obs()

    def _on_live_start(self) -> None:
        if self._is_recording or self._pending_obs_start:
            logger.debug("Already recording or waiting for count-in; ignoring start")
            return
        self._track_label = resolve_track_label(self._metadata, self._track_merge)
        counting_in = self._is_counting_in() if self._is_counting_in else False
        if counting_in:
            self._pending_obs_start = True
            logger.info(
                "Live count-in active; deferring OBS until count-in finishes (track %s)",
                self._track_label,
            )
            return
        self._start_obs()

    def _start_obs(self) -> None:
        if self._is_recording:
            return
        self._pending_obs_start = False
        if self._started_at is None:
            self._started_at = self._clock()
        try:
            self._obs.start_record()
            self._is_recording = True
            logger.info("OBS recording started for track %s", self._track_label)
        except Exception:
            logger.exception("Failed to start OBS recording")
            self._track_label = None
            self._started_at = None
            self._pending_obs_start = False

    def _on_stop(self, _signals: RecordingSignals) -> None:
        self._pending_obs_start = False
        if not self._is_recording:
            logger.debug("Not recording; ignoring stop")
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
            logger.info("Saved recording to %s", dest)
        except Exception:
            logger.exception("Failed to finalize recording")
        finally:
            self._track_label = None
            self._started_at = None
