import pytest

from bridge.recording_state import RecordingEdge, RecordingSignals, RecordingStateMachine


@pytest.mark.parametrize(
    "arrangement,clip_recording,expected_active",
    [
        (0, 0, False),
        (1, 0, True),
        (0, 1, True),
        (1, 1, True),
    ],
)
def test_recording_signals_active(arrangement, clip_recording, expected_active):
    signals = RecordingSignals(arrangement, 0, clip_recording)
    assert signals.active is expected_active


def test_session_status_alone_does_not_activate():
    assert RecordingSignals(0, 1, False).active is False


def test_start_on_arrangement_only():
    sm = RecordingStateMachine()
    assert sm.apply(RecordingSignals(1, 0, False)) == [RecordingEdge.STARTED]


def test_start_on_session_clip_only():
    sm = RecordingStateMachine()
    assert sm.apply(RecordingSignals(0, 0, True)) == [RecordingEdge.STARTED]


def test_stop_when_clip_finishes_after_transport_off():
    sm = RecordingStateMachine()
    sm.apply(RecordingSignals(0, 0, True))
    assert sm.apply(RecordingSignals(0, 1, True)) == []
    assert sm.apply(RecordingSignals(0, 1, False)) == [RecordingEdge.STOPPED]


def test_stop_requires_arrangement_off_and_clip_off():
    sm = RecordingStateMachine()
    sm.apply(RecordingSignals(1, 0, False))
    assert sm.apply(RecordingSignals(0, 0, False)) == [RecordingEdge.STOPPED]


def test_boot_sync_emits_start_if_already_active():
    sm = RecordingStateMachine()
    assert sm.sync_initial(RecordingSignals(1, 0, False)) == [RecordingEdge.STARTED]
    assert sm.was_active is True


def test_boot_sync_idle_when_not_active():
    sm = RecordingStateMachine()
    assert sm.sync_initial(RecordingSignals(0, 0, False)) == []
    assert sm.was_active is False
