import pytest
from datetime import datetime, timezone

from bridge.recording_state import RecordingEdge, RecordingSignals
from bridge.recorder import Recorder
from tests.conftest import wire_recorder_probes
from tests.fakes.fake_obs import FakeObsClient
from tests.fakes.fake_osc_query import FakeOscQuery


@pytest.mark.integration
def test_finalize_moves_not_copies(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    staged = staging_dir / "raw.mkv"
    staged.write_bytes(b"data")
    obs.set_staged_file(staged)
    clock = lambda: datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Drums"}),
        output_dir,
        staging_dir,
        clock=clock,
    )
    wire_recorder_probes(recorder)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))
    assert not staged.exists()
    assert len(list(output_dir.glob("*.mkv"))) == 1
    assert (output_dir / "last_take.json").is_file()
