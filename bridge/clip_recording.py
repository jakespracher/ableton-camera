from __future__ import annotations

from typing import Protocol


class ClipRecordingProbe(Protocol):
    def get_num_tracks(self) -> int: ...

    def get_playing_slot_index(self, track_id: int) -> int: ...

    def get_fired_slot_index(self, track_id: int) -> int: ...

    def clip_slot_has_clip(self, track_id: int, clip_id: int) -> bool: ...

    def clip_is_recording(self, track_id: int, clip_id: int) -> bool: ...


def _slots_to_check(
    probe: ClipRecordingProbe,
    track_id: int,
    *,
    last_slots: dict[int, int],
) -> set[int]:
    slots: set[int] = set()
    playing = probe.get_playing_slot_index(track_id)
    fired = probe.get_fired_slot_index(track_id)
    if playing >= 0:
        slots.add(playing)
    if fired >= 0:
        slots.add(fired)
    if not slots and track_id in last_slots:
        slots.add(last_slots[track_id])
    return slots


def any_clip_recording(
    probe: ClipRecordingProbe,
    *,
    last_slots: dict[int, int] | None = None,
) -> bool:
    """True if any session clip slot is still recording (including quantized tail)."""
    slots_cache = last_slots if last_slots is not None else {}
    num_tracks = probe.get_num_tracks()
    for track_id in range(num_tracks):
        for clip_id in _slots_to_check(probe, track_id, last_slots=slots_cache):
            if not probe.clip_slot_has_clip(track_id, clip_id):
                continue
            if probe.clip_is_recording(track_id, clip_id):
                slots_cache[track_id] = clip_id
                return True
        slots_cache.pop(track_id, None)
    return False
