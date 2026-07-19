from __future__ import annotations

import threading
import time

from bridge.metadata import OscQuery
from bridge.osc_client import OscListener


class LiveOscQuery(OscQuery):
    """Synchronous metadata queries via AbletonOSC (replies on listen port)."""

    def __init__(self, listener: OscListener, timeout_s: float = 0.5) -> None:
        self._listener = listener
        self._timeout_s = timeout_s

    def get_num_tracks(self) -> int:
        return self._listener.fetch_num_tracks(self._timeout_s)

    def is_armed(self, track_id: int) -> bool:
        return self._listener.fetch_arm(track_id, self._timeout_s)

    def get_track_name(self, track_id: int) -> str:
        return self._listener.fetch_track_name(track_id, self._timeout_s)

    def get_selected_track_index(self) -> int:
        return self._listener.fetch_selected_track(self._timeout_s)

    def get_recording_track_index(self) -> int | None:
        return self._listener.fetch_recording_track_index(self._timeout_s)

    def get_tempo(self) -> float:
        return self._listener.fetch_tempo(self._timeout_s)

    def get_signature_numerator(self) -> int:
        return self._listener.fetch_signature_numerator(self._timeout_s)

    def get_current_song_time(self) -> float:
        return self._listener.fetch_current_song_time(self._timeout_s)

    def capture_midi(self, destination: int) -> None:
        self._listener.capture_midi(destination)
