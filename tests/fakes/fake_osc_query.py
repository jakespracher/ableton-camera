from __future__ import annotations


class FakeOscQuery:
    def __init__(
        self,
        *,
        num_tracks: int = 0,
        armed: dict[int, bool] | None = None,
        names: dict[int, str] | None = None,
        selected: int = 0,
        recording_track: int | None = None,
    ) -> None:
        self._num_tracks = num_tracks
        self._armed = armed or {}
        self._names = names or {}
        self._selected = selected
        self._recording_track = recording_track

    def get_num_tracks(self) -> int:
        return self._num_tracks

    def is_armed(self, track_id: int) -> bool:
        return self._armed.get(track_id, False)

    def get_track_name(self, track_id: int) -> str:
        return self._names.get(track_id, "")

    def get_selected_track_index(self) -> int:
        return self._selected

    def get_recording_track_index(self) -> int | None:
        return self._recording_track
