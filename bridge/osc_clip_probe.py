from __future__ import annotations

from bridge.clip_recording import ClipRecordingProbe, any_clip_recording
from bridge.osc_client import OscListener


class LiveOscClipProbe(ClipRecordingProbe):
    def __init__(self, listener: OscListener) -> None:
        self._listener = listener

    def get_num_tracks(self) -> int:
        return self._listener.fetch_num_tracks(0.5)

    def get_playing_slot_index(self, track_id: int) -> int:
        return self._listener.fetch_playing_slot_index(track_id, 0.3)

    def get_fired_slot_index(self, track_id: int) -> int:
        return self._listener.fetch_fired_slot_index(track_id, 0.3)

    def clip_is_recording(self, track_id: int, clip_id: int) -> bool:
        return self._listener.fetch_clip_is_recording(track_id, clip_id, 0.3)

    def any_recording(self) -> bool:
        return any_clip_recording(self)


def attach_clip_poll(listener: OscListener, interval_s: float = 0.15) -> None:
    listener.start_clip_poll(interval_s)
