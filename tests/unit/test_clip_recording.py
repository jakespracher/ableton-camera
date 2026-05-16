from bridge.clip_recording import any_clip_recording


class StubProbe:
    def __init__(self, recording_slots: set[tuple[int, int]]):
        self._recording = recording_slots

    def get_num_tracks(self) -> int:
        return 2

    def get_playing_slot_index(self, track_id: int) -> int:
        return 0 if track_id == 0 else -1

    def get_fired_slot_index(self, track_id: int) -> int:
        return -1

    def clip_is_recording(self, track_id: int, clip_id: int) -> bool:
        return (track_id, clip_id) in self._recording


def test_any_clip_recording_checks_playing_slot():
    probe = StubProbe({(0, 0)})
    assert any_clip_recording(probe) is True


def test_no_recording():
    probe = StubProbe(set())
    assert any_clip_recording(probe) is False
