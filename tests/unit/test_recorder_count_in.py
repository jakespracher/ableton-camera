from bridge.recording_state import RecordingEdge, RecordingSignals
from bridge.recorder import Recorder
from tests.fakes.fake_obs import FakeObsClient
from tests.fakes.fake_osc_query import FakeOscQuery


def test_defers_obs_start_during_count_in(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    recorder.set_counting_in_probe(lambda: True, osc_available=lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(0, 1, False))
    assert obs.calls == []
    assert recorder._pending_obs_start is True


def test_starts_obs_after_count_in_finishes(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    recorder.set_counting_in_probe(lambda: True, osc_available=lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(0, 1, False))
    recorder.on_count_in_finished(RecordingSignals(0, 1, False))
    assert obs.calls == ["start"]


def test_cancelled_count_in_does_not_start_obs(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    recorder.set_counting_in_probe(lambda: True, osc_available=lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(0, 1, False))

    recorder.on_count_in_finished(RecordingSignals(0, 0, False))

    assert obs.calls == []
    assert recorder._pending_obs_start is False


def test_starts_obs_after_count_in_session_before_clip_recording(output_dir, staging_dir):
    """Session record is on after count-in but clip.is_recording may lag by a bar or two."""
    obs = FakeObsClient(staging_dir)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    recorder.set_counting_in_probe(lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(0, 1, False))
    recorder.on_count_in_finished(RecordingSignals(0, 1, False))
    assert obs.calls == ["start"]


def test_pending_start_retries_when_count_in_cleared(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    counting = [True]
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    recorder.set_counting_in_probe(lambda: counting[0], osc_available=lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(0, 1, False))
    assert obs.calls == []
    counting[0] = False
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(0, 1, True))
    assert obs.calls == ["start"]


def test_arrangement_starts_obs_on_record_mode(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    recorder.set_counting_in_probe(lambda: True, osc_available=lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    assert obs.calls == ["start"]


def test_starts_immediately_when_not_counting_in(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    recorder.set_counting_in_probe(lambda: False)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    assert obs.calls == ["start"]
