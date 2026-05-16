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
    recorder.set_counting_in_probe(lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0))
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
    recorder.set_counting_in_probe(lambda: True)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0))
    recorder.on_count_in_finished(RecordingSignals(1, 0))
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
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0))
    assert obs.calls == ["start"]
