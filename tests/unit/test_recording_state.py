import pytest

from bridge.recording_state import RecordingEdge, RecordingSignals, RecordingStateMachine


@pytest.mark.parametrize(
    "arrangement,session,expected_active",
    [
        (0, 0, False),
        (1, 0, True),
        (0, 2, True),
        (1, 2, True),
    ],
)
def test_recording_signals_active(arrangement, session, expected_active):
    assert RecordingSignals(arrangement, session).active is expected_active


def test_start_on_arrangement_only():
    sm = RecordingStateMachine()
    assert sm.apply(RecordingSignals(1, 0)) == [RecordingEdge.STARTED]
    assert sm.apply(RecordingSignals(1, 0)) == []


def test_start_on_session_only():
    sm = RecordingStateMachine()
    assert sm.apply(RecordingSignals(0, 1)) == [RecordingEdge.STARTED]


def test_stop_only_when_both_off():
    sm = RecordingStateMachine()
    sm.apply(RecordingSignals(1, 2))
    assert sm.apply(RecordingSignals(1, 0)) == []
    assert sm.apply(RecordingSignals(0, 0)) == [RecordingEdge.STOPPED]


def test_boot_sync_emits_start_if_already_active():
    sm = RecordingStateMachine()
    assert sm.sync_initial(RecordingSignals(1, 0)) == [RecordingEdge.STARTED]
    assert sm.was_active is True


def test_boot_sync_idle_when_not_active():
    sm = RecordingStateMachine()
    assert sm.sync_initial(RecordingSignals(0, 0)) == []
    assert sm.was_active is False
