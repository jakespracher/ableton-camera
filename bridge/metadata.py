from __future__ import annotations

from typing import Protocol


class OscQuery(Protocol):
    def get_num_tracks(self) -> int: ...

    def is_armed(self, track_id: int) -> bool: ...

    def get_track_name(self, track_id: int) -> str: ...

    def get_selected_track_index(self) -> int: ...


def resolve_track_label(query: OscQuery, merge: str = "_") -> str:
    num_tracks = query.get_num_tracks()
    armed_names: list[str] = []
    for track_id in range(num_tracks):
        if query.is_armed(track_id):
            armed_names.append(query.get_track_name(track_id))

    if len(armed_names) == 1:
        return armed_names[0]
    if len(armed_names) > 1:
        return merge.join(armed_names)

    selected = query.get_selected_track_index()
    if 0 <= selected < num_tracks:
        name = query.get_track_name(selected)
        if name:
            return name

    return "UnknownTrack"
