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
