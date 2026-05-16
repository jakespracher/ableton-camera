import pytest

from bridge.recording_state import RecordingEdge, RecordingSignals, RecordingStateMachine


@pytest.mark.parametrize(
    "arrangement,clip_recording,expected",
    [
        (0, 0, False),
        (1, 0, True),
        (0, 1, True),
        (1, 1, True),
    ],
)
def test_stop_active(arrangement, clip_recording, expected):
    assert RecordingSignals(arrangement, 0, clip_recording).stop_active is expected


def test_session_status_alone_does_not_keep_stop_active():
    assert RecordingSignals(0, 1, False).stop_active is False


def test_stop_when_clip_finishes_while_session_still_on():
    sm = RecordingStateMachine()
    sm.apply(RecordingSignals(0, 1, True))
    assert sm.apply(RecordingSignals(0, 1, False)) == [RecordingEdge.STOPPED]


def test_start_on_arrangement():
    sm = RecordingStateMachine()
    assert sm.apply(RecordingSignals(1, 0, False)) == [RecordingEdge.STARTED]


def test_start_on_clip_recording():
    sm = RecordingStateMachine()
    assert sm.apply(RecordingSignals(0, 0, True)) == [RecordingEdge.STARTED]
