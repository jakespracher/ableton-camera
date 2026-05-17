from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class OscQuery(Protocol):
    def get_num_tracks(self) -> int: ...

    def is_armed(self, track_id: int) -> bool: ...

    def get_track_name(self, track_id: int) -> str: ...

    def get_selected_track_index(self) -> int: ...

    def get_recording_track_index(self) -> int | None: ...


def resolve_track_label(query: OscQuery, merge: str = "_") -> str:
    num_tracks = query.get_num_tracks()
    armed_names: list[str] = []
    for track_id in range(num_tracks):
        if query.is_armed(track_id):
            name = query.get_track_name(track_id)
            if name:
                armed_names.append(name)

    if len(armed_names) == 1:
        return armed_names[0]
    if len(armed_names) > 1:
        return merge.join(armed_names)

    recording = query.get_recording_track_index()
    if recording is not None and 0 <= recording < num_tracks:
        name = query.get_track_name(recording)
        if name:
            return name

    selected = query.get_selected_track_index()
    if 0 <= selected < num_tracks:
        name = query.get_track_name(selected)
        if name:
            return name

    logger.warning(
        "Could not resolve track name (num_tracks=%s, armed=%s, recording_track=%s, selected=%s)",
        num_tracks,
        armed_names,
        recording,
        selected,
    )
    return "UnknownTrack"
