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
        self._started_at: datetime | None = None
        self._track_label: str | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def on_edge(self, edge: RecordingEdge, _signals: RecordingSignals) -> None:
        if edge is RecordingEdge.STARTED:
            self._on_start()
        elif edge is RecordingEdge.STOPPED:
            self._on_stop()

    def _on_start(self) -> None:
        if self._is_recording:
            logger.debug("Already recording; ignoring duplicate start")
            return
        self._track_label = resolve_track_label(self._metadata, self._track_merge)
        self._started_at = self._clock()
        try:
            self._obs.start_record()
            self._is_recording = True
            logger.info("OBS recording started for track %s", self._track_label)
        except Exception:
            logger.exception("Failed to start OBS recording")
            self._track_label = None
            self._started_at = None

    def _on_stop(self) -> None:
        if not self._is_recording:
            logger.debug("Not recording; ignoring stop")
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
