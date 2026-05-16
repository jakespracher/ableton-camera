from __future__ import annotations

from typing import Protocol


class ClipRecordingProbe(Protocol):
    def get_num_tracks(self) -> int: ...

    def get_playing_slot_index(self, track_id: int) -> int: ...

    def get_fired_slot_index(self, track_id: int) -> int: ...

    def clip_is_recording(self, track_id: int, clip_id: int) -> bool: ...


def _slots_to_check(probe: ClipRecordingProbe, track_id: int, *, max_slots: int) -> set[int]:
    slots: set[int] = set()
    playing = probe.get_playing_slot_index(track_id)
    fired = probe.get_fired_slot_index(track_id)
    if playing >= 0:
        slots.add(playing)
    if fired >= 0:
        slots.add(fired)
    if not slots:
        slots.update(range(max_slots))
    return slots


def any_clip_recording(probe: ClipRecordingProbe, *, max_slots: int = 8) -> bool:
    """True if any session clip slot is still recording (including quantized tail)."""
    num_tracks = probe.get_num_tracks()
    for track_id in range(num_tracks):
        for clip_id in _slots_to_check(probe, track_id, max_slots=max_slots):
            if probe.clip_is_recording(track_id, clip_id):
                return True
    return False
